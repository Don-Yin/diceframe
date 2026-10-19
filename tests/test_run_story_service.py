import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.engine.game_instance import GameState
from src.engine.modules import run_finale
from src.engine.participant_view import Viewer
from src.webui.services.run_story import RunStoryDependencies, RunStoryService
from tests.test_run_story import game, plan

GM = Viewer('gm', 'gm')
PLAYER = Viewer('seat', 'alice')


def setup():
    inst = game(); inst.state = GameState.ACTIVE_ACTION; inst.gm_uid = 'gm'
    inst.players['alice'] = {'character_name': 'Alice', 'character_sheet': {'hp': 10, 'max_hp': 10}}
    save = AsyncMock()
    llm = SimpleNamespace(call=AsyncMock())
    svc = RunStoryService(RunStoryDependencies(lambda key: inst, save,
                         lambda _: SimpleNamespace(growth_system='xp_level', template={}), lambda _: None,
                         lambda: llm))
    return svc, inst, save, llm


@pytest.mark.asyncio
async def test_gm_only_adoption_and_save_failure_atomicity():
    svc, inst, save, _ = setup()
    body = {'run_id': inst.run_id, 'revision': 0, 'plan': plan()}
    assert not (await svc.mutate('key', PLAYER, 'plan', body))['ok']
    before = deepcopy(inst.to_dict()); save.side_effect = OSError('disk full')
    result = await svc.mutate('key', GM, 'plan', body)
    assert not result['ok'] and inst.to_dict() == before
    save.side_effect = None
    assert (await svc.mutate('key', GM, 'plan', body))['ok']
    assert 'SECRET' not in str(svc.get('key', PLAYER))


@pytest.mark.asyncio
async def test_finale_blocks_actions_cancels_and_commits_once():
    svc, inst, save, _ = setup()
    for i in range(1, 15):
        inst.log.append({'round': i, 'gm_response': f'Public event {i}',
                         'info_asymmetry': {'alice': 'PRIVATE'}, 'pre_state_snapshot': {'gm': 'SECRET'}})
    assert not (await svc.mutate('key', PLAYER, 'prepare', {'run_id': inst.run_id}))['ok']
    prepared = await svc.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    assert prepared['ok']
    job = prepared['finale']['id']
    async with inst.authoritative_write() as entered:
        assert not entered
    public = svc.get('key', PLAYER)
    assert 'PRIVATE' not in str(public) and 'SECRET' not in str(public)
    assert (await svc.mutate('key', GM, 'cancel', {'run_id': inst.run_id, 'job_id': job}))['ok']
    async with inst.authoritative_write() as entered:
        assert entered
    prepared = await svc.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    job = prepared['finale']['id']
    materials = {'run_id': inst.run_id, 'job_id': job, 'job_revision': 0, 'epilogue': 'The end', 'recap': 'All fourteen rounds', 'gm_notes': 'PRIVATE'}
    assert (await svc.mutate('key', GM, 'materials', materials))['ok']
    committed = await svc.mutate('key', GM, 'commit', {**materials, 'job_revision': 1, 'confirmed': True})
    assert committed['ok'] and inst.state == GameState.ENDED
    calls = save.await_count
    again = await svc.mutate('key', GM, 'commit', {**materials, 'job_revision': 1, 'confirmed': True})
    assert again['finale']['receipt'] == committed['finale']['receipt']
    assert save.await_count == calls
    async with inst.authoritative_write() as entered:
        assert not entered
    async with inst.historical_rewrite() as entered:
        assert not entered
    assert not (await svc.mutate('key', GM, 'cancel', materials))['ok']
    archive = svc.export('key', PLAYER)
    assert 'PRIVATE' not in str(archive) and 'SECRET' not in str(archive)
    assert archive['source_rounds'] == list(range(1, 15))


