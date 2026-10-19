from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from src.lorebook.store import LorebookStore
from src.webui.services.assistant_agent import _digest
from src.webui.services.content_recovery import ContentRecoveryDependencies, ContentRecoveryService
from src.webui.services.lorebooks import LorebookDependencies, save_lorebook_entry
from src.webui.services.lorebook_visibility_plans import (
    LorebookVisibilityPlanDependencies,
    LorebookVisibilityPlans,
)
from src.application_action_execution import ActionExecutionContext


def _service(tmp_path):
    store = LorebookStore(tmp_path / "lorebook.db")
    store.open()
    store.create_lorebook({"id": "book", "name": "Book", "source_kind": "user"})
    lore = LorebookDependencies(store, lambda _: None, lambda: None)
    return store, ContentRecoveryService(ContentRecoveryDependencies(
        store=store, list_games=lambda: {"games": []}, get_game=lambda _key: None,
        world_definition=lambda _world_id: {"world": {"source": "user", "editable": True}},
        save_entry=lambda book, row: save_lorebook_entry(lore, book, row),
    ))


def test_visibility_group_receipt_replays_without_touching_changed_content(tmp_path):
    store, recovery = _service(tmp_path)
    try:
        recovery.deps.save_entry("book", {"id": "e1", "name": "Entry", "content": "before", "visible_to": []})
        digest = _digest(store.list_book_entries("book"))
        rows = [{"id": "e1", "visible_to": ["*"]}]
        result = recovery.write_book_visibility("owner", "book", rows, digest, operation_id="a" * 32)
        assert result["operation_id"] == "a" * 32
        store.update_book_entry("book", "e1", {"content": "later"})
        replay = recovery.write_book_visibility("owner", "book", rows, digest, operation_id="a" * 32)
        assert replay == result
        assert store.get_book_entry("book", "e1")["content"] == "later"
        assert recovery.read_book_visibility_receipt("owner", "a" * 32) == result
        assert all(item["kind"] != "visibility_plan_book"
                   for item in recovery.list_operations("owner")["operations"])
        with pytest.raises(ValueError, match="does not match|不匹配"):
            recovery.write_book_visibility("owner", "book", [{"id": "e1", "visible_to": []}], digest,
                                           operation_id="a" * 32)
    finally:
        store.close()


def test_fulltext_write_digest_fence_rolls_back_stale_request_and_allows_fresh_one(tmp_path):
    store, recovery = _service(tmp_path)
    try:
        recovery.deps.save_entry("book", {
            "id": "e1", "name": "Entry", "content": "before", "visible_to": [],
        })
        stale_digest = _digest(store.list_book_entries("book"))
        store.update_book_entry("book", "e1", {"content": "concurrent"})
        before = deepcopy(store.list_book_entries("book"))
        with pytest.raises(ValueError, match="变化|digest"):
            recovery.write_entries(
                "owner", "book", [{"id": "e1", "content": "planned", "visible_to": []}],
                expected_entries_digest=stale_digest,
            )
        assert store.list_book_entries("book") == before
        assert recovery.list_operations("owner")["operations"] == []

        fresh_digest = _digest(before)
        result = recovery.write_entries(
            "owner", "book", [{"id": "e1", "content": "planned", "visible_to": []}],
            expected_entries_digest=fresh_digest,
        )
        assert result["ok"] is True
        assert store.get_book_entry("book", "e1")["content"] == "planned"
    finally:
        store.close()


def test_visibility_plan_executes_against_sqlite_and_reports_child_receipt_ids(tmp_path):
    store, recovery = _service(tmp_path)
    try:
        store.create_lorebook({"id": "book-2", "name": "Book Two", "source_kind": "user"})
        recovery.deps.save_entry("book", {"id": "e1", "name": "One", "content": "one", "visible_to": []})
        recovery.deps.save_entry("book-2", {"id": "e2", "name": "Two", "content": "two", "visible_to": []})
        deps = LorebookVisibilityPlanDependencies(
            list_entries=lambda book_id: {"ok": True,
                                          "book": store.snapshot_lorebook(book_id)["book"],
                                          "entries": store.list_book_entries(book_id)},
            snapshot=store.snapshot_lorebook,
            preview=lambda owner, book_id, rows, digest: recovery.preview_book_visibility(
                owner, book_id, rows, digest),
            write=lambda owner, book_id, rows, digest, *, operation_id: recovery.write_book_visibility(
                owner, book_id, rows, digest, operation_id=operation_id),
            receipt=recovery.read_book_visibility_receipt,
            game_players=lambda game_key, owner: {"players": {}},
        )
        service = LorebookVisibilityPlans(deps)
        prepared = service.prepare({"book_ids": ["book", "book-2"], "audience": "public"}, "owner")
        persisted = []
        context = ActionExecutionContext("plan-sqlite", {}, persisted.append, lambda: None)
        report = asyncio.run(service.execute(prepared.payload, "owner", context))
        assert report["status"] == "completed"
        assert all(row["operation_ids"] for row in report["books"])
        assert all(len(row["operation_ids"][0]) == 32 for row in report["books"])
        assert all(row["visible_to"] == ["*"] for row in store.list_book_entries("book"))
        assert all(row["visible_to"] == ["*"] for row in store.list_book_entries("book-2"))
    finally:
        store.close()


def test_visibility_plan_retries_transactional_second_book_and_skips_first(tmp_path):
    store, recovery = _service(tmp_path)
    try:
        store.create_lorebook({"id": "book-2", "name": "Book Two", "source_kind": "user"})
        recovery.deps.save_entry("book", {"id": "e1", "name": "One", "content": "one", "visible_to": []})
        recovery.deps.save_entry("book-2", {"id": "e2", "name": "Two", "content": "two", "visible_to": []})
        deps = LorebookVisibilityPlanDependencies(
            list_entries=lambda book_id: {"ok": True,
                                          "book": store.snapshot_lorebook(book_id)["book"],
                                          "entries": store.list_book_entries(book_id)},
            snapshot=store.snapshot_lorebook,
            preview=lambda owner, book_id, rows, digest: recovery.preview_book_visibility(
                owner, book_id, rows, digest),
            write=lambda owner, book_id, rows, digest, *, operation_id: recovery.write_book_visibility(
                owner, book_id, rows, digest, operation_id=operation_id),
            receipt=recovery.read_book_visibility_receipt,
            game_players=lambda game_key, owner: {"players": {}},
        )
        service = LorebookVisibilityPlans(deps)
        prepared = service.prepare({"book_ids": ["book", "book-2"], "audience": "public"}, "owner")
        original_update = store.update_book_entry
        failed = [False]

        def fail_once(book_id, entry_id, patch):
            if book_id == "book-2" and not failed[0]:
                failed[0] = True
                return False
            return original_update(book_id, entry_id, patch)

        store.update_book_entry = fail_once
        context = ActionExecutionContext("plan-retry", {}, lambda state: None, lambda: None)
        first = asyncio.run(service.execute(prepared.payload, "owner", context))
        assert first["status"] == "partial"
        assert first["success_count"] == 1 and first["failed_count"] == 1
        assert store.get_book_entry("book", "e1")["visible_to"] == ["*"]
        assert store.get_book_entry("book-2", "e2")["visible_to"] == []

        store.update_book_entry = original_update
        second = asyncio.run(service.execute(prepared.payload, "owner", context))
        assert second["status"] == "completed"
        assert second["success_count"] == 2
        assert store.get_book_entry("book-2", "e2")["visible_to"] == ["*"]
    finally:
        store.close()
