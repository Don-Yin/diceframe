"""Cold-start upgrades keep legacy world provenance usable without manual repair."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

import pytest

from src.engine.game_instance import GameInstance
from src.lorebook.store import LorebookStore
from src.webui.services.lorebooks import LorebookDependencies, list_lorebooks
from src.migrations.world_identity import migrate_legacy_world_ids, WorldIdentityMigrationError
from tests.world_identity_fixture import _make_fixture, OLD_WORLD_ID


def test_automatic_v4_upgrade_keeps_names_entries_and_existing_games(tmp_path):
    _make_fixture(tmp_path)
    old_paths = sorted(tmp_path.glob('saves/*/state*.json'))
    originals = {path: json.loads(path.read_text(encoding='utf-8')) for path in old_paths}
    mapping = migrate_legacy_world_ids(tmp_path, tmp_path / 'templates/worlds')
    assert OLD_WORLD_ID in mapping
    new = mapping[OLD_WORLD_ID]
    assert not (tmp_path / f'templates/worlds/{OLD_WORLD_ID}.json').exists()
    assert (tmp_path / f'templates/worlds/{new}.json').is_file()
    for path, before in originals.items():
        after = json.loads(path.read_text(encoding='utf-8'))
        assert after['world_id'] == new
        assert after['world_name'] == before['world_name']
        assert after['game_key'] == before['game_key']
        assert after.get('memory_namespace') == before.get('memory_namespace')
        assert after['chatlog_marker'] == before['chatlog_marker']
        assert after['players'] == before['players']
        assert GameInstance.from_dict(after).world_id == new
    store = LorebookStore(tmp_path / 'lorebook.db')
    store.open()
    try:
        rows = list_lorebooks(LorebookDependencies(store, lambda _: None, lambda: None), world_id=new)['books']
        assert rows[0]['ref']['source_id'] == new and rows[0]['entry_count'] == 20
    finally:
        store.close()
    snapshot = {path: path.read_bytes() for path in old_paths}
    assert migrate_legacy_world_ids(tmp_path, tmp_path / 'templates/worlds') == {}
    assert snapshot == {path: path.read_bytes() for path in old_paths}


def test_upgrade_resumes_after_process_stops_between_db_commit_and_file_publication(tmp_path):
    _make_fixture(tmp_path)
    from src.migrations import world_identity
    original = world_identity._publish_file
    counter = 0
    def interrupted(root, record):
        nonlocal counter
        counter += 1
        if counter == 2:
            raise OSError('process interrupted')
        return original(root, record)
    with patch.object(world_identity, '_publish_file', interrupted):
        with pytest.raises(OSError):
            migrate_legacy_world_ids(tmp_path, tmp_path / 'templates/worlds')
    mapping = migrate_legacy_world_ids(tmp_path, tmp_path / 'templates/worlds')
    assert OLD_WORLD_ID in mapping
    assert migrate_legacy_world_ids(tmp_path, tmp_path / 'templates/worlds') == {}
    conn = sqlite3.connect(tmp_path / 'lorebook.db')
    assert conn.execute('SELECT count(*) FROM lorebook_entries').fetchone()[0] == 20
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    conn.close()


def test_upgrade_refuses_changed_file_instead_of_overwriting_after_interruption(tmp_path):
    _make_fixture(tmp_path)
    with patch('src.migrations.world_identity._publish_file', side_effect=OSError('interrupt')):
        with pytest.raises(OSError):
            migrate_legacy_world_ids(tmp_path, tmp_path / 'templates/worlds')
    state = next(tmp_path.glob('saves/*/state.json'))
    modified = json.loads(state.read_text(encoding='utf-8'))
    modified['world_name'] = 'User edit after interrupted upgrade'
    state.write_text(json.dumps(modified), encoding='utf-8')
    with pytest.raises(WorldIdentityMigrationError, match='changed'):
        migrate_legacy_world_ids(tmp_path, tmp_path / 'templates/worlds')
    assert json.loads(state.read_text(encoding='utf-8')) == modified


def test_database_conflict_leaves_templates_and_saves_untouched(tmp_path):
    _make_fixture(tmp_path)
    from src.migrations.world_identity import migrated_world_id
    new = migrated_world_id(OLD_WORLD_ID)
    conn = sqlite3.connect(tmp_path / 'lorebook.db')
    conn.execute('INSERT INTO worlds (id,name) VALUES (?,?)', (new, 'Another existing world'))
    conn.commit(); conn.close()
    files = {path: path.read_bytes() for path in tmp_path.rglob('*.json')}
    with pytest.raises(ValueError):
        migrate_legacy_world_ids(tmp_path, tmp_path / 'templates/worlds')
    assert all(path.read_bytes() == content for path, content in files.items())


def test_subsystem_construction_migrates_before_loading_saves_or_seeding_books(tmp_path):
    _make_fixture(tmp_path)
    from src.common_factory import create_trpg_subsystems
    events = []
    def upgraded(data, worlds):
        events.append('migration')
        return {}
    def registry(*_args, **_kwargs):
        assert events == ['migration']
        raise RuntimeError('stop after registry admission')
    with patch('src.common_factory.migrate_legacy_world_ids', upgraded), patch('src.common_factory.GameRegistry', registry):
        with pytest.raises(RuntimeError, match='registry admission'):
            create_trpg_subsystems(tmp_path, tmp_path/'prompts', tmp_path/'templates/rules',
                                   tmp_path/'templates/worlds', [], '')


def test_future_save_is_refused_before_any_identity_is_changed(tmp_path):
    _make_fixture(tmp_path)
    state = next(tmp_path.glob('saves/*/state.json'))
    payload = json.loads(state.read_text(encoding='utf-8'))
    payload['instance_schema_version'] = 999
    state.write_text(json.dumps(payload), encoding='utf-8')
    files = {path: path.read_bytes() for path in tmp_path.rglob('*.json')}
    with pytest.raises(WorldIdentityMigrationError, match='unsupported save'):
        migrate_legacy_world_ids(tmp_path, tmp_path/'templates/worlds')
    assert all(path.read_bytes() == before for path, before in files.items())


def test_unrelated_future_save_is_refused_before_identity_upgrade(tmp_path):
    _make_fixture(tmp_path)
    future_dir = tmp_path / 'saves' / 'future'
    future_dir.mkdir()
    (future_dir / 'state.json').write_text(json.dumps({
        'instance_schema_version': 999,
        'world_id': 'already_canonical',
    }), encoding='utf-8')
    files = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}

    with pytest.raises(WorldIdentityMigrationError, match='unsupported save'):
        migrate_legacy_world_ids(tmp_path, tmp_path / 'templates/worlds')

    assert all(path.read_bytes() == before for path, before in files.items())
    assert (tmp_path / 'templates' / 'worlds' / f'{OLD_WORLD_ID}.json').is_file()


@pytest.mark.asyncio
async def test_real_cold_start_upgrades_and_recovers_without_dropping_books_or_characters(tmp_path):
    from src.common_factory import create_trpg_subsystems, close_model_clients
    from src.llm.client import ProviderConfig
    from src.engine.modules import content_binding
    _make_fixture(tmp_path)
    subsystem = create_trpg_subsystems(tmp_path, tmp_path/'prompts', tmp_path/'templates/rules',
        tmp_path/'templates/worlds', [ProviderConfig('default', 'https://example.invalid', '', 'test')], 'default')
    try:
        recovered = await subsystem.registry.recover_all()
        assert len(recovered) == 2
        for instance in recovered:
            assert instance.players['alice']['character_name'] == 'Alice'
            assert instance.get_character_sheet('alice')['sanity'] == 40
            assert instance.world_id != OLD_WORLD_ID
            assert OLD_WORLD_ID in instance.game_key[1]
            ref = content_binding.world_ref(instance)
            assert ref['source_id'] == instance.world_id and ref['id'] == instance.world_id
            rows = list_lorebooks(LorebookDependencies(subsystem.lorebook_store, lambda _: None, lambda: None),
                                  world_id=instance.world_id)['books']
            assert rows[0]['ref']['source_id'] == instance.world_id and rows[0]['entry_count'] == 20
    finally:
        await close_model_clients(subsystem)
        subsystem.lorebook_store.close()
        subsystem.memory_store.close()
