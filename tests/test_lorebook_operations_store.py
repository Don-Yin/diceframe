"""Persistence contracts for owner-private Lorebook operations and snapshots."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest

from src.lorebook.store import LorebookStore


@pytest.fixture()
def store(tmp_path: Path):
    value = LorebookStore(tmp_path / "lorebook.db")
    value.open()
    try:
        yield value
    finally:
        value.close()


def _operation(operation_id: str = "op-1", owner: str = "owner-1") -> dict:
    return {
        "id": operation_id,
        "owner": owner,
        "kind": "entry_delete",
        "status": "prepared",
        "payload": {"before": {"id": "entry-1"}, "after": None},
    }


def _book(store: LorebookStore, book_id: str = "book-1") -> None:
    store.create_lorebook({
        "id": book_id,
        "name": "Book",
        "description": "Description",
        "language": "en",
        "settings": {"locale": "en", "mechanics": "exact"},
    })
    store.bind_lorebook({
        "id": f"binding:{book_id}",
        "book_id": book_id,
        "scope_kind": "world",
        "scope_id": "world-1",
        "role": "custom",
    })
    store.add_entry({
        "id": f"{book_id}-entry",
        "book_id": book_id,
        "name": "Entry",
        "type": "location",
        "keywords": ["key"],
        "content": "author content",
        "visible_to": ["*"],
        "match_mode": "all",
        "extensions_json": json.dumps({"locale": "en"}),
        "provenance_json": json.dumps({"source": "author"}),
    })


def test_operation_history_same_second_uses_insertion_order(store):
    for identity in ("z-first", "a-second"):
        store.record_lorebook_operation({
            **_operation(identity),
            "created_at": "2026-10-14 00:00:00",
            "updated_at": "2026-10-14 00:00:00",
        })
    assert [row["id"] for row in store.list_lorebook_operations("owner-1")] == ["a-second", "z-first"]


def test_failed_journal_commit_does_not_leak_into_next_successful_write(store):
    connection = store._conn

    class FailingCommit:
        def __getattr__(self, key):
            return getattr(connection, key)

        def commit(self):
            raise OSError("commit unavailable")

    store._conn = FailingCommit()
    try:
        with pytest.raises(OSError):
            store.record_lorebook_operation(_operation("failed"))
    finally:
        store._conn = connection
    store.record_lorebook_operation(_operation("success"))
    assert store.get_lorebook_operation("failed", "owner-1") is None


def test_operations_are_owner_private_insert_only_and_persist_after_restart(tmp_path: Path):
    path = tmp_path / "lorebook.db"
    store = LorebookStore(path)
    store.open()
    store.record_lorebook_operation(_operation())
    assert store.get_lorebook_operation("op-1", "owner-1")["payload"]["before"]["id"] == "entry-1"
    assert store.get_lorebook_operation("op-1", "other-owner") is None
    assert [row["id"] for row in store.list_lorebook_operations("owner-1")] == ["op-1"]
    with pytest.raises(sqlite3.IntegrityError):
        store.record_lorebook_operation(_operation())
    assert store.update_lorebook_operation("op-1", "owner-1", {"status": "applied"}) is True
    assert store.update_lorebook_operation("op-1", "other-owner", {"status": "undone"}) is False
    assert store.get_lorebook_operation("op-1", "owner-1")["status"] == "applied"
    store.close()

    reopened = LorebookStore(path)
    reopened.open()
    try:
        assert reopened.get_lorebook_operation("op-1", "owner-1")["status"] == "applied"
    finally:
        reopened.close()


def test_v9_to_v10_migration_preserves_books_entries_and_adds_operation_table(tmp_path: Path):
    path = tmp_path / "lorebook.db"
    store = LorebookStore(path)
    store.open()
    _book(store)
    before = store.snapshot_lorebook("book-1")
    store.close()

    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE lorebook_operations")
    conn.execute("PRAGMA user_version = 9")
    conn.commit()
    conn.close()

    migrated = LorebookStore(path)
    migrated.open()
    try:
        assert migrated._conn.execute("PRAGMA user_version").fetchone()[0] == 12
        assert migrated.snapshot_lorebook("book-1") == before
        assert migrated._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='lorebook_operations'"
        ).fetchone() is not None
    finally:
        migrated.close()


def test_lorebook_snapshot_restore_is_exact_and_bumps_revision(store: LorebookStore):
    _book(store)
    snapshot = store.snapshot_lorebook("book-1")
    assert snapshot is not None
    original_revision = int(snapshot["book"]["revision"])
    store.delete_lorebook("book-1")

    store.restore_lorebook_snapshot(snapshot)

    restored = store.snapshot_lorebook("book-1")
    assert restored is not None
    assert restored["book"]["name"] == snapshot["book"]["name"]
    assert restored["book"]["settings_json"] == snapshot["book"]["settings_json"]
    assert restored["book"]["revision"] >= original_revision + 1
    restored_book = dict(restored["book"])
    restored_book.pop("revision")
    expected_book = dict(snapshot["book"])
    expected_book.pop("revision")
    assert restored_book == expected_book
    assert restored["entries"] == snapshot["entries"]
    assert restored["bindings"] == snapshot["bindings"]


def test_restore_fails_closed_on_book_and_entry_identity_collisions(store: LorebookStore):
    _book(store, "book-a")
    snapshot = store.snapshot_lorebook("book-a")
    assert snapshot is not None
    with pytest.raises(ValueError):
        store.restore_lorebook_snapshot(snapshot)

    entry_snapshot = snapshot["entries"][0]
    _book(store, "book-b")
    with pytest.raises(ValueError):
        store.restore_lorebook_entry("book-b", entry_snapshot)
    assert store.get_lorebook("book-b") is not None
    assert store.get_entry("book-b-entry") is not None


def test_operation_failure_rolls_back_content_in_same_transaction(store: LorebookStore):
    store.record_lorebook_operation(_operation())
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction():
            store.create_lorebook({"id": "rolled-back", "name": "Rollback"})
            store.record_lorebook_operation(_operation())
    assert store.get_lorebook("rolled-back") is None
    assert store.get_lorebook_operation("op-1", "owner-1")["status"] == "prepared"


def test_snapshot_restore_fault_rolls_back_every_insert(store: LorebookStore, monkeypatch):
    _book(store)
    snapshot = store.snapshot_lorebook("book-1")
    assert snapshot is not None
    store.delete_lorebook("book-1")

    original_insert = store._insert_fixed_row_locked
    calls = 0

    def fail_after_book(table, columns, row):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected restore failure")
        return original_insert(table, columns, row)

    monkeypatch.setattr(store, "_insert_fixed_row_locked", fail_after_book)
    with pytest.raises(RuntimeError, match="injected restore failure"):
        store.restore_lorebook_snapshot(snapshot)
    assert store.snapshot_lorebook("book-1") is None


def test_explicit_transaction_blocks_other_threads_until_commit(store: LorebookStore):
    store.create_lorebook({"id": "threaded", "name": "Before"})
    entered = threading.Event()
    release = threading.Event()
    reader_done = threading.Event()
    observed: list[str] = []

    def writer() -> None:
        with store.transaction():
            store.update_lorebook("threaded", {"name": "After"})
            entered.set()
            release.wait(timeout=2)

    def reader() -> None:
        entered.wait(timeout=2)
        observed.append(store.get_lorebook("threaded")["name"])
        reader_done.set()

    writer_thread = threading.Thread(target=writer)
    reader_thread = threading.Thread(target=reader)
    writer_thread.start()
    assert entered.wait(timeout=2)
    reader_thread.start()
    assert not reader_done.wait(timeout=0.05)
    release.set()
    writer_thread.join(timeout=2)
    reader_thread.join(timeout=2)
    assert observed == ["After"]
