from __future__ import annotations

import copy
import json
import sqlite3

import pytest

from src.lorebook.store import SCHEMA
from src.migrations.lorebook import migrate
from src.migrations.world_identity_payload import (
    WorldIdentityError,
    rebind_lorebook_worlds,
    rewrite_references,
)


OLD = "ai_old_world"
NEW = "ai_new_world"
OLD_BOOK = f"world:{OLD}"
NEW_BOOK = f"world:{NEW}"


def test_rewrite_references_changes_only_known_world_identities() -> None:
    value = {
        "world_id": OLD,
        "world_ids": [OLD, "other"],
        "book_id": OLD_BOOK,
        "book_ids": [OLD_BOOK, "user:book"],
        "lorebook_ids": [OLD_BOOK],
        "world_ref": {
            "source_kind": "world", "source_id": OLD,
            "kind": "world", "id": OLD, "digest": "",
        },
        "book_ref": {
            "source": f"world:{OLD}", "kind": "lorebook",
            "id": OLD_BOOK, "digest": "",
        },
        "binding": {"scope_kind": "world", "scope_id": OLD, "book_id": OLD_BOOK},
        "game_key": f"web#{OLD}_123#web_bot",
        "memory_namespace": f"('web', '{OLD}')::run:1",
        "world_name": "Old display name",
        "log": [{"world_id": OLD, "text": "chat stays byte-for-byte semantic"}],
        "entry_ids": [OLD, f"{OLD}_entry"],
        "world_state": {"facts": {"story": {"value": {"world_id": OLD}}}},
        "raw_text": f"world:{OLD}",
    }
    original = copy.deepcopy(value)

    result = rewrite_references(value, {OLD: NEW})

    assert value == original
    assert result["world_id"] == NEW
    assert result["world_ids"] == [NEW, "other"]
    assert result["book_id"] == NEW_BOOK
    assert result["book_ids"] == [NEW_BOOK, "user:book"]
    assert result["lorebook_ids"] == [NEW_BOOK]
    assert result["world_ref"] == {
        "source_kind": "world", "source_id": NEW,
        "kind": "world", "id": NEW, "digest": "",
    }
    assert result["book_ref"] == {
        "source": f"world:{NEW}", "kind": "lorebook",
        "id": NEW_BOOK, "digest": "",
    }
    assert result["binding"] == {
        "scope_kind": "world", "scope_id": NEW, "book_id": NEW_BOOK,
    }
    for key in ("game_key", "memory_namespace", "world_name", "log", "entry_ids", "raw_text", "world_state"):
        assert result[key] == value[key]


def _v4_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO worlds(id, name) VALUES (?, ?)", (OLD, "display"))
    conn.execute(
        "INSERT INTO lorebook_entries(id, world_id, name, content) VALUES (?, ?, ?, ?)",
        ("entry_keep", OLD, "entry", "content"),
    )
    conn.commit()
    migrate(conn, upto=4)
    return conn


def test_rebind_v4_updates_world_ownership_without_renaming_entries() -> None:
    conn = _v4_db()
    try:
        conn.execute("BEGIN")
        rebind_lorebook_worlds(conn, {OLD: NEW})
        assert conn.execute("SELECT id FROM worlds").fetchone()[0] == NEW
        assert tuple(conn.execute("SELECT world_id, id FROM lorebook_entries").fetchone()) == (NEW, "entry_keep")
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'lorebooks'").fetchone()
        conn.rollback()
        assert conn.execute("SELECT id FROM worlds").fetchone()[0] == OLD
    finally:
        conn.close()


