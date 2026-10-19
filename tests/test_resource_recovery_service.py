import asyncio
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.engine.game_instance import GameInstance, GameState
from src.engine.modules import resource_recovery, skill_growth
from src.engine.participant_view import Viewer
from src.engine.world_state import clock_to_minutes, world_clock
from src.rules.rule_system import RuleSystem
from src.webui.services.resource_recovery import RecoveryDependencies, RecoveryService

GM = Viewer('gm', 'gm')
ALICE = Viewer('seat', 'alice')
BOB = Viewer('seat', 'bob')


def setup():
    template = json.loads((Path(__file__).parents[1] / 'templates/rules/freeform_coc.json').read_text(encoding='utf-8'))
    template['resource_recovery'] = {'version': 1, 'policy': 'coc_light', 'luck_recovery': 'check'}
    rule = RuleSystem(template)
    instance = GameInstance(('test', 'recovery'))
    instance.state = GameState.ACTIVE_ACTION
    instance.gm_uid = 'gm'
    instance.rule_id = rule.rule_id
    for uid in ('alice', 'bob'):
        instance.players[uid] = {'character_name': uid, 'character_sheet': {
            'hp': 12, 'max_hp': 12, 'sanity': 40, 'max_sanity': 90, 'luck': 50, 'max_luck': 99,
            'resources': {'sanity': {'current': 40, 'max': 90}, 'luck': {'current': 50, 'max': 99}},
            'skills': [{'id': 'psychoanalysis', 'name': '精神分析', 'value': 80}],
        }}
    save = AsyncMock()
    service = RecoveryService(RecoveryDependencies(lambda _key: instance, save, lambda _instance: rule))
    return service, instance, save, rule


def body(service, instance, operation_id, **fields):
    return {'run_id': instance.run_id, 'operation_id': operation_id,
            'expected_revision': service.get('key', GM)['revision'], **fields}


async def request_rest(service, instance):
    result = await service.mutate('key', ALICE, 'request', body(service, instance, 'request-rest', kind='overnight'))
    assert result['ok'], result
    return result['source_id']


@pytest.mark.asyncio
async def test_request_is_not_qualification_and_only_gm_can_approve():
    service, instance, _, _ = setup()
    source_id = await request_rest(service, instance)
    before = deepcopy(instance.to_dict())
    assert not (await service.mutate('key', ALICE, 'approve', body(service, instance, 'forged', source_id=source_id)))['ok']
    assert not (await service.mutate('key', BOB, 'claim', body(service, instance, 'cross-actor', source_id=source_id)))['ok']
    assert instance.to_dict() == before
    approved = await service.mutate('key', GM, 'approve', body(service, instance, 'approve-rest', source_id=source_id))
    assert approved['ok'], approved
    assert 41 <= instance.get_character_sheet('alice')['sanity'] <= 46
    assert clock_to_minutes(world_clock(instance.world_state)) == 480
    same = await service.mutate('key', GM, 'approve', body(service, instance, 'approve-rest', source_id=source_id))
    assert same['ok'] and same['duplicate']
    assert clock_to_minutes(world_clock(instance.world_state)) == 480
    assert not (await service.mutate('key', GM, 'approve', body(service, instance, 'another-approval', source_id=source_id)))['ok']


@pytest.mark.asyncio
async def test_existing_elapsed_time_is_not_advanced_twice_and_failed_save_restores_world_and_character():
    from src.engine.world_events import advance_world_time
    service, instance, save, _ = setup()
    source_id = await request_rest(service, instance)
    advance_world_time(instance, 480)
    before = deepcopy(instance.to_dict())
    save.side_effect = OSError('disk full')
    failed = await service.mutate('key', GM, 'approve', body(service, instance, 'approve', source_id=source_id))
    assert not failed['ok'] and instance.to_dict() == before
    save.side_effect = None
    result = await service.mutate('key', GM, 'approve', body(service, instance, 'approve', source_id=source_id))
    assert result['ok'], result
    assert clock_to_minutes(world_clock(instance.world_state)) == 480
    assert result['receipt']['time_advanced_minutes'] == 0


