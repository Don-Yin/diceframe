from copy import deepcopy

import pytest

from src.lorebook.store import LorebookStore
from src.webui.services.assistant_agent import _digest
from src.webui.services.assistant_authoring import AuthoringDependencies, authoring_tools
from src.webui.services.content_recovery import ContentRecoveryDependencies, ContentRecoveryService
from src.webui.services.lorebooks import LorebookDependencies, save_lorebook_entry


def _service(tmp_path, *, save_override=None):
    store = LorebookStore(tmp_path / "lorebook.db")
    store.open()
    store.create_lorebook({"id": "book", "name": "Book", "source_kind": "user"})
    lore = LorebookDependencies(store, lambda _: None, lambda: None)
    save = save_override or (lambda book, row: save_lorebook_entry(lore, book, row))
    recovery = ContentRecoveryService(ContentRecoveryDependencies(
        store=store, list_games=lambda: {"games": []}, get_game=lambda key: None,
        world_definition=lambda world_id: {"world": {"source": "user", "editable": True}},
        save_entry=save,
    ))
    return store, recovery


def _digest_entries(store):
    return _digest(store.list_book_entries("book"))


def _rows(count=35, *, visible_to=None):
    return [{"id": f"e-{index}", "name": f"Entry {index}", "content": f"Text {index}",
             "type": "other", "keywords": [f"k-{index}"], "visible_to": list(visible_to or [])}
            for index in range(count)]


def _without_update_time(rows):
    return [{key: value for key, value in row.items() if key != 'updated_at'} for row in rows]


def test_real_sqlite_book_visibility_batches_and_undo_preserve_all_fields(tmp_path):
    store, recovery = _service(tmp_path)
    try:
        for row in _rows():
            assert recovery.deps.save_entry("book", row)["ok"]
        before = deepcopy(store.list_book_entries("book"))
        result = recovery.write_book_visibility("owner", "book",
                                                [{"id": row["id"], "visible_to": ["*"]} for row in before],
                                                _digest_entries(store))
        assert result["ok"] and len(result["operation_ids"]) == 3
        assert all(row["visible_to"] == ["*"] for row in store.list_book_entries("book"))
        assert [{**row, 'visible_to': before[index]['visible_to']}
                for index, row in enumerate(_without_update_time(store.list_book_entries('book')))] == _without_update_time(before)
        for operation_id in reversed(result["operation_ids"]):
            assert recovery.undo("owner", operation_id)["ok"]
        assert _without_update_time(store.list_book_entries("book")) == _without_update_time(before)
    finally:
        store.close()


def test_book_visibility_rejects_stale_or_new_entries_and_repeated_value_is_noop(tmp_path):
    store, recovery = _service(tmp_path)
    try:
        for row in _rows(2):
            recovery.deps.save_entry("book", row)
        digest = _digest_entries(store)
        assert recovery.write_book_visibility("owner", "book", [{"id": "e-0", "visible_to": []}], digest)["operation_ids"] == []
        with pytest.raises(ValueError):
            recovery.write_book_visibility("owner", "book", [{"id": "e-0", "visible_to": ["*"]}], "sha256:stale")
        with pytest.raises(ValueError, match="既有|不存在|完整"):
            recovery.write_book_visibility("owner", "book", [{"id": "new", "visible_to": ["*"]}], digest)
    finally:
        store.close()


def test_book_visibility_private_marker_and_second_batch_failure_roll_back_everything(tmp_path):
    calls = []
    store, recovery = _service(tmp_path)
    try:
        for row in _rows(35):
            recovery.deps.save_entry("book", row)
        original = deepcopy(store.list_book_entries("book"))
        # A failing owner save in the second batch must roll back the first
        # batch and its prepared journal rows too.
        real_update = store.update_book_entry
        def fail_second(book, entry_id, patch):
            calls.append(entry_id)
            if len(calls) == 18:
                return False
            return real_update(book, entry_id, patch)
        store.update_book_entry = fail_second
        with pytest.raises(ValueError):
            recovery.write_book_visibility("owner", "book",
                                           [{"id": row["id"], "visible_to": ["*"]} for row in original],
                                           _digest_entries(store))
        assert store.list_book_entries("book") == original
        assert recovery.list_operations("owner")["operations"] == []
    finally:
        store.close()


def test_visibility_undo_rejects_binding_changes(tmp_path):
    store, recovery = _service(tmp_path)
    try:
        recovery.deps.save_entry("book", _rows(1)[0])
        result = recovery.write_book_visibility("owner", "book",
                                                [{"id": "e-0", "visible_to": ["*"]}],
                                                _digest_entries(store))
        store.bind_lorebook({"id": "binding-1", "book_id": "book", "scope_kind": "global", "scope_id": ""})
        with pytest.raises(ValueError):
            recovery.undo("owner", result["operation_ids"][0])
    finally:
        store.close()