@pytest.mark.asyncio
async def test_legacy_finale_export_uses_one_public_projection_without_rewriting_archive():
    svc, inst, save, _ = setup()
    # Settle an empty run, then inject the persisted source shape from a legacy
    # archive. This deliberately bypasses today's preparation-time sanitizer.
    prepared = await svc.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    assert prepared['ok']
    job = prepared['finale']['id']
    assert (await svc.mutate('key', GM, 'materials', {
        'run_id': inst.run_id, 'job_id': job, 'job_revision': 0,
        'epilogue': '公开结局', 'recap': '公开总结', 'gm_notes': 'PRIVATE GM NOTE',
    }))['ok']
    assert (await svc.mutate('key', GM, 'commit', {
        'run_id': inst.run_id, 'job_id': job, 'job_revision': 1,
        'confirmed': True,
    }))['ok']

    persisted = [
        {
            'round': 1,
            'text': '玩家走进房间。\n---\n【GM指令】SECRET PLAN',
            'actions': [
                {'user_id': 'alice', 'text': '搜查书架', 'gm_private': 'HIDDEN'},
                {'user_id': 'alice', 'text': {'gm_private': 'SECRET ACTION PAYLOAD'}},
                {'user_id': 'system', 'text': 'SECRET SYSTEM'},
                {'user_id': 'unknown', 'text': 'SECRET UNKNOWN'},
            ],
            'gm_snapshot': {'plan': 'SECRET SNAPSHOT'},
        },
        {
            'round': 3, 'text': '---\n【状态变更】PRIVATE',
            'actions': [{'user_id': 'alice', 'text': '继续前进'}],
        },
        {'round': 4, 'text': '---\n【状态变更】PRIVATE', 'actions': []},
        {'round': 5, 'text': {'secret': 'UNSAFE OBJECT'}, 'actions': []},
    ]
    inst.modules['run_finale']['archive']['source'] = deepcopy(persisted)
    frozen = deepcopy(inst.to_dict())

    public = svc.export('key', PLAYER)
    assert public['source'] == [
        {'round': 1, 'text': '玩家走进房间。',
         'actions': [{'user_id': 'alice', 'text': '搜查书架'}]},
        {'round': 3, 'text': '',
         'actions': [{'user_id': 'alice', 'text': '继续前进'}]},
    ]
    assert public['source_rounds'] == [1, 3]
    assert 'SECRET' not in str(public) and 'PRIVATE' not in str(public)
    assert 'HIDDEN' not in str(public) and 'UNSAFE OBJECT' not in str(public)
    assert 'gm_notes' not in public and 'receipt' not in public
    assert svc.export('key', PLAYER) == public
    assert inst.to_dict() == frozen
    assert inst.modules['run_finale']['archive']['source'] == persisted
    gm_export = svc.export('key', GM)
    assert gm_export['source'] == public['source']
    assert gm_export['gm_notes'] == 'PRIVATE GM NOTE'
    assert 'receipt' in gm_export


@pytest.mark.asyncio
async def test_legacy_protocol_leak_is_scrubbed_at_settlement_and_public_export():
    svc, inst, _, _ = setup()
    inst.log.extend([
        {
            "round": 1,
            "gm_response": "灰沼的雾散了。\n---\n【状态变更】\nHP: -2",
            "actions": [{"user_id": "alice", "text": "观察雾"}],
        },
        {
            "round": 2,
            "gm_response": "【GM指令】秘密出口在东侧\n你们继续赶路。",
            "actions": [{"user_id": "alice", "text": "继续赶路"}],
        },
    ])
    prepared = await svc.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    assert prepared['ok'], prepared
    body = {'run_id': inst.run_id, 'job_id': prepared['finale']['id'], 'job_revision': 0,
            'epilogue': '雾散之后', 'recap': '两人穿过灰沼', 'gm_notes': 'GM PRIVATE'}
    assert (await svc.mutate('key', GM, 'materials', body))['ok']
    assert (await svc.mutate(
        'key', GM, 'commit', {**body, 'job_revision': 1, 'confirmed': True},
    ))['ok']

    archive = svc.export('key', PLAYER)

    assert archive['source'] == [
        {'round': 1, 'text': '灰沼的雾散了。', 'actions': [{'user_id': 'alice', 'text': '观察雾'}]},
        {'round': 2, 'text': '你们继续赶路。', 'actions': [{'user_id': 'alice', 'text': '继续赶路'}]},
    ]
    assert archive['source_rounds'] == [1, 2]
    rendered = json.dumps(archive, ensure_ascii=False)
    assert 'GM PRIVATE' not in rendered
    assert 'GM指令' not in rendered and '状态变更' not in rendered
    assert 'gm_notes' not in archive and 'receipt' not in archive
    # The persisted archive and a repeated export stay identical.
    assert run_finale.view(inst)['archive']['source'] == archive['source']
    assert svc.export('key', PLAYER) == archive


