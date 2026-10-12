"""Confirmable Lorebook import plans: update / duplicate / skip.

``plan_lorebook_import`` shows what a commit would do against the current
store; ``execute_lorebook_plan`` carries out one confirmed item atomically.
The caller (the Lorebook service) revalidates ``plan_digest`` between the two.

Semantics per matched Book:

- update: full mirror. Book metadata and settings are overwritten, entries
  are upserted by their import id and entries the pushed Book no longer has
  are deleted. Bindings and ``enabled`` are server-side setup and are kept.
- duplicate: a new Book takes over the import identity (tracked); the old
  one is kept and detached, with its provenance intact.
- skip: nothing is written; the existing Book id is returned.
- unchanged: the draft equals what was last imported and the server copy was
  not edited since; nothing is written.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from src.content_modules.plan import Decision, ExistingMatch, PlanItem, content_digest
from src.content_modules.refs import ContentDraft
from src.lorebook.domain import LorebookDraft
from src.lorebook.exporter import export_lorebook_v3
from src.lorebook.importer import (
    DeclaredSource,
    book_settings,
    draft_lorebook_import,
    import_entry_id,
    in_import_transaction,
    legacy_book_id,
    lorebook_draft_digest,
    lorebook_content_draft,
    write_import_entries,
)

#: Book fields that make up its content for ``server_modified`` detection.
#: ``enabled`` and bindings are server-side table setup, not imported content.
_STATE_BOOK_FIELDS = (
    "name", "description", "language", "scan_depth", "token_budget",
    "recursive_scanning", "settings",
)
_STATE_ENTRY_IGNORED = frozenset({"created_at", "updated_at", "book_id", "world_id"})


def book_state_digest(store: Any, book_id: str) -> str:
    """Digest of a stored Book's imported content (metadata + entries)."""

    book = store.get_lorebook(book_id) or {}
    entries = sorted(
        (
            {key: value for key, value in row.items() if key not in _STATE_ENTRY_IGNORED}
            for row in store.list_book_entries(book_id)
        ),
        key=lambda row: str(row.get("id") or ""),
    )
    return content_digest({
        "book": {key: book.get(key) for key in _STATE_BOOK_FIELDS},
        "entries": entries,
    })


def portable_lorebook_document(store: Any, book_id: str) -> dict[str, Any]:
    """``lorebook_v3`` export whose entry ids are the ids the source used.

    An imported entry is exported under the external id it was pushed with,
    so pushing the document back addresses the same canonical entries instead
    of replacing them. Entries created on the server keep their canonical id.
    """

    document = export_lorebook_v3(store, book_id)
    rows = {str(row.get("id") or ""): row for row in store.list_book_entries(book_id)}
    for entry in document["data"]["lorebook"]["entries"]:
        provenance = (rows.get(str(entry.get("id") or "")) or {}).get("provenance")
        external = provenance.get("external_id") if isinstance(provenance, dict) else None
        if external:
            entry["id"] = str(external)
    return document


@dataclass(frozen=True)
class LorebookImportPlan:
    draft: LorebookDraft
    content_draft: ContentDraft
    declared: DeclaredSource | None
    item: PlanItem
    #: "identity" (the Book follows this source), "hint" (a server Book the
    #: client named via canonical_hint) or "" (no match).
    matched_by: str = ""


def tracked_books(
    store: Any, content_draft: ContentDraft, declared: DeclaredSource | None,
) -> list[dict[str, Any]]:
    """Books currently following this draft's identity, oldest first.

    A declared (device) draft follows a Book by its external id; the tracked
    identity index allows at most one. A legacy draft is identified by its
    source alone and matches only Books written without an external id, and
    nothing prevents several legacy Books from sharing a source, so the order
    is fixed (creation time, then id) instead of depending on list order.
    Detached Books never match.
    """

    matches = []
    for book in store.list_lorebooks():
        if str(book.get("import_link") or "") == "detached":
            continue
        if str(book.get("source_kind") or "") != content_draft.source_kind:
            continue
        if str(book.get("source_id") or "") != content_draft.source_id:
            continue
        external = str(book.get("external_id") or "")
        if (declared is not None and external == content_draft.external_id) or (
            declared is None and not external
        ):
            matches.append(book)
    return sorted(matches, key=lambda book: (str(book.get("created_at") or ""), str(book.get("id") or "")))


def tracked_book(
    store: Any, content_draft: ContentDraft, declared: DeclaredSource | None,
) -> dict[str, Any] | None:
    """The Book a plan targets: the oldest of :func:`tracked_books`."""

    matches = tracked_books(store, content_draft, declared)
    return matches[0] if matches else None