@pytest.mark.asyncio
async def test_cancellation_rolls_back_all_domain_state():
    service, instance, save, _ = setup()
    source_id = await request_rest(service, instance)
    before = deepcopy(instance.to_dict())
    save.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await service.mutate('key', GM, 'approve', body(service, instance, 'cancelled', source_id=source_id))
    assert instance.to_dict() == before


@pytest.mark.asyncio
async def test_concurrent_claims_and_operation_payload_reuse_cannot_duplicate_rewards():
    service, instance, _, _ = setup()
    grant_body = body(service, instance, 'grant', actor_uid='alice', resource_key='sanity', resource_delta=3, reason='Resolved the haunting')
    grant = await service.mutate('key', GM, 'reward', grant_body)
    assert grant['ok'], grant
    source_id = grant['source_id']
    revision = service.get('key', ALICE)['revision']
    results = await asyncio.gather(*[
        service.mutate('key', ALICE, 'claim', {'run_id': instance.run_id, 'expected_revision': revision,
                       'operation_id': operation_id, 'source_id': source_id})
        for operation_id in ('claim-a', 'claim-b')
    ])
    assert sum(result['ok'] for result in results) == 1
    assert instance.get_character_sheet('alice')['sanity'] == 43
    reused = await service.mutate('key', GM, 'reward', {**grant_body, 'resource_delta': 9})
    assert not reused['ok']
    assert reused['code'] == 'OPERATION_ID_REUSED'


@pytest.mark.asyncio
async def test_therapy_ignores_client_rolls_and_binds_the_server_check():
    service, instance, _, _ = setup()
    result = await service.mutate('key', ALICE, 'request', body(service, instance, 'therapy',
        kind='therapy', healer_uid='bob', skill_id='psychoanalysis', check_id='ordinary-check'))
    assert not result['ok']
    result = await service.mutate('key', ALICE, 'request', body(service, instance, 'therapy',
        kind='therapy', healer_uid='bob', skill_id='psychoanalysis'))
    assert result['ok'], result
    source_id = result['source_id']
    settled = await service.mutate('key', GM, 'approve', body(service, instance, 'treat', source_id=source_id))
    assert settled['ok'], settled
    receipt = settled['receipt']
    assert receipt['actor_uid'] == 'alice' and receipt['healer_uid'] == 'bob'
    assert receipt['skill_id'] == 'psychoanalysis' and receipt['check_id']


@pytest.mark.asyncio
async def test_luck_requires_an_existing_played_intermission_and_same_round_cannot_grant_twice():
    service, instance, _, rule = setup()
    result = await service.mutate('key', GM, 'luck', body(service, instance, 'fake', intermission_id='invented'))
    assert not result['ok']
    instance.round_number = 2
    instance.log = [{'round': 1, 'gm_response': 'A completed session.'}]
    skill_growth.settle(instance, rule, 'session-a', expected_run=instance.run_id)
    result = await service.mutate('key', GM, 'luck', body(service, instance, 'luck-a', intermission_id='session-a'))
    assert result['ok'], result
    skill_growth.settle(instance, rule, 'session-b', expected_run=instance.run_id)
    result = await service.mutate('key', GM, 'luck', body(service, instance, 'luck-b', intermission_id='session-b'))
    assert not result['ok']
    assert len([s for s in resource_recovery.view(instance)['sources'].values() if s['kind'] == 'luck']) == 2


def test_projection_excludes_seeds_other_players_and_internals_and_does_not_materialize_state():
    service, instance, _, _ = setup()
    instance.modules.pop('resource_recovery', None)
    before = deepcopy(instance.to_dict())
    assert service.get('key', ALICE)['supported']
    assert instance.to_dict() == before
    assert not service.get('key', Viewer('outsider'))['ok']


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['ended', 'away', 'dead', 'san_zero', 'stale_run', 'stale_revision'])
async def test_ineligible_or_stale_requests_change_nothing(condition):
    service, instance, _, _ = setup()
    request = body(service, instance, 'request', kind='overnight')
    if condition == 'ended': instance.state = GameState.ENDED
    if condition == 'away': instance.away_players.add('alice')
    if condition == 'dead': instance.players['alice']['character_sheet']['deceased'] = True
    if condition == 'san_zero': instance.players['alice']['character_sheet']['sanity'] = 0
    if condition == 'stale_run': request['run_id'] = 'old-run'
    if condition == 'stale_revision': request['expected_revision'] = 999
    before = deepcopy(instance.to_dict())
    assert not (await service.mutate('key', ALICE, 'request', request))['ok']
    assert instance.to_dict() == before