@pytest.mark.asyncio
async def test_inflight_actions_and_unsettled_operations_block_prepare():
    svc, inst, _, _ = setup()
    inst.action_queue = [{'user_id': 'alice', 'text': 'pending action'}]
    result = await svc.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    assert not result['ok'] and 'actions' in str(result)
    assert inst.state != GameState.ENDED


@pytest.mark.asyncio
async def test_optional_ai_is_cancellable_and_does_not_install_plan_or_award_rewards():
    svc, inst, _, llm = setup()
    started = asyncio.Event()
    async def slow(**kwargs):
        started.set(); await asyncio.Event().wait()
    llm.call.side_effect = slow
    before = deepcopy(inst.to_dict())
    task = asyncio.create_task(svc.generate('key', GM, 'plan', {'run_id': inst.run_id, 'token_consent': True}, AsyncMock()))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert inst.to_dict() == before


@pytest.mark.asyncio
async def test_another_gm_edit_invalidates_previously_reviewed_finale_materials():
    svc, inst, _, _ = setup()
    prepared = await svc.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    job = prepared['finale']['id']
    first = await svc.mutate('key', GM, 'materials', {'run_id': inst.run_id, 'job_id': job, 'job_revision': 0,
                                                    'epilogue': 'First ending', 'recap': 'First recap'})
    assert first['ok']
    second = await svc.mutate('key', GM, 'materials', {'run_id': inst.run_id, 'job_id': job, 'job_revision': 1,
                                                     'epilogue': 'Changed ending', 'recap': 'Changed recap'})
    assert second['ok']
    before = deepcopy(inst.to_dict())
    stale = await svc.mutate('key', GM, 'commit', {'run_id': inst.run_id, 'job_id': job, 'job_revision': 1, 'confirmed': True})
    assert not stale['ok'] and inst.to_dict() == before


@pytest.mark.asyncio
async def test_finale_write_barrier_is_kernel_authority_even_without_presentation_hooks():
    from src.engine import module_hooks
    service, inst, _, _ = setup()
    assert (await service.mutate('key', GM, 'prepare', {'run_id': inst.run_id}))['ok']
    removed = module_hooks.unregister_owner('run_finale')
    try:
        async with inst.authoritative_write() as entered:
            assert not entered
    finally:
        for point, handler in removed.items():
            module_hooks.register(point, 'run_finale', handler)


@pytest.mark.asyncio
async def test_growth_retry_after_failed_save_keeps_the_same_random_outcome():
    from dataclasses import replace
    from src.engine.modules import skill_growth
    from tests.test_intermission_growth import fixture
    service, _, save, _ = setup()
    inst, rule, check = fixture()
    inst.state = GameState.ACTIVE_ACTION
    inst.gm_uid = 'gm'
    skill_growth.mark_checks(inst, rule, [check])
    service.deps = replace(service.deps, get_instance=lambda _: inst, load_rule=lambda _: rule)
    attempted = []

    async def fail_settlement(candidate):
        receipts = skill_growth.view(candidate)['receipts']
        if receipts:
            attempted.append(deepcopy(next(iter(receipts.values()))['changes']))
            raise OSError('disk full after entropy reservation')

    save.side_effect = fail_settlement
    for identity in ('retry-one', 'retry-two'):
        result = await service.mutate('key', GM, 'intermission', {'run_id': inst.run_id, 'receipt_id': identity})
        assert not result['ok']
        assert not skill_growth.view(inst)['receipts']
    assert len(attempted) == 2 and attempted[0] == attempted[1]
    assert skill_growth.view(inst).get('entropy')
    save.side_effect = None
    result = await service.mutate('key', GM, 'intermission', {'run_id': inst.run_id, 'receipt_id': 'retry-final'})
    assert result['ok']
    assert skill_growth.view(inst)['receipts']['retry-final']['changes'] == attempted[0]


@pytest.mark.asyncio
async def test_direct_lifecycle_calls_reject_frozen_run_before_model_or_state_work():
    from src.commands.game_lifecycle import GameLifecycle
    service, inst, _, _ = setup()
    await service.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    lifecycle = GameLifecycle.__new__(GameLifecycle)
    before = deepcopy(inst.to_dict())
    for action in (lifecycle.start_game, lifecycle.resume_game):
        with pytest.raises(ValueError, match='read-only'):
            await action(inst)
        assert inst.to_dict() == before