#: Why a hinted Book cannot be updated by this push.
LOCKED_PLUGIN_BOOK = "PLUGIN_BOOK"
LOCKED_TRACKED_BY_OTHER_SOURCE = "TRACKED_BY_OTHER_SOURCE"
LOCKED_DETACHED_FROM_OTHER_SOURCE = "DETACHED_FROM_OTHER_SOURCE"


def _book_bindings(store: Any, book_id: str) -> list[dict[str, str]]:
    """Where a hinted Book is bound, so a client can warn before a mirror
    update rewrites a Book that games or characters use."""

    return [
        {"scope_kind": str(binding.get("scope_kind") or ""), "scope_id": str(binding.get("scope_id") or "")}
        for binding in store.list_bindings()
        if str(binding.get("book_id") or "") == book_id
    ]


def book_lock_reason(store: Any, book_id: str) -> str:
    """The lock that holds whoever pushes: a Book with plugin entries is the
    plugin's (``""`` when free). Preview, list and export all use this."""

    return LOCKED_PLUGIN_BOOK if store.book_has_plugin_entries(book_id) else ""


def _hint_lock_reason(store: Any, book: dict[str, Any], declared: DeclaredSource) -> str:
    """Duplicate/skip only for a hinted Book that belongs to someone else.

    Plugin content, and any Book carrying another source's provenance
    (tracked, legacy-linked or detached), stays that source's lineage.
    """

    if reason := book_lock_reason(store, str(book["id"])):
        return reason
    if not str(book.get("source_id") or ""):
        return ""  # created on this server: free to adopt
    origin = (
        str(book.get("source_kind") or ""), str(book.get("source_id") or ""),
        str(book.get("external_id") or ""),
    )
    if origin == (declared.source_kind, declared.source_id, declared.external_id):
        return ""
    if str(book.get("import_link") or "") == "detached":
        return LOCKED_DETACHED_FROM_OTHER_SOURCE
    return LOCKED_TRACKED_BY_OTHER_SOURCE


@dataclass(frozen=True)
class PreparedLorebook:
    """One parsed Lorebook push: everything that needs no server state."""

    draft: LorebookDraft
    content_draft: ContentDraft


def prepare_lorebook_import(
    payload: dict[str, Any], *, declared: DeclaredSource | None = None,
) -> PreparedLorebook:
    """Parse ``payload`` once (adapter + shared draft); no store access."""

    draft = draft_lorebook_import(payload)
    return PreparedLorebook(
        draft=draft,
        content_draft=lorebook_content_draft(payload, declared=declared, draft=draft),
    )


def plan_lorebook_import(
    store: Any,
    payload: dict[str, Any],
    *,
    declared: DeclaredSource | None = None,
    hint: str = "",
    prepared: PreparedLorebook | None = None,
) -> LorebookImportPlan:
    """What a commit of ``payload`` would do against the current store.

    ``hint`` names a server Book the client pulled earlier. It is only
    consulted when nothing follows the declared identity: a hint never
    overrides an identity match.
    """

    if prepared is None:
        prepared = prepare_lorebook_import(payload, declared=declared)
    draft, content_draft = prepared.draft, prepared.content_draft
    matches = tracked_books(store, content_draft, declared)
    book = matches[0] if matches else None
    matched_by = "identity" if book is not None else ""
    lock_reason = ""
    if book is None and hint and declared is not None:
        book = store.get_lorebook(hint)
        if book is not None:
            matched_by = "hint"
            matches = [book]
            lock_reason = _hint_lock_reason(store, book, declared)
    existing: ExistingMatch | None = None
    unchanged = False
    if book is not None:
        book_id = str(book["id"])
        recorded = str(book.get("import_state_digest") or "") if matched_by == "identity" else ""
        # Books imported before plans existed (and hinted Books, which never
        # followed this source) carry no recorded state: unknown, not "no".
        server_modified = (book_state_digest(store, book_id) != recorded) if recorded else None
        planned = {
            import_entry_id(store, draft, book_id, index, entry)
            for index, entry in enumerate(draft.entries)
        }
        current = {str(row.get("id") or "") for row in store.list_book_entries(book_id)}
        existing = ExistingMatch(
            canonical_id=book_id,
            state_token=str(int(book.get("revision") or 0)),
            server_modified=server_modified,
            details={
                "name": str(book.get("name") or ""),
                "matched_by": matched_by,
                **({"bindings": _book_bindings(store, book_id)} if matched_by == "hint" else {}),
                "entries_add": len(planned - current),
                "entries_update": len(planned & current),
                "entries_remove": len(current - planned),
                # Other legacy Books sharing this source; the plan never
                # touches them, but the user should know they exist.
                "other_matches": [str(other["id"]) for other in matches[1:]],
            },
        )
        unchanged = server_modified is False and (
            str(book.get("source_digest") or "") == content_draft.digest
            # A client that pulled this Book pushes back our own export of it.
            or lorebook_draft_digest(
                draft_lorebook_import(portable_lorebook_document(store, book_id))
            ) == content_draft.digest
        )
    item = PlanItem(
        client_ref=content_draft.ref.canonical(),
        kind="lorebook",
        draft_digest=content_draft.digest,
        action="create" if existing is None else ("unchanged" if unchanged else "update"),
        existing=existing,
        restricted_to=("duplicate", "skip") if lock_reason else None,
        reason=lock_reason,
    )
    return LorebookImportPlan(
        draft=draft, content_draft=content_draft, declared=declared, item=item, matched_by=matched_by,
    )


