"""Bounded persistence contracts for lorebook operations and raw snapshots.

This module deliberately owns the SQL used by the undo foundation.  Callers
provide already-authorized owner identifiers and opaque JSON payloads; no
policy, HTTP exposure, or agent-specific ownership is inferred here.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from src.lorebook.models import Lorebook, LorebookBinding, LorebookEntry


OPERATION_STATUSES = frozenset({"prepared", "applied", "undone", "restored"})
_OPERATION_COLUMNS = (
    "id", "owner", "kind", "status", "payload_json", "created_at", "updated_at",
)
_BOOK_COLUMNS = tuple(field.column_name for field in Lorebook._meta.sorted_fields)
_ENTRY_COLUMNS = tuple(field.column_name for field in LorebookEntry._meta.sorted_fields)
_BINDING_COLUMNS = tuple(field.column_name for field in LorebookBinding._meta.sorted_fields)


def _quote_column(column: str) -> str:
    return '"' + column.replace('"', '""') + '"'


def _columns_sql(columns: tuple[str, ...]) -> str:
    return ", ".join(_quote_column(column) for column in columns)


def _nonempty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _row_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


class LorebookOperationsMixin:
    """Store methods for durable operations and collision-safe restoration."""

    def _operation_from_row(self, row: sqlite3.Row) -> dict:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("stored lorebook operation payload is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("stored lorebook operation payload must be an object")
        return {
            "id": row["id"],
            "owner": row["owner"],
            "kind": row["kind"],
            "status": row["status"],
            "payload": payload,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def record_lorebook_operation(self, operation: dict) -> None:
        if not isinstance(operation, dict):
            raise ValueError("operation must be an object")
        unknown = set(operation) - {
            "id", "owner", "kind", "status", "payload", "created_at", "updated_at",
        }
        if unknown:
            raise ValueError(f"unsupported operation fields: {sorted(unknown)!r}")
        operation_id = _nonempty_text(operation.get("id"), "id")
        owner = _nonempty_text(operation.get("owner"), "owner")
        kind = _nonempty_text(operation.get("kind"), "kind")
        status = _nonempty_text(operation.get("status"), "status")
        if status not in OPERATION_STATUSES:
            raise ValueError(f"invalid operation status {status!r}")
        payload = operation.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        values: list[Any] = [
            operation_id, owner, kind, status,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        ]
        columns = ["id", "owner", "kind", "status", "payload_json"]
        for column in ("created_at", "updated_at"):
            if column in operation:
                if not isinstance(operation[column], str) or not operation[column].strip():
                    raise ValueError(f"{column} must be a non-empty string when provided")
                columns.append(column)
                values.append(operation[column])
        placeholders = ", ".join("?" for _ in columns)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO lorebook_operations ({_columns_sql(tuple(columns))}) "
                f"VALUES ({placeholders})",
                tuple(values),
            )
            self._commit_locked()

    def get_lorebook_operation(self, operation_id: str, owner: str) -> dict | None:
        operation_id = _nonempty_text(operation_id, "id")
        owner = _nonempty_text(owner, "owner")
        with self._lock:
            row = self._conn.execute(
                "SELECT id, owner, kind, status, payload_json, created_at, updated_at "
                "FROM lorebook_operations WHERE id = ? AND owner = ?",
                (operation_id, owner),
            ).fetchone()
        return self._operation_from_row(row) if row is not None else None

    def list_lorebook_operations(self, owner: str, limit: int = 50) -> list[dict]:
        owner = _nonempty_text(owner, "owner")
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit must be an integer")
        if limit < 0:
            raise ValueError("limit must be non-negative")
        limit = min(limit, 100)
        if limit == 0:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, owner, kind, status, payload_json, created_at, updated_at "
                "FROM lorebook_operations WHERE owner = ? "
                "ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (owner, limit),
            ).fetchall()
        return [self._operation_from_row(row) for row in rows]

    def update_lorebook_operation(self, operation_id: str, owner: str, changes: dict) -> bool:
        operation_id = _nonempty_text(operation_id, "id")
        owner = _nonempty_text(owner, "owner")
        if not isinstance(changes, dict) or not changes:
            raise ValueError("changes must be a non-empty object")
        if set(changes) - {"status", "payload"}:
            raise ValueError("only status and payload may be updated")
        status = changes.get("status")
        if "status" in changes:
            status = _nonempty_text(status, "status")
            if status not in OPERATION_STATUSES:
                raise ValueError(f"invalid operation status {status!r}")
        payload = changes.get("payload")
        if "payload" in changes and not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        with self._lock:
            existing = self._conn.execute(
                "SELECT status, payload_json FROM lorebook_operations "
                "WHERE id = ? AND owner = ?",
                (operation_id, owner),
            ).fetchone()
            if existing is None:
                return False
            new_status = status if status is not None else existing["status"]
            new_payload = (
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                if "payload" in changes else existing["payload_json"]
            )
            self._conn.execute(
                "UPDATE lorebook_operations SET status = ?, payload_json = ?, "
                "updated_at = datetime('now') WHERE id = ? AND owner = ?",
                (new_status, new_payload, operation_id, owner),
            )
            self._commit_locked()
            return True

    def _snapshot_rows_locked(self, book_id: str) -> dict | None:
        book = _row_dict(self._conn.execute("SELECT * FROM lorebooks WHERE id = ?", (book_id,)).fetchone())
        if book is None:
            return None
        entries = [
            dict(row) for row in self._conn.execute(
                "SELECT * FROM lorebook_entries WHERE book_id = ? ORDER BY id", (book_id,)
            ).fetchall()
        ]
        bindings = [
            dict(row) for row in self._conn.execute(
                "SELECT * FROM lorebook_bindings WHERE book_id = ? ORDER BY id", (book_id,)
            ).fetchall()
        ]
        return {"book": book, "entries": entries, "bindings": bindings}

    def snapshot_lorebook(self, book_id: str) -> dict | None:
        book_id = _nonempty_text(book_id, "book_id")
        with self._lock:
            return self._snapshot_rows_locked(book_id)

    def snapshot_lorebook_entry(self, book_id: str, entry_id: str) -> dict | None:
        book_id = _nonempty_text(book_id, "book_id")
        entry_id = _nonempty_text(entry_id, "entry_id")
        with self._lock:
            return _row_dict(self._conn.execute(
                "SELECT * FROM lorebook_entries WHERE book_id = ? AND id = ?",
                (book_id, entry_id),
            ).fetchone())

    @staticmethod
    def _validate_snapshot_row(row: Any, columns: tuple[str, ...], label: str) -> dict:
        if not isinstance(row, dict) or set(row) != set(columns):
            raise ValueError(f"{label} does not match the canonical schema")
        return row

    def _validate_book_snapshot(self, snapshot: Any) -> tuple[dict, list[dict], list[dict]]:
        if not isinstance(snapshot, dict) or set(snapshot) != {"book", "entries", "bindings"}:
            raise ValueError("invalid lorebook snapshot")
        book = self._validate_snapshot_row(snapshot["book"], _BOOK_COLUMNS, "book snapshot")
        entries = snapshot["entries"]
        bindings = snapshot["bindings"]
        if not isinstance(entries, list) or not isinstance(bindings, list):
            raise ValueError("snapshot entries and bindings must be lists")
        entries = [self._validate_snapshot_row(row, _ENTRY_COLUMNS, "entry snapshot") for row in entries]
        bindings = [self._validate_snapshot_row(row, _BINDING_COLUMNS, "binding snapshot") for row in bindings]
        book_id = _nonempty_text(book.get("id"), "book.id")
        if len({row["id"] for row in entries}) != len(entries) or len({row["id"] for row in bindings}) != len(bindings):
            raise ValueError("snapshot contains duplicate identities")
        for row in entries:
            if row["book_id"] != book_id or not isinstance(row["id"], str) or not row["id"].strip():
                raise ValueError("entry snapshot has an invalid book or identity")
        for row in bindings:
            if row["book_id"] != book_id or not isinstance(row["id"], str) or not row["id"].strip():
                raise ValueError("binding snapshot has an invalid book or identity")
        try:
            revision = int(book["revision"])
        except (TypeError, ValueError) as exc:
            raise ValueError("book revision is invalid") from exc
        if revision < 0:
            raise ValueError("book revision is invalid")
        return book, entries, bindings

    def _ensure_absent_locked(self, table: str, identity: str, label: str) -> None:
        if self._conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (identity,)).fetchone() is not None:
            raise ValueError(f"{label} identity already exists")

    def _insert_fixed_row_locked(self, table: str, columns: tuple[str, ...], row: dict) -> None:
        self._conn.execute(
            f"INSERT INTO {table} ({_columns_sql(columns)}) VALUES "
            f"({', '.join('?' for _ in columns)})",
            tuple(row[column] for column in columns),
        )

    def restore_lorebook_snapshot(self, snapshot: dict) -> None:
        book, entries, bindings = self._validate_book_snapshot(snapshot)
        book_id = book["id"]
        with self.transaction():
            self._ensure_absent_locked("lorebooks", book_id, "book")
            for row in entries:
                self._ensure_absent_locked("lorebook_entries", row["id"], "entry")
            for row in bindings:
                self._ensure_absent_locked("lorebook_bindings", row["id"], "binding")
            restored_book = dict(book)
            restored_book["revision"] = int(book["revision"]) + 1
            self._insert_fixed_row_locked("lorebooks", _BOOK_COLUMNS, restored_book)
            for row in bindings:
                self._insert_fixed_row_locked("lorebook_bindings", _BINDING_COLUMNS, row)
            for row in entries:
                self._insert_fixed_row_locked("lorebook_entries", _ENTRY_COLUMNS, row)

    def restore_lorebook_entry(self, book_id: str, snapshot: dict) -> None:
        book_id = _nonempty_text(book_id, "book_id")
        row = self._validate_snapshot_row(snapshot, _ENTRY_COLUMNS, "entry snapshot")
        if row["book_id"] != book_id or not isinstance(row["id"], str) or not row["id"].strip():
            raise ValueError("entry snapshot has an invalid book or identity")
        with self.transaction():
            if self._conn.execute("SELECT 1 FROM lorebooks WHERE id = ?", (book_id,)).fetchone() is None:
                raise ValueError("target book does not exist")
            self._ensure_absent_locked("lorebook_entries", row["id"], "entry")
            self._insert_fixed_row_locked("lorebook_entries", _ENTRY_COLUMNS, row)
            self._bump_book_revision_locked(book_id)