def test_authoring_registers_whole_book_visibility_only_with_recovery_callback():
    callback = lambda owner, book_id, rows, digest, **kwargs: {"ok": True, "operation_ids": []}
    preview = lambda owner, book_id, rows, digest: {"target_name": "Book", "total": 0,
                                                     "changed_count": 0, "batch_count": 0,
                                                     "affected_games": ["game-1"]}
    snapshot = lambda book_id: {"book": {"id": book_id}, "entries": [], "bindings": []}
    receipt = lambda owner, operation_id: None
    deps = AuthoringDependencies(
        list_worlds=lambda: {"worlds": []}, update_world=lambda *args: {},
        list_book_entries=lambda book: {"ok": True, "book": {"name": "Book"}, "entries": []},
        save_book_entry=lambda *args: {"ok": True}, list_cards=lambda: {"cards": []},
        update_card=lambda *args: {}, adventure_detail=lambda *args: {}, get_rule=lambda *args: {},
        write_book_visibility_with_recovery=callback,
        preview_book_visibility_with_recovery=preview,
        book_snapshot=snapshot,
        book_visibility_receipt=receipt,
    )
    tool = next(item for item in authoring_tools(deps) if item.name == "set_lorebook_visibility")
    assert tool.effect == "disclosure" and tool.version == 3 and not tool.automatic
    assert callable(tool.prepare) and callable(tool.execute) and tool.resumable
    assert set(tool.schema["properties"]) == {"book_id", "audience", "game_key", "character_ids"}
    summary = tool.preview({"book_id": "book", "audience": "public"}, "owner")
    assert summary["affected_games"] == ["game-1"]
    assert summary["changed_count"] == 0


@pytest.mark.asyncio
async def test_whole_visibility_previews_private_entries_before_owner_write():
    writes = []
    deps = AuthoringDependencies(
        list_worlds=lambda: {"worlds": []}, update_world=lambda *args: {},
        list_book_entries=lambda book: {"ok": True, "book": {"name": "Book"},
                                        "entries": [{"id": "e1", "content": "GM: secret", "visible_to": []}]},
        save_book_entry=lambda *args: {"ok": True}, list_cards=lambda: {"cards": []},
        update_card=lambda *args: {}, adventure_detail=lambda *args: {}, get_rule=lambda *args: {},
        write_book_visibility_with_recovery=lambda *args: writes.append(args) or {"ok": True},
    )
    tool = next(item for item in authoring_tools(deps) if item.name == "set_lorebook_visibility")
    with pytest.raises(ValueError, match="private"):
        tool.preview({"book_id": "book", "audience": "public"}, "owner")
    with pytest.raises(ValueError, match="private"):
        await tool.handler({"book_id": "book", "audience": "public"}, "owner")
    assert writes == []


@pytest.mark.parametrize('patch', [
    {'id': 'e-0', 'name': 'Unexpected'},
    {'id': 'new', 'visible_to': ['*']},
    {'id': 'e-0', 'visible_to': ['']},
])
def test_visibility_marker_only_supports_existing_audience_patches(tmp_path, patch):
    store, recovery = _service(tmp_path)
    try:
        recovery.deps.save_entry('book', _rows(1)[0])
        before = store.list_book_entries('book')
        with pytest.raises(ValueError):
            recovery.write_entries('owner', 'book', [patch], _visibility_only=True)
        assert store.list_book_entries('book') == before
    finally:
        store.close()


def test_visibility_noop_still_requires_owner_and_existing_book(tmp_path):
    store, recovery = _service(tmp_path)
    try:
        with pytest.raises(PermissionError):
            recovery.write_book_visibility('', 'book', [], _digest_entries(store))
        with pytest.raises(ValueError):
            recovery.write_book_visibility('owner', 'missing', [], _digest([]))
        assert recovery.write_book_visibility('owner', 'book', [], _digest_entries(store))['operation_ids'] == []
        assert recovery.list_operations('owner')['operations'] == []
    finally:
        store.close()


def test_snapshot_limit_rolls_back_earlier_visibility_batches(tmp_path):
    store, recovery = _service(tmp_path)
    try:
        for row in _rows(35):
            if row['id'] == 'e-20':
                row['content'] = 'Large text ' * 60000
            recovery.deps.save_entry('book', row)
        before = store.list_book_entries('book')
        with pytest.raises(ValueError, match='快照'):
            recovery.write_book_visibility('owner', 'book',
                [{'id': row['id'], 'visible_to': ['*']} for row in before], _digest_entries(store))
        assert store.list_book_entries('book') == before
        assert recovery.list_operations('owner')['operations'] == []
    finally:
        store.close()


def test_visibility_snapshot_budget_reserves_space_for_undo(tmp_path):
    store, recovery = _service(tmp_path)
    try:
        for row in _rows(16):
            row['content'] = 'x' * 13000
            recovery.deps.save_entry('book', row)
        before = store.list_book_entries('book')
        # Before/after alone fit the cap, but the recovery receipt would not.
        # Refuse this batch atomically rather than issuing an unusable undo ID.
        with pytest.raises(ValueError, match='快照'):
            recovery.write_book_visibility('owner', 'book',
                [{'id': row['id'], 'visible_to': ['*']} for row in before], _digest_entries(store))
        assert store.list_book_entries('book') == before
        assert recovery.list_operations('owner')['operations'] == []
    finally:
        store.close()