@pytest.mark.asyncio
async def test_clock_due_events_source_and_balance_commit_and_rollback_together():
    from src.engine.world_state import apply_world_ops, fact_value, world_scheduled_events
    service, instance, save, _ = setup()
    apply_world_ops(instance, [{'op': 'schedule_event', 'event_id': 'dawn',
        'due_at': {'day': 1, 'minute': 400}, 'label': 'Secret dawn event',
        'ops': [{'op': 'set_fact', 'key': 'secret', 'value': 'revealed'}]}])
    source = await request_rest(service, instance)
    before = deepcopy(instance.to_dict())
    save.side_effect = OSError('disk full')
    operation = body(service, instance, 'with-event', source_id=source)
    assert not (await service.mutate('key', GM, 'approve', operation))['ok']
    assert instance.to_dict() == before
    save.side_effect = None
    first = await service.mutate('key', GM, 'approve', operation)
    assert first['ok'] and first['receipt']['time_advanced_minutes'] == 480
    assert fact_value(instance.world_state, 'secret') == 'revealed'
    assert world_scheduled_events(instance.world_state)['dawn']['status'] == 'applied'
    state = resource_recovery.view(instance)
    assert len(state['commands']['with-event']['world_events']) == 1
    assert state['commands']['with-event']['world_events'][0]['applied'][0]['event_id'] == 'dawn'
    player = service.get('key', ALICE)
    assert 'Secret dawn event' not in json.dumps(player)
    assert 'seed' not in json.dumps(player) and 'commands' not in player


@pytest.mark.asyncio
async def test_standard_style_only_monthly_psychoanalysis_with_one_clock_owner():
    service, instance, save, rule = setup()
    rule.template['resource_recovery']['policy'] = 'coc7e_style'
    actions = service.get('key', ALICE)['actions']
    assert [action['id'] for action in actions] == ['therapy']
    assert actions[0]['duration_minutes'] == 43200
    assert not (await service.mutate('key', ALICE, 'request', body(service, instance, 'night', kind='overnight')))['ok']
    assert not (await service.mutate('key', ALICE, 'request', body(service, instance, 'psych',
        kind='therapy', healer_uid='bob', skill_id='psychology')))['ok']
    request = await service.mutate('key', ALICE, 'request', body(service, instance, 'month',
        kind='therapy', healer_uid='bob', skill_id='psychoanalysis'))
    assert request['ok']
    save.reset_mock()
    result = await service.mutate('key', GM, 'approve', body(service, instance, 'treat-month', source_id=request['source_id']))
    assert result['ok'], result
    assert result['receipt']['time_advanced_minutes'] == 43200
    assert clock_to_minutes(world_clock(instance.world_state)) == 43200
    # Thirty event-safe clock chunks still persist as one aggregate transaction.
    save.assert_awaited_once()
    saved = deepcopy(instance.to_dict())
    duplicate = await service.mutate('key', GM, 'approve', body(service, instance, 'treat-month', source_id=request['source_id']))
    assert duplicate['ok'] and duplicate['duplicate'] and instance.to_dict() == saved


@pytest.mark.asyncio
async def test_projection_filters_other_actors_sources_after_grants_and_reload():
    service, instance, save, rule = setup()
    ids = []
    for actor in ('alice', 'bob'):
        result = await service.mutate('key', GM, 'reward', body(service, instance, f'grant-{actor}',
            actor_uid=actor, resource_key='luck', resource_delta=2, reason=f'Private reward for {actor}'))
        assert result['ok']
        ids.append(result['source_id'])
    claim = body(service, instance, 'claim-alice', source_id=ids[0])
    result = await service.mutate('key', ALICE, 'claim', claim)
    assert result['ok']
    restored = GameInstance.from_dict(deepcopy(instance.to_dict()))
    service = RecoveryService(RecoveryDependencies(lambda _: restored, save, lambda _: rule))
    again = await service.mutate('key', ALICE, 'claim', claim)
    assert again['ok'] and again['duplicate']
    assert restored.get_character_sheet('alice')['luck'] == 52
    alice = service.get('key', ALICE)
    bob = service.get('key', BOB)
    assert {row['actor_uid'] for row in alice['sources']} == {'alice'}
    assert {row['actor_uid'] for row in alice['receipts']} == {'alice'}
    assert {row['actor_uid'] for row in bob['sources']} == {'bob'}
    assert bob['receipts'] == [] and alice['intermissions'] == []
    assert ids[1] not in json.dumps(alice)
    assert 'seed' not in json.dumps(service.get('key', GM))


