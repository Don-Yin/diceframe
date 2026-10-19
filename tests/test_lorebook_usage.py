"""Read-only Lorebook usage projection tests."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from src.webui.services.lorebook_usage import LorebookUsageDependencies, usage_summary


class _Store:
    def __init__(self) -> None:
        self.books = {
            "global": {"id": "global", "name": "Global", "enabled": True},
            "world": {"id": "world", "name": "World", "enabled": True},
            "game": {"id": "game", "name": "Game", "enabled": True},
            "character": {"id": "character", "name": "Character", "enabled": True},
            "disabled": {"id": "disabled", "name": "Disabled", "enabled": False},
            "unbound": {"id": "unbound", "name": "Unbound", "enabled": True},
            "duplicate": {"id": "duplicate", "name": "Duplicate", "enabled": True},
            "other": {"id": "other", "name": "Other", "enabled": True},
        }
        self.bindings = [
            {"id": "b-global", "book_id": "global", "scope_kind": "global", "scope_id": "", "enabled": True, "order": 10},
            {"id": "b-world", "book_id": "world", "scope_kind": "world", "scope_id": "w1", "enabled": True, "order": 20},
            {"id": "b-game", "book_id": "game", "scope_kind": "game", "scope_id": "g1", "enabled": True, "order": 30},
            {"id": "b-character", "book_id": "character", "scope_kind": "character", "scope_id": "c1", "enabled": True, "order": 40},
            {"id": "b-disabled", "book_id": "disabled", "scope_kind": "global", "scope_id": "", "enabled": False, "order": 50},
            {"id": "b-other", "book_id": "other", "scope_kind": "world", "scope_id": "other-world", "enabled": True, "order": 60},
            {"id": "b-duplicate-global", "book_id": "duplicate", "scope_kind": "global", "scope_id": "", "enabled": True, "order": 70},
            {"id": "b-duplicate-world", "book_id": "duplicate", "scope_kind": "world", "scope_id": "w1", "enabled": True, "order": 80},
        ]
        self.entries = {book_id: [{"id": f"{book_id}-entry", "content": "private body"}] for book_id in self.books}
        self.reads = 0

    def list_lorebooks(self):
        self.reads += 1
        return [deepcopy(book) for book in self.books.values()]

    def list_bindings(self):
        self.reads += 1
        return deepcopy(self.bindings)

    def get_lorebook(self, book_id: str):
        self.reads += 1
        return deepcopy(self.books.get(book_id))

    def list_book_entries(self, book_id: str):
        self.reads += 1
        return deepcopy(self.entries.get(book_id, []))

    def get_world(self, world_id: str):
        self.reads += 1
        return {"id": world_id, "name": "World One"} if world_id == "w1" else None


def _instance(*, explicit: bool = False):
    return SimpleNamespace(
        game_key="g1",
        game_id="g1",
        world_id="w1",
        world_name="Runtime World",
        players={"c1": object(), "c2": object()},
        action_actor_uids=["c1"],
        modules={"content_binding": {"book_selection": "explicit" if explicit else "auto"}},
    )


def _deps(store: _Store, instance=None):
    return LorebookUsageDependencies(
        lorebook=store,
        get_instance=lambda key: instance if key == "g1" else None,
    )


def test_library_includes_unbound_and_counts_book_enabled_without_entry_bodies():
    store = _Store()
    before_books = deepcopy(store.books)
    before_bindings = deepcopy(store.bindings)
    before_entries = deepcopy(store.entries)
    result = usage_summary(_deps(store), "", "gm")

    assert result["ok"] is True
    assert result["game"]["status"] == "none"
    assert result["game"]["count"] is None
    library = result["library"]
    assert library["total"] == 8
    assert library["enabled"] == 7
    assert library["disabled"] == 1
    by_id = {book["id"]: book for book in library["books"]}
    assert by_id["unbound"]["scope"] == ""
    assert by_id["duplicate"]["scope"] == "world"
    assert by_id["global"]["entry_count"] == 1
    assert all("content" not in book for book in library["books"])
    assert store.books == before_books
    assert store.bindings == before_bindings
    assert store.entries == before_entries


def test_game_summary_uses_resolver_for_gm_party_character_and_explicit_selection():
    store = _Store()
    instance = _instance()
    store.entries["game"] = [
        {"id": f"game-entry-{index}", "content": "private body"}
        for index in range(11)
    ]

    gm = usage_summary(_deps(store, instance), "g1", "gm")
    party = usage_summary(_deps(store, instance), "g1", "party")
    character = usage_summary(_deps(store, instance), "g1", "c1")
    explicit = usage_summary(_deps(store, _instance(explicit=True)), "g1", "gm")

    assert gm["game"]["status"] == "ready"
    assert {book["id"] for book in gm["game"]["books"]} == {"global", "world", "game", "character", "duplicate"}
    assert {book["id"] for book in party["game"]["books"]} == {"global", "world", "game", "duplicate"}
    assert {book["id"] for book in character["game"]["books"]} == {"global", "world", "game", "character", "duplicate"}
    assert {book["id"] for book in explicit["game"]["books"]} == {"game", "character"}
    assert gm["game"]["count"] == 5
    assert explicit["game"]["count"] == 2
    assert next(book for book in gm["game"]["books"] if book["id"] == "game")["entry_count"] == 11
    assert gm["game"]["world_name"] == "Runtime World"


def test_game_scope_uses_the_resolved_binding_not_an_unselected_binding():
    store = _Store()
    store.books["resolved-scope"] = {"id": "resolved-scope", "name": "Resolved", "enabled": True}
    store.entries["resolved-scope"] = [{"id": "resolved-entry", "content": "private body"}]
    store.bindings.extend([
        {"id": "b-resolved-global", "book_id": "resolved-scope", "scope_kind": "global", "scope_id": "", "enabled": True, "order": 5},
        {"id": "b-resolved-character", "book_id": "resolved-scope", "scope_kind": "character", "scope_id": "c2", "enabled": True, "order": 6},
    ])

    result = usage_summary(_deps(store, _instance()), "g1", "gm")

    resolved = next(book for book in result["game"]["books"] if book["id"] == "resolved-scope")
    assert resolved["scope"] == "global"


def test_invalid_game_character_and_missing_canonical_book_are_unavailable():
    store = _Store()
    instance = _instance()
    assert usage_summary(_deps(store, instance), "missing", "gm")["game"] == {
        "status": "unavailable", "game_key": "missing", "world_id": "", "world_name": "", "count": None, "books": [],
    }
    assert usage_summary(_deps(store, instance), "g1", "missing-character")["game"]["status"] == "unavailable"
    store.books.pop("game")
    assert usage_summary(_deps(store, instance), "g1", "gm")["game"]["status"] == "unavailable"
