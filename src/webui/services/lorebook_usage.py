"""Read-only canonical Lorebook usage projections."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from src.lorebook.resolver import BookRef, resolve_active_books


@dataclass(frozen=True)
class LorebookUsageDependencies:
    """Explicit read dependencies for the owner-facing usage projection."""

    lorebook: Any
    get_instance: Callable[[str], Any | None]


def _scope(bindings: list[Mapping[str, Any]]) -> str:
    for kind in ("character", "game", "world", "global"):
        if any(str(binding.get("scope_kind") or "") == kind for binding in bindings):
            return kind
    return ""


def _book_row(
    book: Mapping[str, Any],
    bindings: list[Mapping[str, Any]],
    entry_count: int,
    *,
    scope: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(book.get("id") or ""),
        "name": str(book.get("name") or book.get("id") or ""),
        "enabled": bool(book.get("enabled", True)),
        "scope": _scope(bindings) if scope is None else scope,
        "entry_count": int(entry_count),
    }


def _all_books(deps: LorebookUsageDependencies) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    store = deps.lorebook
    bindings_by_book: dict[str, list[dict[str, Any]]] = {}
    for binding in store.list_bindings():
        book_id = str(binding.get("book_id") or "")
        if book_id:
            bindings_by_book.setdefault(book_id, []).append(dict(binding))

    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for raw_book in store.list_lorebooks():
        book = dict(raw_book)
        book_id = str(book.get("id") or "")
        if not book_id or book_id in seen:
            continue
        seen.add(book_id)
        rows.append(_book_row(
            book,
            bindings_by_book.get(book_id, []),
            len(store.list_book_entries(book_id)),
        ))
    return rows, bindings_by_book


def _unavailable(game_key: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "game_key": game_key,
        "world_id": "",
        "world_name": "",
        "count": None,
        "books": [],
    }


def _game_projection(
    deps: LorebookUsageDependencies,
    game_key: str,
    viewer: str,
    bindings_by_book: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    try:
        instance = deps.get_instance(game_key) if game_key else None
    except Exception:
        instance = None
    if instance is None:
        return _unavailable(game_key)

    players = getattr(instance, "players", {}) or {}
    viewer = str(viewer or "gm")
    if viewer == "gm":
        viewer_kind, viewer_uid = "gm", ""
        actors = list(getattr(instance, "action_actor_uids", []) or [])
    elif viewer == "party":
        viewer_kind, viewer_uid, actors = "party", "", []
    elif viewer in {str(uid) for uid in players}:
        viewer_kind, viewer_uid, actors = "character", viewer, [viewer]
    else:
        return _unavailable(game_key)

    try:
        refs: list[BookRef] = resolve_active_books(
            instance,
            viewer_kind=viewer_kind,
            viewer_uid=viewer_uid,
            action_actor_uids=actors,
            store=deps.lorebook,
        )
    except Exception:
        return _unavailable(game_key)
    books: list[dict[str, Any]] = []
    for ref in refs:
        book = deps.lorebook.get_lorebook(ref.book_id)
        if not isinstance(book, dict) or not str(book.get("id") or ""):
            return _unavailable(game_key)
        entry_count = len(deps.lorebook.list_book_entries(ref.book_id))
        resolved_binding = next(
            (
                binding for binding in bindings_by_book.get(ref.book_id, [])
                if str(binding.get("id") or "") == str(ref.binding_id or "")
            ),
            None,
        )
        books.append(_book_row(
            book,
            bindings_by_book.get(ref.book_id, []),
            entry_count,
            scope=(
                str(resolved_binding.get("scope_kind") or "")
                if resolved_binding is not None else ""
            ),
        ))

    world_id = str(getattr(instance, "world_id", "") or "")
    world_name = str(getattr(instance, "world_name", "") or "")
    get_world = getattr(deps.lorebook, "get_world", None)
    if callable(get_world) and world_id and not world_name:
        world = get_world(world_id)
        if isinstance(world, dict):
            world_name = str(world.get("name") or world_name)
    return {
        "status": "ready",
        "game_key": game_key,
        "world_id": world_id,
        "world_name": world_name,
        "count": len(books),
        "books": books,
    }


def usage_summary(
    deps: LorebookUsageDependencies,
    game_key: str = "",
    viewer: str = "gm",
) -> dict[str, Any]:
    """Build a detached library/game usage summary without side effects."""
    library_books, bindings_by_book = _all_books(deps)
    enabled = sum(1 for book in library_books if book["enabled"])
    game = (
        {"status": "none", "game_key": "", "world_id": "", "world_name": "", "count": None, "books": []}
        if not str(game_key or "").strip()
        else _game_projection(deps, str(game_key), str(viewer or "gm"), bindings_by_book)
    )
    return {
        "ok": True,
        "library": {
            "total": len(library_books),
            "enabled": enabled,
            "disabled": len(library_books) - enabled,
            "books": deepcopy(library_books),
        },
        "game": game,
    }


__all__ = ["LorebookUsageDependencies", "usage_summary"]