def test_rebind_v12_updates_canonical_rows_and_known_json_refs() -> None:
    conn = _v4_db()
    migrate(conn)
    conn.execute(
        "UPDATE lorebooks SET settings_json = ? WHERE id = ?",
        (json.dumps({"world_ref": {"source_kind": "world", "source_id": OLD, "kind": "world", "id": OLD}}), OLD_BOOK),
    )
    conn.execute(
        "UPDATE lorebook_entries SET provenance_json = ? WHERE id = ?",
        (json.dumps({"ref": {"source_kind": "world", "source_id": OLD, "kind": "lorebook", "id": OLD_BOOK}, "entry_id": OLD}), "entry_keep"),
    )
    conn.execute(
        "INSERT INTO lorebook_operations(id, owner, kind, status, payload_json) VALUES (?, ?, ?, ?, ?)",
        ("op", "owner", "game_lorebooks", "applied", json.dumps({
            "book_id": OLD_BOOK,
            "book_ids": [OLD_BOOK],
            "content_binding": {"book_refs": [{"source_kind": "world", "source_id": OLD, "kind": "lorebook", "id": OLD_BOOK}]},
            "game_key": f"web#{OLD}_1#web_bot",
        })),
    )
    conn.commit()
    try:
        conn.execute("BEGIN")
        rebind_lorebook_worlds(conn, {OLD: NEW})
        assert conn.execute("SELECT id FROM worlds").fetchone()[0] == NEW
        assert tuple(conn.execute("SELECT id, book_id, world_id FROM lorebook_entries").fetchone()) == ("entry_keep", NEW_BOOK, NEW)
        assert tuple(conn.execute("SELECT id, source_id FROM lorebooks").fetchone()) == (NEW_BOOK, NEW)
        binding = conn.execute("SELECT id, book_id, scope_id FROM lorebook_bindings").fetchone()
        assert tuple(binding) == (f"binding:{NEW_BOOK}:primary", NEW_BOOK, NEW)
        settings = json.loads(conn.execute("SELECT settings_json FROM lorebooks").fetchone()[0])
        assert settings["world_ref"]["source_id"] == NEW
        provenance = json.loads(conn.execute("SELECT provenance_json FROM lorebook_entries").fetchone()[0])
        assert provenance["ref"]["id"] == NEW_BOOK
        assert provenance["entry_id"] == OLD
        operation = json.loads(conn.execute("SELECT payload_json FROM lorebook_operations").fetchone()[0])
        assert operation["book_id"] == NEW_BOOK
        assert operation["content_binding"]["book_refs"][0]["source_id"] == NEW
        assert operation["game_key"] == f"web#{OLD}_1#web_bot"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.rollback()
        conn.close()

def test_rebind_refuses_conflicts_and_partial_canonical_schema() -> None:
    conn = _v4_db()
    try:
        conn.execute("INSERT INTO worlds(id, name) VALUES (?, ?)", (NEW, "collision"))
        conn.commit()
        conn.execute("BEGIN")
        with pytest.raises(WorldIdentityError, match="target world already exists"):
            rebind_lorebook_worlds(conn, {OLD: NEW})
    finally:
        conn.close()

    partial = sqlite3.connect(":memory:")
    partial.executescript("CREATE TABLE worlds (id TEXT PRIMARY KEY); CREATE TABLE lorebooks (id TEXT PRIMARY KEY);")
    partial.commit()
    try:
        partial.execute("BEGIN")
        with pytest.raises(WorldIdentityError, match="unsupported lorebook schema"):
            rebind_lorebook_worlds(partial, {OLD: NEW})
    finally:
        partial.close()


def test_rebind_skips_mapping_without_a_world_row() -> None:
    conn = _v4_db()
    try:
        conn.execute("BEGIN")
        rebind_lorebook_worlds(conn, {"template_only": "canonical"})
        assert conn.execute("SELECT id FROM worlds").fetchone()[0] == OLD
        assert conn.execute("SELECT world_id FROM lorebook_entries").fetchone()[0] == OLD
    finally:
        conn.rollback()
        conn.close()


def test_missing_legacy_world_cannot_alias_an_existing_target_world():
    conn = _v4_db()
    try:
        conn.execute('BEGIN')
        with pytest.raises(WorldIdentityError, match='target world already exists'):
            rebind_lorebook_worlds(conn, {'missing-legacy': OLD})
    finally:
        conn.close()
