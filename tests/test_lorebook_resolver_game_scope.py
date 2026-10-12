"""Game-scoped Book bindings resolve for tuple game keys stored as 'a|b|c'."""

from __future__ import annotations

from types import SimpleNamespace

from src.lorebook.resolver import resolve_active_books


class _Store:
    def __init__(self, bindings):
        self._bindings = bindings

    def list_bindings(self):
        return list(self._bindings)


def test_game_binding_matches_joined_tuple_game_key() -> None:
    store = _Store([{
        "id": "binding:game:web|room|gm:lorebook:b1", "book_id": "b1",
        "scope_kind": "game", "scope_id": "web|room|gm", "role": "runtime", "order": 110,
    }])
    instance = SimpleNamespace(world_id="w1", game_id="", game_key=("web", "room", "gm"))

    refs = resolve_active_books(instance, store=store)

    assert [ref.book_id for ref in refs] == ["b1"]


def test_game_binding_for_another_game_is_ignored() -> None:
    store = _Store([{
        "id": "x", "book_id": "b2", "scope_kind": "game", "scope_id": "web|other|gm",
    }])
    instance = SimpleNamespace(world_id="w1", game_id="", game_key=("web", "room", "gm"))

    assert resolve_active_books(instance, store=store) == []
