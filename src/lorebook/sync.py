"""Lorebook importer/exporter for the multi-kind content sync contract."""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from typing import Any

from src.content_modules.plan import Decision, DeclaredSource
from src.content_modules.sync import KindPlan, SyncItem, SyncItemError, SyncSource, check_book_limits
from src.engine.world.contracts import canonical_id
from src.lorebook.import_plan import (
    PreparedLorebook,
    book_lock_reason,
    execute_lorebook_plan,
    plan_lorebook_import,
    prepare_lorebook_import,
    portable_lorebook_document,
)

LOREBOOK_FORMAT = "lorebook_v3"
FORMAT_UNSUPPORTED = "FORMAT_UNSUPPORTED"


def lorebook_state_token(store: Any, book_id: str, *, book: dict[str, Any] | None = None) -> str:
    """A Book's state token; pass ``book`` when it is already loaded."""

    if book is None:
        book = store.get_lorebook(book_id) or {}
    return str(int(book.get("revision") or 0))


def lorebook_result(store: Any, client_ref: str, result: dict[str, Any]) -> dict[str, Any]:
    """One sync result row for an executed Lorebook plan."""

    row: dict[str, Any] = {
        "client_ref": client_ref,
        "kind": "lorebook",
        "status": result["status"],
        "canonical_id": result["book_id"],
        "state_token": lorebook_state_token(store, result["book_id"]),
        "entries_removed": int(result.get("entries_removed") or 0),
    }
    if result.get("detached_book_id"):
        row["detached_id"] = result["detached_book_id"]
    return row


def book_provenance(book: dict[str, Any]) -> dict[str, str] | None:
    if not str(book.get("source_id") or ""):
        return None
    return {
        "source_kind": str(book.get("source_kind") or ""),
        "source_id": str(book.get("source_id") or ""),
        "external_id": str(book.get("external_id") or ""),
        "link": str(book.get("import_link") or ""),
        "source_digest": str(book.get("source_digest") or ""),
    }


class LorebookSyncImporter:
    """Plans one pushed ``lorebook_v3`` document; the Book is left unbound."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def lock(self) -> AbstractContextManager[Any]:
        # The canonical store is SQLite on the event-loop thread and each
        # item commits in its own transaction; no library-level lock needed.
        return nullcontext()

    def prepare(self, source: SyncSource, item: SyncItem) -> PreparedLorebook:
        document = item.document
        if item.format not in ("", LOREBOOK_FORMAT) or not isinstance(document, dict) or (
            document.get("spec") != LOREBOOK_FORMAT
        ):
            raise SyncItemError(FORMAT_UNSUPPORTED, "a lorebook item must be a lorebook_v3 document")
        declared = DeclaredSource(source.kind, source.id, canonical_id(item.client_ref, field="client_ref"))
        prepared = prepare_lorebook_import(document, declared=declared)
        # Limits apply to what the adapter actually parsed, before planning.
        check_book_limits(prepared.draft.entries, client_ref=item.client_ref)
        return prepared

    def plan(self, source: SyncSource, item: SyncItem, prepared: PreparedLorebook) -> KindPlan:
        declared = DeclaredSource(source.kind, source.id, item.client_ref)
        plan = plan_lorebook_import(
            self.store, item.document, declared=declared, prepared=prepared, hint=item.canonical_hint,
        )
        store = self.store

        def execute(resolved: Any) -> list[dict[str, Any]]:
            decision: Decision | None = resolved.get(item.client_ref)
            result = execute_lorebook_plan(store, plan, decision)
            return [lorebook_result(store, item.client_ref, result)]

        warnings = [{"code": "LOREBOOK_ADAPTER", "message": str(text)} for text in plan.draft.warnings]
        return KindPlan(entries=[(item.client_ref, plan.item)], execute=execute, warnings=warnings)


class LorebookSyncExporter:
    def __init__(self, store: Any) -> None:
        self.store = store

    def status(self, canonical_id: str) -> dict[str, Any] | None:
        book = self.store.get_lorebook(canonical_id)
        if not book:
            return None
        return {
            "state_token": lorebook_state_token(self.store, canonical_id, book=book),
            "provenance": book_provenance(book),
        }

    def export(self, canonical_id: str) -> dict[str, Any] | None:
        book = self.store.get_lorebook(canonical_id)
        if not book:
            return None
        return {
            "format": LOREBOOK_FORMAT,
            "document": portable_lorebook_document(self.store, canonical_id),
            "state_token": lorebook_state_token(self.store, canonical_id, book=book),
            "provenance": book_provenance(book),
            "locked_reason": book_lock_reason(self.store, canonical_id),
        }

    def ids(self) -> list[str]:
        # Every Book, whatever it is bound to (world, game, character, global)
        # or unbound: the owner's library, not one scope's view of it.
        return [str(book["id"]) for book in self.store.list_lorebooks()]

    def summary(self, canonical_id: str) -> dict[str, Any] | None:
        book = self.store.get_lorebook(canonical_id)
        if not book:
            return None
        # One Book read plus two indexed counts: no entry bodies are loaded.
        return {
            "name": str(book.get("name") or ""),
            "state_token": lorebook_state_token(self.store, canonical_id, book=book),
            "provenance": book_provenance(book),
            "locked_reason": book_lock_reason(self.store, canonical_id),
            "entries": self.store.count_book_entries(canonical_id),
        }


__all__ = [
    "LorebookSyncExporter",
    "LorebookSyncImporter",
    "book_provenance",
    "lorebook_result",
    "lorebook_state_token",
]