@pytest.mark.asyncio
@pytest.mark.parametrize('extra', [{'rolls': [100]}, {'amount': 99}, {'success': True},
    {'recipient_uid': 'bob'}, {'target_uid': 'bob'}, {'expected_revision': True}])
async def test_client_cannot_inject_results_targets_or_bool_revision(extra):
    service, instance, _, _ = setup()
    before = deepcopy(instance.to_dict())
    result = await service.mutate('key', ALICE, 'request', body(service, instance, 'injection', kind='overnight', **extra))
    assert not result['ok'] and result['code'] == 'INVALID_REQUEST'
    assert instance.to_dict() == before


@pytest.mark.asyncio
async def test_save_validation_failure_is_safely_reported_and_rolled_back():
    service, instance, save, _ = setup()
    source = await request_rest(service, instance)
    before = deepcopy(instance.to_dict())
    save.side_effect = ValueError('private backend path')
    result = await service.mutate('key', GM, 'approve', body(service, instance, 'bad-save', source_id=source))
    assert result['code'] == 'SAVE_FAILED' and 'private backend path' not in result['error']
    assert instance.to_dict() == before


@pytest.mark.asyncio
async def test_world_event_adventure_gate_and_memory_share_the_recovery_transaction():
    from src.engine.modules import economy_state
    from src.engine.world_state import apply_world_ops
    service, instance, save, rule = setup()
    apply_world_ops(instance, [{'op': 'start_process', 'process_id': 'new-dawn',
        'kind': 'ritual', 'participants': [], 'due_at': {'day': 1, 'minute': 400}}])
    observed = []
    def gate(staged):
        observed.append(clock_to_minutes(world_clock(staged.world_state)))
        staged.modules['gate_test_marker'] = {'world_advanced': True}
    service = RecoveryService(RecoveryDependencies(lambda _: instance, save, lambda _: rule, gate))
    source = await request_rest(service, instance)
    before = deepcopy(instance.to_dict())
    save.side_effect = OSError('full')
    assert not (await service.mutate('key', GM, 'approve', body(service, instance, 'gate', source_id=source)))['ok']
    assert instance.to_dict() == before
    save.side_effect = None
    result = await service.mutate('key', GM, 'approve', body(service, instance, 'gate', source_id=source))
    assert result['ok'], result
    assert observed == [480, 480] and instance.modules['gate_test_marker']['world_advanced']
    deliveries = economy_state.state(instance)['external_effects_outbox']
    assert any(row['payload'].get('memory_kind') == 'authoritative_world' for row in deliveries)


def test_invalid_treatment_metadata_is_a_readable_error_not_an_opaque_server_error():
    service, _, _, rule = setup()
    rule.template['skills']['psychoanalysis'] = 'bad metadata'
    result = service.get('key', ALICE)
    assert result['ok'] is False and result['code'] == 'RECOVERY_UNAVAILABLE'
    rule.template['skills'] = ['bad container']
    assert service.get('key', ALICE)['ok'] is False


@pytest.mark.asyncio
async def test_authenticated_owner_can_authorize_a_legacy_table_without_a_gm_uid():
    service, instance, _, _ = setup()
    instance.gm_uid = ''
    source = await request_rest(service, instance)
    result = await service.mutate('key', Viewer('gm'), 'approve', body(service, instance, 'owner', source_id=source))
    assert result['ok'], result
    assert resource_recovery.view(instance)['sources'][source]['authorizer']
