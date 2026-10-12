"""Read-only projection contracts for canonical content.

Content projection is an application/read boundary.  A projector may combine
canonical content with already-resolved view context, but it must return a new
mapping and must not mutate the authority it received.  The broad contract is
kept deliberately small here; the domain-specific ``ContentProjectionService``
belongs to the later projection cutover (Track C PR D).
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Protocol, runtime_checkable

from src.engine.participant_view import Viewer
from src.knowledge.visibility import entry_visible_to_viewer
from src.lorebook.resolver import resolve_active_books


@runtime_checkable
class ContentProjection(Protocol):
    """A read-only projector from canonical content to a public view.

    ``context`` is intentionally opaque at this stage.  The Lorebook
    management service uses it for its already-existing binding facts; later
    projection work can add viewer/locale contexts without changing the
    canonical store contract.
    """

    def project(
        self,
        content: Mapping[str, Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class ContentProjectionService:
    """Canonical read-side projection over Book/Binding ownership.

    The service deliberately returns detached mappings.  It never mutates a
    Book, Entry, Binding, or runtime instance and it does not persist a
    compatibility ``world_id``.  Legacy world-only callers can still use the
    Store facade during the migration, but new runtime views should choose one
    of the explicit context methods below.
    """

    def __init__(self, store: Any, *, load_world_template: Any | None = None) -> None:
        self.store = store
        self.load_world_template = load_world_template

    @staticmethod
    def _filter(entries: list[dict[str, Any]], entry_type: str | None) -> list[dict[str, Any]]:
        if not entry_type:
            return [deepcopy(entry) for entry in entries]
        return [
            deepcopy(entry) for entry in entries
            if str(entry.get("type") or "") == str(entry_type)
        ]

    def for_book(self, book_id: str, *, entry_type: str | None = None) -> list[dict[str, Any]]:
        """Project one Book by its canonical owner."""

        if not self.store or not str(book_id or ""):
            return []
        list_book_entries = getattr(self.store, "list_book_entries", None)
        if callable(list_book_entries):
            return self._filter(list_book_entries(str(book_id)), entry_type)
        # Explicit compatibility boundary for stores predating Book-scoped CRUD.
        return self._filter(
            self.store.list_entries(str(book_id), entry_type) if hasattr(self.store, "list_entries") else [],
            entry_type,
        )

    def for_world_authoring(
        self, world_id: str, *, entry_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Project all Books explicitly bound to a World for authoring views."""

        world_id = str(world_id or "")
        if not world_id or not self.store:
            return []
        book_ids: list[str] = []
        if hasattr(self.store, "list_bindings"):
            book_ids = [
                str(binding.get("book_id") or "")
                for binding in self.store.list_bindings(scope_kind="world", scope_id=world_id)
                if binding.get("book_id")
            ]
        if not book_ids and hasattr(self.store, "primary_world_book_id"):
            book_ids = [str(self.store.primary_world_book_id(world_id))]
        result: list[dict[str, Any]] = []
        for book_id in dict.fromkeys(book_ids):
            result.extend(self.for_book(book_id, entry_type=entry_type))
        return result

    def for_game(
        self,
        instance: Any,
        *,
        viewer_kind: str = "gm",
        viewer_uid: str = "",
        action_actor_uids: list[str] | None = None,
        entry_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Project active Books for one runtime context."""

        if not instance or not self.store:
            return []
        actors = (
            action_actor_uids if action_actor_uids is not None
            else getattr(instance, "action_actor_uids", []) or []
        )
        refs = resolve_active_books(
            instance,
            viewer_kind,
            viewer_uid,
            list(actors),
            store=self.store,
        ) if hasattr(self.store, "list_bindings") else []
        if not refs:
            # Same rule as LoreRetriever.ensure_lore_context: a store with no
            # bindings at all is a legacy store whose only content path is the
            # world facade; a store that has bindings but resolved none for
            # this context means "nothing is active" (e.g. a disabled Book).
            # Viewer filtering stays with the callers (for_character/for_party).
            if not hasattr(self.store, "list_bindings") or not self.store.list_bindings():
                return self.for_world_authoring(
                    str(getattr(instance, "world_id", "") or ""), entry_type=entry_type,
                )
            return []
        result: list[dict[str, Any]] = []
        for ref in refs:
            for entry in self.for_book(ref.book_id, entry_type=entry_type):
                row = deepcopy(entry)
                row["_lorebook_id"] = ref.book_id
                row["_lorebook_order"] = ref.order
                result.append(row)
        return result

    def for_character(
        self,
        instance: Any,
        viewer_uid: str,
        *,
        viewer_name: str = "",
        entry_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Project content visible to one character seat.

        Only this seat's character-scoped Books are resolved (never the other
        current actors'), and every entry must pass the shared visibility
        predicate, so GM-private and other-character entries stay hidden.
        """

        uid = str(viewer_uid or "")
        if not uid:
            return []
        return [
            entry
            for entry in self.for_game(
                instance,
                viewer_kind="character",
                viewer_uid=uid,
                action_actor_uids=[],
                entry_type=entry_type,
            )
            if entry_visible_to_viewer(entry, "character", uid, viewer_name)
        ]

    def for_party(
        self, instance: Any, *, entry_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Project only what the whole table may see.

        No character-scoped Book is resolved and every entry must carry an
        explicit public marker; this is the view for a party-wide audience
        and for anyone who is not (yet) a seat of the game.
        """

        return [
            entry
            for entry in self.for_game(
                instance,
                viewer_kind="party",
                action_actor_uids=[],
                entry_type=entry_type,
            )
            if entry_visible_to_viewer(entry, "party")
        ]

    def for_viewer(
        self,
        instance: Any,
        viewer: Viewer,
        *,
        entry_type: str | None = None,
        action_actor_uids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Project content for one resolved participant (Track R6-b).

        ``gm`` gets the full runtime view (``for_game``); a ``seat`` gets its
        character view, matched by uid and its character name as a secondary
        token; any other viewer gets the party view.  ``action_actor_uids``
        only shapes the GM view.
        """

        if viewer.is_gm:
            return self.for_game(
                instance,
                viewer_kind="gm",
                viewer_uid=viewer.uid,
                action_actor_uids=action_actor_uids,
                entry_type=entry_type,
            )
        if viewer.is_seat and viewer.uid:
            players = getattr(instance, "players", {}) or {}
            seat = players.get(viewer.uid) if isinstance(players, dict) else None
            name = str((seat or {}).get("character_name") or "") if isinstance(seat, dict) else ""
            return self.for_character(
                instance, viewer.uid, viewer_name=name, entry_type=entry_type,
            )
        return self.for_party(instance, entry_type=entry_type)


__all__ = ["ContentProjection", "ContentProjectionService"]
