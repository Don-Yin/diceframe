import pytest

from src.lorebook.store import LorebookStore
from src.webui.services.content_recovery import ContentRecoveryDependencies, ContentRecoveryService


@pytest.fixture
def recovery(tmp_path):
    store = LorebookStore(tmp_path / 'lorebook.db')
    store.open()
    store.create_lorebook({'id': 'mine', 'name': 'My book', 'source_kind': 'user'})
    store.add_book_entry('mine', {'id': 'note', 'name': 'Note', 'content': 'Original', 'visible_to': []})
    from src.webui.services.lorebooks import LorebookDependencies, save_lorebook_entry
    dependencies = LorebookDependencies(store, lambda _: None, lambda: None)
    service = ContentRecoveryService(ContentRecoveryDependencies(
        store=store, list_games=lambda: {'games': []}, get_game=lambda _: None,
        world_definition=lambda _: {'ok': True, 'world': {'source': 'builtin', 'editable': False}},
        save_entry=lambda book, row: save_lorebook_entry(dependencies, book, row),
    ))
    yield service, store
    store.close()


def test_confirmed_entry_edit_can_undo_without_exposing_snapshots(recovery):
    service, store = recovery
    result = service.write_entries('owner', 'mine', [{'id': 'note', 'name': 'Wrong', 'content': 'GM: Private mistake'}])
    operation_id = result['operation_id']
    summary = service.list_operations('owner')['operations'][0]
    assert summary['operation_id'] == operation_id and summary['can_undo']
    assert 'Private mistake' not in str(summary)
    assert service.list_operations('another')['operations'] == []
    service.undo('owner', operation_id)
    assert store.get_book_entry('mine', 'note')['content'] == 'Original'
    assert store.get_book_entry('mine', 'note')['visible_to'] == []


def test_undo_rejects_later_edits_and_cannot_use_another_owner_operation(recovery):
    service, store = recovery
    result = service.write_entries('owner', 'mine', [{'id': 'note', 'name': 'Note', 'content': 'Mistake'}])
    store.update_book_entry('mine', 'note', {'content': 'Later human edit'})
    with pytest.raises(ValueError): service.undo('owner', result['operation_id'])
    with pytest.raises(ValueError): service.undo('another', result['operation_id'])
    assert store.get_book_entry('mine', 'note')['content'] == 'Later human edit'


def test_archive_and_restore_entries_preserve_identity_and_private_visibility(recovery):
    service, store = recovery
    original = store.get_book_entry('mine', 'note')
    result = service.archive_entries('owner', 'mine', ['note'])
    assert store.get_book_entry('mine', 'note') is None
    assert service.list_operations('owner')['operations'][0]['can_restore']
    service.restore('owner', result['operation_id'])
    restored = store.get_book_entry('mine', 'note')
    assert {key: restored[key] for key in ('id', 'book_id', 'content', 'visible_to')} == {key: original[key] for key in ('id', 'book_id', 'content', 'visible_to')}


def test_primary_book_archive_and_builtin_entry_archive_are_rejected(recovery):
    service, store = recovery
    store.create_world('builtin', 'Builtin')
    store.add_book_entry('world:builtin', {'id': 'builtin-note', 'name': 'Builtin note', 'content': 'System'})
    with pytest.raises(ValueError): service.archive_book('owner', 'world:builtin')
    with pytest.raises(ValueError): service.archive_entries('owner', 'world:builtin', ['builtin-note'])
    assert store.get_book_entry('world:builtin', 'builtin-note')


def test_authored_book_with_plugin_source_entries_cannot_archive_source_content(recovery):
    service, store = recovery
    store.add_book_entry('mine', {'id': 'plugin-note', 'name': 'Plugin source', 'content': 'Source', 'source_plugin': 'plugin-source'})
    with pytest.raises(ValueError, match='插件'):
        service.archive_book('owner', 'mine')
    assert store.get_book_entry('mine', 'note')


def test_batch_and_cross_book_targets_are_explicit_and_bounded(recovery):
    service, store = recovery
    with pytest.raises(ValueError): service.archive_entries('owner', 'mine', ['note', 'note'])
    with pytest.raises(ValueError): service.archive_entries('owner', 'mine', ['*'])
    with pytest.raises(ValueError): service.archive_entries('owner', 'mine', [str(i) for i in range(11)])
    assert store.get_book_entry('mine', 'note')


def test_active_bindings_block_whole_book_archive_but_entry_disable_is_reversible(recovery):
    service, store = recovery
    store.bind_lorebook({'id': 'live', 'book_id': 'mine', 'scope_kind': 'game', 'scope_id': 'g1', 'role': 'runtime'})
    with pytest.raises(ValueError): service.archive_book('owner', 'mine')
    result = service.set_entries_enabled('owner', 'mine', ['note'], False)
    assert store.get_book_entry('mine', 'note')['enabled'] is False
    service.undo('owner', result['operation_id'])
    assert store.get_book_entry('mine', 'note')['enabled'] is True


def test_journal_failure_refuses_content_write(recovery, monkeypatch):
    service, store = recovery
    def fail(_): raise OSError('journal unavailable')
    monkeypatch.setattr(store, 'record_lorebook_operation', fail)
    with pytest.raises(OSError): service.write_entries('owner', 'mine', [{'id': 'note', 'name': 'Note', 'content': 'Wrong'}])
    assert store.get_book_entry('mine', 'note')['content'] == 'Original'


def test_failed_sql_commit_rolls_back_before_any_later_write(recovery):
    service, store = recovery
    connection = store._conn
    class FailingCommit:
        def __getattr__(self, key): return getattr(connection, key)
        def commit(self): raise OSError('commit unavailable')
    store._conn = FailingCommit()
    try:
        with pytest.raises(OSError): service.set_book_enabled('owner', 'mine', False)
        assert store.get_lorebook('mine')['enabled'] is True
        assert service.list_operations('owner')['operations'] == []
    finally:
        store._conn = connection
    store.update_book_entry('mine', 'note', {'content': 'Later'})
    assert store.get_lorebook('mine')['enabled'] is True


def test_archive_can_restore_private_entry_after_store_restart(recovery):
    from dataclasses import replace
    service, store = recovery
    archived = service.archive_entries('owner', 'mine', ['note'])
    store.close()
    store.open()
    restarted_service = ContentRecoveryService(replace(service.deps, store=store))
    assert restarted_service.list_operations('owner')['operations'][0]['can_restore']
    restarted_service.restore('owner', archived['operation_id'])
    restored = store.get_book_entry('mine', 'note')
    assert restored['id'] == 'note' and restored['content'] == 'Original' and restored['visible_to'] == []
