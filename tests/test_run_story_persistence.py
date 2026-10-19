from copy import deepcopy

import pytest

from src.engine.game_instance import GameInstance, GameRegistry, GameState
from src.engine.modules import run_finale
from src.engine.participant_view import Viewer
from src.migrations.instance import CURRENT_INSTANCE_SCHEMA_VERSION, migrate_game_state_payload, rebind_imported_game_state_payload
from tests.test_run_story_service import setup, GM


@pytest.mark.asyncio
async def test_preparation_restarts_without_phase_change_ghost_cleanup_or_lost_source(tmp_path):
    svc, inst, _, _ = setup(); inst.game_key = ('web', 'archive', 'bot')
    inst.players['never-acted'] = {'character_name': 'Observer', 'character_sheet': {'hp': 10, 'max_hp': 10}}
    for i in range(1, 125):
        inst.log.append({'round': i, 'gm_response': f'Public event {i}', 'actions': [{'user_id': 'alice', 'text': 'Look'}]})
    assert (await svc.mutate('key', GM, 'prepare', {'run_id': inst.run_id}))['ok']
    before = run_finale.view(inst)['job']
    registry = GameRegistry(tmp_path / 'saves'); await registry.save(inst)
    restored_registry = GameRegistry(tmp_path / 'saves')
    recovered = await restored_registry.recover_all()
    restored = restored_registry.get(inst.game_key)
    assert not recovered and restored.state == GameState.ACTIVE_ACTION
    assert 'never-acted' in restored.players
    _, job = run_finale.require_job(restored, before['id'])
    assert len(job['source']) == 124 and job == before
    async with restored.authoritative_write() as entered:
        assert not entered


def test_migration_fences_old_readers_without_inventing_historical_growth_or_plan():
    assert CURRENT_INSTANCE_SCHEMA_VERSION >= 46
    inst = GameInstance(('web', 'old', 'bot'))
    old = deepcopy(inst.to_dict()); old['instance_schema_version'] = 45
    for key in ('run_story', 'skill_growth', 'run_finale'):
        old['modules'].pop(key, None)
    old['players'] = {'p': {'character_name': 'P', 'character_sheet': {'skills': [{'name': 'Search', 'value': 65}]}}}
    migrated = migrate_game_state_payload(old)
    assert old['instance_schema_version'] == 45
    assert migrated['players'] == old['players']
    assert migrate_game_state_payload(migrated) == migrated
    restored = GameInstance.from_dict(migrated)
    assert restored.modules['run_story']['plan'] is None
    assert restored.modules['skill_growth']['pending'] == []


@pytest.mark.asyncio
async def test_import_preparing_refuses_and_exported_ended_run_cannot_resettle():
    svc, inst, _, _ = setup()
    result = await svc.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    with pytest.raises(ValueError):
        rebind_imported_game_state_payload(inst.to_dict(), game_key=('web', 'copy', 'bot'), run_id='new-run')
    job = result['finale']['id']
    body = {'run_id': inst.run_id, 'job_id': job, 'job_revision': 0, 'epilogue': 'End', 'recap': 'Recap'}
    await svc.mutate('key', GM, 'materials', body)
    await svc.mutate('key', GM, 'commit', {**body, 'job_revision': 1, 'confirmed': True})
    rebound = rebind_imported_game_state_payload(inst.to_dict(), game_key=('web', 'copy', 'bot'), run_id='new-run')
    copy = GameInstance.from_dict(rebound)
    assert copy.state == GameState.ENDED
    async with copy.authoritative_write() as entered:
        assert not entered
    assert run_finale.project(copy, is_gm=False)['epilogue'] == 'End'


@pytest.mark.asyncio
async def test_settled_save_zip_contains_verifiable_materials_and_character_cards(tmp_path):
    import hashlib
    import json
    import zipfile
    from io import BytesIO
    from tests.test_game_packages import _Registry, _service
    svc, inst, _, _ = setup()
    inst.game_key = ('web', 'settled-export', 'bot')
    prepared = await svc.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    body = {'run_id': inst.run_id, 'job_id': prepared['finale']['id'], 'job_revision': 0,
            'epilogue': 'Public end', 'recap': 'All public events', 'gm_notes': 'GM NOTES'}
    await svc.mutate('key', GM, 'materials', body)
    assert (await svc.mutate('key', GM, 'commit', {**body, 'job_revision': 1, 'confirmed': True}))['ok']
    registry = _Registry(tmp_path)
    registry.instances[inst.game_key] = inst
    path = registry.save_package_state_path(inst.game_key)
    path.parent.mkdir(parents=True)
    payload = inst.to_dict()
    payload['modules']['room_access']['bot_bind_token'] = 'ROOM SECRET'
    path.write_text(json.dumps(payload), encoding='utf-8')
    packages, _ = _service(registry)
    result = packages.export_game_package('|'.join(inst.game_key))
    assert result['ok']
    with zipfile.ZipFile(BytesIO(result['payload'])) as archive:
        manifest = json.loads(archive.read('finale/manifest.json'))
        for name, digest in manifest['sha256'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        assert archive.read('finale/epilogue.md').decode() == 'Public end'
        assert archive.read('finale/recap.md').decode() == 'All public events'
        card = json.loads(archive.read(manifest['characters'][0]['path']))
        assert card['character_sheet'] == run_finale.view(inst)['archive']['characters']['alice']
        assert 'ROOM SECRET' not in str([archive.read(name) for name in archive.namelist()])


@pytest.mark.parametrize('slot', [
    {'schema_version': True},
    {'schema_version': 1, 'job': [], 'archive': None, 'deliveries': {}},
    {'schema_version': 1, 'job': {}, 'archive': None, 'deliveries': {}},
    {'schema_version': 1, 'job': None, 'archive': {}, 'deliveries': {}},
])
def test_invalid_finale_envelope_cannot_reopen_a_persisted_write_barrier(slot):
    inst = GameInstance(('web', 'malformed', 'bot'))
    inst.modules['run_finale'] = slot
    before = deepcopy(inst.modules)
    with pytest.raises(ValueError):
        inst.run_writable()
    assert inst.modules == before


@pytest.mark.parametrize('name', ['run_finale', 'skill_growth', 'run_story'])
@pytest.mark.parametrize('slot', [None, [], 'damaged', True, 1])
def test_loading_malformed_run_slots_never_silently_replaces_authority_with_empty_state(name, slot):
    payload = GameInstance(('web', 'malformed-save', 'bot')).to_dict()
    payload['modules'][name] = slot
    before = deepcopy(payload)
    with pytest.raises(ValueError):
        GameInstance.from_dict(payload)
    assert payload == before


@pytest.mark.parametrize('name', ['run_finale', 'skill_growth', 'run_story'])
def test_boolean_module_schema_cannot_admit_gameplay_writes(name):
    inst = GameInstance(('web', 'boolean-schema', 'bot'))
    inst.modules[name]['schema_version'] = True
    with pytest.raises(ValueError):
        inst.run_writable()


@pytest.mark.parametrize('modules', [None, [], 'damaged', True, 1])
def test_current_save_cannot_discard_a_damaged_module_container(modules):
    payload = GameInstance(('web', 'damaged-container', 'bot')).to_dict()
    payload['modules'] = modules
    before = deepcopy(payload)
    with pytest.raises(ValueError, match='module container'):
        GameInstance.from_dict(payload)
    assert payload == before