def _new_book_id(store: Any, plan: LorebookImportPlan) -> str:
    if plan.declared is None:
        base = legacy_book_id(plan.draft)
    else:
        key = f"{plan.declared.source_id}/{plan.declared.external_id}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        base = f"import:{plan.declared.source_kind}:{digest}"
    book_id = base
    while store.get_lorebook(book_id) is not None:
        book_id = f"{base}:{uuid.uuid4().hex[:8]}"
    return book_id


def _book_fields(draft: LorebookDraft) -> dict[str, Any]:
    return {
        "name": draft.name,
        "description": draft.description,
        "language": draft.language,
        "scan_depth": draft.settings.get("scan_depth", 0),
        "token_budget": draft.settings.get("token_budget", 0),
        "recursive_scanning": draft.settings.get("recursive_scanning", False),
    }


def execute_lorebook_plan(
    store: Any,
    plan: LorebookImportPlan,
    decision: Decision | None,
    *,
    binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Carry out one confirmed plan item atomically.

    ``decision`` is ``None`` only when nothing matched (create).
    """

    item, draft, content = plan.item, plan.draft, plan.content_draft
    existing = item.existing
    if existing is not None and decision == "skip":
        return {"status": "skipped", "book_id": existing.canonical_id, "entries_removed": 0}
    if existing is not None and decision == "update" and item.action == "unchanged":
        return {"status": "unchanged", "book_id": existing.canonical_id, "entries_removed": 0}

    def _bind(book_id: str) -> None:
        if binding:
            store.bind_lorebook({
                "id": binding.get("id", f"binding:{book_id}"), "book_id": book_id,
                **{key: value for key, value in binding.items() if key != "id"},
            })

    def _record(book_id: str) -> None:
        store.record_lorebook_import(
            book_id,
            source_kind=content.source_kind,
            source_id=content.source_id,
            external_id=plan.declared.external_id if plan.declared else "",
            source_digest=content.digest,
            import_link="tracked",
            import_state_digest=book_state_digest(store, book_id),
        )

    if existing is not None and decision == "update":
        book_id = existing.canonical_id
        removed: list[str] = []

        def _mirror() -> None:
            store.update_lorebook(book_id, {**_book_fields(draft), "settings_json": book_settings(draft)})
            _bind(book_id)
            written = set(write_import_entries(store, draft, book_id, binding))
            # Full mirror: an entry the pushed Book no longer has is removed.
            for row in store.list_book_entries(book_id):
                entry_id = str(row.get("id") or "")
                if entry_id not in written:
                    store.delete_book_entry(book_id, entry_id)
                    removed.append(entry_id)
            _record(book_id)

        in_import_transaction(store, _mirror)
        return {"status": "updated", "book_id": book_id, "entries_removed": len(removed)}

    book_id = _new_book_id(store, plan)
    # Only a Book that followed this source is detached by "keep both"; a
    # hinted Book is someone else's and stays exactly as it is.
    detached = existing.canonical_id if existing is not None and plan.matched_by == "identity" else ""

    def _create() -> None:
        if detached:
            # "Keep both": the old copy stops following the source (its
            # provenance stays) and the new copy takes over the identity.
            store.detach_lorebook(detached)
        store.create_lorebook({
            "id": book_id, **_book_fields(draft), "settings": book_settings(draft),
            "source_kind": content.source_kind, "source_id": content.source_id,
        })
        _bind(book_id)
        write_import_entries(store, draft, book_id, binding)
        _record(book_id)

    in_import_transaction(store, _create)
    result: dict[str, Any] = {
        "status": "duplicated" if existing is not None else "created", "book_id": book_id, "entries_removed": 0,
    }
    if detached:
        result["detached_book_id"] = detached
    return result


__all__ = [
    "LorebookImportPlan",
    "book_lock_reason",
    "book_state_digest",
    "execute_lorebook_plan",
    "PreparedLorebook",
    "plan_lorebook_import",
    "prepare_lorebook_import",
    "portable_lorebook_document",
    "tracked_book",
    "tracked_books",
]
