"""Narrow, transaction-owned rewrites for legacy world identities.

This module only knows persistence contracts that already exist in the game and
Lorebook schemas.  It deliberately does not derive or invent a replacement
identity, rename game keys, or rewrite opaque user content.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from src.engine.world.contracts import canonical_id


class WorldIdentityError(ValueError):
    """The persisted world identity cannot be rebound safely."""


_WORLD_VALUE_KEYS = frozenset({"world_id"})
_WORLD_LIST_KEYS = frozenset({"world_ids"})
_BOOK_VALUE_KEYS = frozenset({"book_id", "lorebook_id"})
_BOOK_LIST_KEYS = frozenset({"book_ids", "bookids", "lorebook_ids"})
_PROTECTED_KEYS = frozenset({
    "game_key", "memory_namespace", "world_name", "log", "chatlog", "entry_ids", "world_state",
})


def _parts(mapping: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    if not isinstance(mapping, Mapping) or not mapping:
        raise WorldIdentityError("world identity mapping must be a non-empty object")
    worlds: dict[str, str] = {}
    books: dict[str, str] = {}
    for old_raw, new_raw in mapping.items():
        old = str(old_raw)
        new = str(new_raw)
        if not old or not new or old == new:
            raise WorldIdentityError("world identity mapping contains an invalid or no-op pair")
        try:
            canonical_id(new, field="replacement world id")
        except ValueError as exc:
            raise WorldIdentityError(str(exc)) from exc
        if new in worlds.values():
            raise WorldIdentityError("multiple legacy worlds target one canonical world")
        worlds[old] = new
        books[f"world:{old}"] = f"world:{new}"
    return worlds, books


def _mapped(value: Any, worlds: Mapping[str, str]) -> Any:
    return worlds.get(value, value) if isinstance(value, str) else value


def _mapped_book(value: Any, books: Mapping[str, str]) -> Any:
    return books.get(value, value) if isinstance(value, str) else value


def rewrite_references(value: Any, mapping: Mapping[str, str]) -> Any:
    """Copy ``value`` while rewriting known world/book identity fields.

    The walk is intentionally conservative.  Generic ``id`` fields, game
    keys, memory namespaces, display text, logs, and lore entry identities are
    opaque and stay unchanged.  A ``source_id`` or ``id`` is rewritten only
    when its sibling fields prove it is a World ContentRef.
    """

    worlds, books = _parts(mapping)

    def visit(node: Any) -> Any:
        if isinstance(node, list):
            return [visit(item) for item in node]
        if not isinstance(node, dict):
            return copy.deepcopy(node)

        source_kind = node.get("source_kind")
        source = node.get("source")
        source_world_id = None
        if source_kind == "world" and isinstance(node.get("source_id"), str):
            source_world_id = node["source_id"]
        elif isinstance(source, str) and source.startswith("world:"):
            source_world_id = source.partition(":")[2]
        kind = node.get("kind")

        result: dict[str, Any] = {}
        for key, raw in node.items():
            if key in _PROTECTED_KEYS:
                result[key] = copy.deepcopy(raw)
                continue
            if key in _WORLD_VALUE_KEYS:
                result[key] = _mapped(raw, worlds)
                continue
            if key in _WORLD_LIST_KEYS and isinstance(raw, list):
                result[key] = [_mapped(item, worlds) for item in raw]
                continue
            if key in _BOOK_VALUE_KEYS:
                result[key] = _mapped_book(raw, books)
                continue
            if key in _BOOK_LIST_KEYS and isinstance(raw, list):
                result[key] = [_mapped_book(item, books) for item in raw]
                continue
            if key == "scope_id" and node.get("scope_kind") == "world":
                result[key] = _mapped(raw, worlds)
                continue
            if key == "source_id" and source_world_id is not None:
                result[key] = _mapped(source_world_id, worlds)
                continue
            if key == "source" and source_world_id is not None:
                result[key] = f"world:{_mapped(source_world_id, worlds)}"
                continue
            if key == "id" and kind == "world":
                result[key] = _mapped(raw, worlds)
                continue
            if key == "id" and kind == "lorebook":
                result[key] = _mapped_book(raw, books)
                continue
            result[key] = visit(raw)
        return result

    return visit(value)


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _require_columns(conn: sqlite3.Connection, table: str, required: set[str]) -> None:
    missing = required - _columns(conn, table)
    if missing:
        raise WorldIdentityError(
            f"unsupported lorebook schema: {table} missing {sorted(missing)!r}"
        )


def _schema_mode(conn: sqlite3.Connection, tables: set[str]) -> str:
    if "worlds" not in tables or "lorebook_entries" not in tables:
        raise WorldIdentityError("unsupported lorebook schema: worlds/entries are required")
    _require_columns(conn, "worlds", {"id"})
    _require_columns(conn, "lorebook_entries", {"id", "world_id"})
    has_books = "lorebooks" in tables or "lorebook_bindings" in tables
    if has_books and not {"lorebooks", "lorebook_bindings"}.issubset(tables):
        raise WorldIdentityError("unsupported lorebook schema: partial canonical tables")
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if not has_books:
        if version != 4:
            raise WorldIdentityError(f"unsupported lorebook schema version: {version}")
        return "v4"
    if version < 5 or version > 12:
        raise WorldIdentityError(f"unsupported lorebook schema version: {version}")
    _require_columns(conn, "lorebooks", {"id", "source_kind", "source_id"})
    _require_columns(conn, "lorebook_bindings", {"id", "book_id", "scope_kind", "scope_id"})
    _require_columns(conn, "lorebook_entries", {"book_id"})
    if version == 12:
        if "lorebook_operations" not in tables:
            raise WorldIdentityError("unsupported lorebook schema: v12 operations table is missing")
        _require_columns(conn, "lorebook_operations", {"id", "payload_json"})
    return "canonical"


def _json_update(conn: sqlite3.Connection, table: str, column: str, worlds: Mapping[str, str]) -> None:
    if table not in _tables(conn) or column not in _columns(conn, table):
        return
    rows = conn.execute(f'SELECT "id", "{column}" FROM "{table}"').fetchall()
    for row in rows:
        raw = row[1]
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise WorldIdentityError(f"invalid {table}.{column} JSON") from exc
        updated = rewrite_references(payload, worlds)
        if updated != payload:
            conn.execute(
                f'UPDATE "{table}" SET "{column}" = ? WHERE "id" = ?',
                (json.dumps(updated, ensure_ascii=False, separators=(",", ":")), row[0]),
            )


def _prospective_binding(row: sqlite3.Row, worlds: Mapping[str, str], books: Mapping[str, str]) -> tuple[str, str, str, str]:
    book_id = _mapped_book(row["book_id"], books)
    scope_id = worlds.get(row["scope_id"], row["scope_id"]) if row["scope_kind"] == "world" else row["scope_id"]
    binding_id = row["id"]
    for old_book, new_book in books.items():
        if binding_id == f"binding:{old_book}:primary":
            binding_id = f"binding:{new_book}:primary"
            break
    return str(binding_id), str(book_id), str(row["scope_kind"]), str(scope_id)


def rebind_lorebook_worlds(conn: sqlite3.Connection, mapping: Mapping[str, str]) -> None:
    """Rebind existing world rows inside the caller's transaction.

    No commit or rollback is performed.  The caller must have started a
    transaction and owns recovery/journaling around this operation.
    """

    if not conn.in_transaction:
        raise WorldIdentityError("rebind_lorebook_worlds requires a caller-owned transaction")
    worlds, books = _parts(mapping)
    tables = _tables(conn)
    mode = _schema_mode(conn, tables)
    conn.execute("PRAGMA defer_foreign_keys = ON")

    active: dict[str, str] = {}
    for old, new in worlds.items():
        if conn.execute("SELECT 1 FROM worlds WHERE id = ?", (new,)).fetchone() is not None:
            raise WorldIdentityError("target world already exists")
        if mode == 'canonical' and conn.execute('SELECT 1 FROM lorebooks WHERE id = ?', (f'world:{new}',)).fetchone():
            raise WorldIdentityError('target lorebook already exists')
        if conn.execute("SELECT 1 FROM worlds WHERE id = ?", (old,)).fetchone() is None:
            continue
        active[old] = new
    if not active:
        return
    active_books = {
        old: (f"world:{old}", f"world:{new}") for old, new in active.items()
    }
    active_book_map = {old_book: new_book for old_book, new_book in active_books.values()}

    if mode == "canonical":
        for old_book, new_book in active_books.values():
            old_book_exists = conn.execute("SELECT 1 FROM lorebooks WHERE id = ?", (old_book,)).fetchone() is not None
            new_book_exists = conn.execute("SELECT 1 FROM lorebooks WHERE id = ?", (new_book,)).fetchone() is not None
            if new_book_exists:
                raise WorldIdentityError("target lorebook already exists")
            if not old_book_exists:
                referenced = conn.execute(
                    "SELECT 1 FROM lorebook_entries WHERE book_id = ? UNION ALL "
                    "SELECT 1 FROM lorebook_bindings WHERE book_id = ? LIMIT 1",
                    (old_book, old_book),
                ).fetchone()
                if referenced is not None:
                    raise WorldIdentityError("legacy lorebook reference has no lorebook row")

        existing_ids = {str(row[0]) for row in conn.execute("SELECT id FROM lorebook_bindings")}
        prospective_ids: set[str] = set()
        prospective_unique: set[tuple[str, str, str, str]] = set()
        for row in conn.execute("SELECT id, book_id, scope_kind, scope_id, role FROM lorebook_bindings").fetchall():
            binding_id, book_id, scope_kind, scope_id = _prospective_binding(row, active, active_book_map)
            if binding_id in prospective_ids or (binding_id in existing_ids and binding_id != row["id"]):
                raise WorldIdentityError("target lorebook binding already exists")
            prospective_ids.add(binding_id)
            unique = (book_id, scope_kind, scope_id, str(row["role"]))
            if unique in prospective_unique:
                raise WorldIdentityError("target lorebook binding conflicts with an existing binding")
            prospective_unique.add(unique)

    # Child identities are updated in the same deferred transaction as their
    # parent primary keys.  Entry IDs are deliberately never touched.
    for old, new in active.items():
        conn.execute("UPDATE lorebook_entries SET world_id = ? WHERE world_id = ?", (new, old))
        if mode == "canonical":
            old_book, new_book = active_books[old]
            conn.execute("UPDATE lorebook_entries SET book_id = ? WHERE book_id = ?", (new_book, old_book))
    for old, new in active.items():
        conn.execute("UPDATE worlds SET id = ? WHERE id = ?", (new, old))
    if mode == "canonical":
        for old, new in active.items():
            old_book, new_book = active_books[old]
            conn.execute("UPDATE lorebooks SET id = ?, source_id = ? WHERE id = ?", (new_book, new, old_book))
            conn.execute("UPDATE lorebooks SET source_id = ? WHERE source_kind = 'world' AND source_id = ?", (new, old))
            conn.execute("UPDATE lorebook_bindings SET book_id = ? WHERE book_id = ?", (new_book, old_book))
            conn.execute("UPDATE lorebook_bindings SET scope_id = ? WHERE scope_kind = 'world' AND scope_id = ?", (new, old))
            conn.execute("UPDATE lorebook_bindings SET id = ? WHERE id = ?", (f"binding:{new_book}:primary", f"binding:{old_book}:primary"))
        _json_update(conn, "lorebooks", "settings_json", active)
        _json_update(conn, "lorebook_entries", "provenance_json", active)
        _json_update(conn, "lorebook_operations", "payload_json", active)

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise WorldIdentityError(f"foreign key check failed: {len(violations)} violation(s)")


__all__ = ["WorldIdentityError", "rebind_lorebook_worlds", "rewrite_references"]
