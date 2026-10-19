"""Prove that the two published schema sequences are never conflated."""

from copy import deepcopy
import sqlite3

import pytest

from src.migrations.instance import CURRENT_INSTANCE_SCHEMA_VERSION, migrate_game_state_payload
from src.migrations import lorebook
from src.migrations.sqlite import MigrationError, table_columns
from src.lorebook.store import SCHEMA


def local_save(version=38):
    payload = {
        "instance_schema_version": version,
        "world_id": "harbor",
        "scene": "A public harbor scene",
        "play_mode": "free",
        "adventure_progress": {"visited": ["pier"]},
        "modules": {
            "ai_seats": {
                "schema_version": 1, "revision": 2, "defaults_revision": 2,
                "seat_revisions": {}, "seats": {}, "outcomes": {},
                "defaults": {"provider_ref": "local", "model": "test", "style": "bold"},
            },
            "room_access": {
                "schema_version": 1, "max_players": 4, "player_access_open": True,
                "bot_bind_token": "", "room_password": "room-example",
                "room_token": "token-example",
            },
            "checks": {
                "schema_version": 1, "last_check": None,
                "last_checks": [{"check_id": "pending", "push": {"status": "offered"}}],
                "round_checks_prepared": True, "manual_roll_requests": [],
            },
        },
    }
    if version >= 37:
        payload["modules"]["check_modes"] = {
            "schema_version": 1, "revision": 3,
            "seats": {"pc": {"run_id": "old", "context_id": "narrative", "grant": None}},
        }
    return payload


@pytest.mark.parametrize("version", [36, 37, 38])
def test_local_save_uses_main_migrations_without_losing_local_policy(version):
    original = local_save(version)
    before = deepcopy(original)
    upgraded = migrate_game_state_payload(original)
    assert original == before
    assert upgraded["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    modules = upgraded["modules"]
    assert modules["room_access"]["schema_version"] == 3
    assert "room_password" not in modules["room_access"]
    assert "room_token" not in modules["room_access"]
    assert modules["room_access"]["room_password_hash"]
    assert modules["content_binding"]["world_ref"]["id"] == "harbor"
    assert modules["narrative_notes"]["scene"] == before["scene"]
    assert modules["adventure_runtime"]["progress"] == before["adventure_progress"]
    assert modules["ai_seats"] == before["modules"]["ai_seats"]
    assert modules["checks"] == before["modules"]["checks"]
    if version >= 37:
        assert modules["check_modes"] == before["modules"]["check_modes"]
    assert migrate_game_state_payload(upgraded) == upgraded


def test_unknown_local_variant_is_rejected_without_mutating_the_save():
    original = local_save()
    original["modules"]["ai_seats"]["schema_version"] = 99
    before = deepcopy(original)
    with pytest.raises(ValueError, match="local"):
        migrate_game_state_payload(original)
    assert original == before


def test_main_save_also_gets_the_new_reader_fence_without_overwriting_slots():
    original = {"instance_schema_version": 43, "modules": {"ai_seats": {"schema_version": 99}}}
    upgraded = migrate_game_state_payload(original)
    assert upgraded["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert upgraded["modules"]["ai_seats"] == original["modules"]["ai_seats"]
    assert upgraded["modules"]["check_modes"]["seats"] == {}


LOCAL_OPERATIONS_SQL = """
CREATE TABLE lorebook_operations (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('prepared','applied','undone','restored')),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def base_database():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    return conn


def local_database():
    conn = base_database()
    lorebook.migrate(conn, upto=9)
    conn.execute(LOCAL_OPERATIONS_SQL)
    conn.execute("INSERT INTO lorebook_operations(id, owner, kind, status, payload_json) VALUES (?, ?, ?, ?, ?)",
                 ("undo-1", "owner", "delete", "applied", '{"original":"retained"}'))
    conn.execute("INSERT INTO lorebooks(id, name, source_kind, source_id) VALUES (?, ?, ?, ?)",
                 ("private-book", "Private notes", "user", "owner"))
    conn.execute("PRAGMA user_version = 10")
    conn.commit()
    return conn


def test_local_lorebook_v10_preserves_books_and_undo_records_and_adds_main_identity():
    conn = local_database()
    try:
        book = conn.execute("SELECT id, name, source_kind, source_id FROM lorebooks").fetchall()
        journal = conn.execute("SELECT * FROM lorebook_operations").fetchall()
        assert lorebook.migrate(conn) == 12
        assert {"external_id", "import_link", "import_state_digest"} <= table_columns(conn, "lorebooks")
        assert conn.execute("SELECT id, name, source_kind, source_id FROM lorebooks").fetchall() == book
        assert conn.execute("SELECT * FROM lorebook_operations").fetchall() == journal
        assert lorebook.migrate(conn) == 12
    finally:
        conn.close()


@pytest.mark.parametrize("version", [9, 10, 11])
def test_main_lorebook_versions_follow_their_own_sequence(version):
    conn = base_database()
    try:
        lorebook.migrate(conn, upto=version)
        assert lorebook.migrate(conn) == 12
        assert "external_id" in table_columns(conn, "lorebooks")
        assert "payload_json" in table_columns(conn, "lorebook_operations")
    finally:
        conn.close()


def test_unknown_v10_shape_is_rejected_atomically():
    conn = base_database()
    try:
        lorebook.migrate(conn, upto=9)
        conn.execute("CREATE TABLE lorebook_operations (unexpected TEXT)")
        conn.execute("PRAGMA user_version = 10")
        conn.commit()
        with pytest.raises(MigrationError):
            lorebook.migrate(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
        assert "external_id" not in table_columns(conn, "lorebooks")
        assert table_columns(conn, "lorebook_operations") == {"unexpected"}
    finally:
        conn.close()
