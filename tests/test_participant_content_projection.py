"""Track R6-b: participant read paths consume the content projection.

Private-data isolation contract (ENGINEERING_RULES §15): a seat never sees
GM-private lore, another character's entries or another character's Book; the
GM keeps the full view; anyone else (party audience, lobby visitor) sees only
public lore.  P2P guests (owner + preview + delegate) and bots acting for a
seat are seats.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

import web_server
from src.commands.kp_questions import KPQuestionResponder
from src.content_modules.projection import ContentProjectionService
from src.engine.game_instance import GameInstance
from src.engine.participant_view import Viewer
from src.lorebook.store import LorebookStore
from src.webui.routes.maps import register_maps
from src.webui.services import maps as map_service
from test_game_query_routes_http import (
    _make_app,
    _make_game,
    _owner,
    _owner_password,  # noqa: F401
    play_env,  # noqa: F401
)
from src.engine.modules import room_access


WORLD = "template_world"


def _seed_lore(store: LorebookStore, world_id: str = WORLD) -> None:
    """One world with every audience, plus a character Book for each seat."""

    if store.get_world(world_id) is None:
        store.create_world(world_id, world_id)
    for book_id, uid in (("book-p1", "p1"), ("book-p2", "p2")):
        store.create_lorebook({"id": book_id, "name": book_id})
        store.bind_lorebook({
            "id": f"binding:{book_id}", "book_id": book_id,
            "scope_kind": "character", "scope_id": uid,
            "role": "secondary", "order": 110,
        })
    world_book = f"world:{world_id}"
    rows = [
        (world_book, {"id": "town", "name": "Town", "type": "location", "visible_to": ["*"],
                      "content": "Market square", "connected_to": ["vault", "inn"]}),
        (world_book, {"id": "inn", "name": "Inn", "type": "location", "visible_to": ["party"],
                      "content": "Warm beds", "connected_to": ["town"]}),
        (world_book, {"id": "vault", "name": "Hidden Vault", "type": "location",
                      "content": "GM SECRET: the lich sleeps here", "connected_to": ["town"]}),
        (world_book, {"id": "p1-den", "name": "Alpha Den", "type": "location", "visible_to": ["p1"],
                      "content": "Only p1 knows"}),
        (world_book, {"id": "p2-den", "name": "Beta Den", "type": "location", "visible_to": ["乙"],
                      "content": "Only 乙 knows"}),
        ("book-p1", {"id": "p1-book-loc", "name": "Alpha Memory", "type": "location",
                     "visible_to": ["*"], "content": "p1 book"}),
        ("book-p2", {"id": "p2-book-loc", "name": "Beta Memory", "type": "location",
                     "visible_to": ["*"], "content": "p2 book"}),
        (world_book, {"id": "gm-lore", "name": "Lich", "type": "npc", "keywords": ["lich"],
                      "content": "GM SECRET lich"}),
    ]
    for book_id, entry in rows:
        store.add_book_entry(book_id, entry)


GM_ALL = {"town", "inn", "vault", "p1-den", "p2-den"}
P1_VIEW = {"town", "inn", "p1-den", "p1-book-loc"}
P2_VIEW = {"town", "inn", "p2-den", "p2-book-loc"}
PUBLIC_VIEW = {"town", "inn"}


@pytest.fixture
def lore_store(tmp_path):
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    _seed_lore(store)
    try:
        yield store
    finally:
        store.close()


def _instance(store: LorebookStore) -> GameInstance:
    instance = GameInstance(game_key=("web", "r6b", "web"), world_id=WORLD)
    instance.gm_uid = "gm_user"
    instance.players = {
        "p1": {"character_name": "甲", "character_sheet": {}},
        "p2": {"character_name": "乙", "character_sheet": {}},
    }
    # Both seats act this round: the GM runtime view resolves their Books.
    instance.action_actor_uids = ["p1", "p2"]  # type: ignore[attr-defined]
    return instance


def _ids(entries: list[dict[str, Any]]) -> set[str]:
    return {str(entry.get("id")) for entry in entries}


# ---- ContentProjectionService.for_viewer / for_party -----------------------


def test_for_viewer_projects_each_participant_kind(lore_store) -> None:
    service = ContentProjectionService(lore_store)
    instance = _instance(lore_store)

    gm = _ids(service.for_viewer(instance, Viewer("gm", "gm_user"), entry_type="location"))
    assert GM_ALL | {"p1-book-loc", "p2-book-loc"} <= gm

    assert _ids(service.for_viewer(instance, Viewer("seat", "p1"), entry_type="location")) == P1_VIEW
    # The seat's character name is the secondary match token (乙 → p2).
    assert _ids(service.for_viewer(instance, Viewer("seat", "p2"), entry_type="location")) == P2_VIEW
    assert _ids(service.for_viewer(instance, Viewer("outsider", "stranger"), entry_type="location")) == PUBLIC_VIEW
    assert _ids(service.for_party(instance, entry_type="location")) == PUBLIC_VIEW


# ---- Map (service level, both store paths) ---------------------------------


def _map_dependencies(store: LorebookStore, instance: GameInstance, *, projection: bool):
    return map_service.MapDependencies(
        get_instance=lambda _key: instance,
        parse_game_key=lambda key: (key,),
        list_lore_entries=store.list_entries,
        list_map_assets=lambda _world_id: {"maps": [], "locations": [], "icons": [], "scenes": []},
        validate_background_selection=lambda _value: {"kind": "auto"},
        save_instance=None,  # type: ignore[arg-type]
        load_world_template=lambda _world_id: None,
        map_background_file=lambda _asset_id: None,
        generated_image_file=lambda _asset_id: None,
        content_projection=ContentProjectionService(store) if projection else None,
    )


@pytest.mark.parametrize("projection", [True, False], ids=["projection", "compat-store"])
def test_map_is_projected_per_viewer(lore_store, projection) -> None:
    instance = _instance(lore_store)
    deps = _map_dependencies(lore_store, instance, projection=projection)

    def view(viewer: Viewer) -> dict[str, Any]:
        return map_service.get_map_locations(deps, "g", viewer=viewer)

    gm = view(Viewer("gm", "gm_user"))
    gm_ids = {loc["id"] for loc in gm["locations"]}
    assert GM_ALL <= gm_ids
    vault = next(loc for loc in gm["locations"] if loc["id"] == "vault")
    assert "lich" in vault["content"]
    # The GM map keeps every edge.
    assert next(loc for loc in gm["locations"] if loc["id"] == "town")["connected_to"] == ["vault", "inn"]

    expected_p1 = P1_VIEW if projection else P1_VIEW - {"p1-book-loc"}
    p1 = view(Viewer("seat", "p1"))
    assert {loc["id"] for loc in p1["locations"]} == expected_p1
    serialized = repr(p1)
    assert "GM SECRET" not in serialized and "Hidden Vault" not in serialized
    assert "Beta" not in serialized and "Only 乙 knows" not in serialized
    # An edge to a hidden location would name it.
    assert next(loc for loc in p1["locations"] if loc["id"] == "town")["connected_to"] == ["inn"]

    expected_p2 = P2_VIEW if projection else P2_VIEW - {"p2-book-loc"}
    assert {loc["id"] for loc in view(Viewer("seat", "p2"))["locations"]} == expected_p2
    assert {loc["id"] for loc in view(Viewer("outsider", ""))["locations"]} == PUBLIC_VIEW


# ---- Map over HTTP: identity resolution for every transport -----------------


@pytest.fixture
def map_env(play_env):
    store = play_env.api._lore
    _seed_lore(store)
    game_key, instance = _make_game(play_env, "r6bmap")
    instance.players["p2"] = {"character_name": "乙", "character_sheet": {}}
    instance.action_actor_uids = ["p1", "p2"]  # type: ignore[attr-defined]
    # Production wires the handler's projection; this harness has no handler.
    play_env.api._map_dependencies = dataclasses.replace(
        play_env.api._map_dependencies, content_projection=ContentProjectionService(store),
    )
    app = _make_app(play_env)
    register_maps(app)
    return app, game_key, instance


async def _map_ids(client, url: str, headers: dict[str, str]) -> set[str]:
    response = await client.get(url, headers=headers)
    body = await response.json()
    assert response.status == 200, body
    return {loc["id"] for loc in body["locations"]}


@pytest.mark.asyncio
async def test_map_route_projects_for_owner_seat_p2p_and_bot(map_env, monkeypatch) -> None:
    app, key, instance = map_env
    monkeypatch.setitem(web_server.STATE, "bot_token", "bot-secret")
    url = f"/api/games/{key}/map"
    async with TestClient(TestServer(app)) as client:
        owner = await _map_ids(client, url, _owner())
        seat = await _map_ids(
            client, f"{url}?share=1",
            {"X-Seat-Token": room_access.issue_seat_token(instance, "p1")},
        )
        preview = await _map_ids(client, f"{url}?user=p1&share=1", _owner())
        p2p_guest = await _map_ids(client, f"{url}?user=p2&share=1&delegate=1", _owner())
        bot = await _map_ids(client, url, {"X-Bot-Token": "bot-secret", "X-Bot-Actor": "p1"})

    assert GM_ALL <= owner
    assert seat == P1_VIEW
    assert preview == P1_VIEW
    assert p2p_guest == P2_VIEW
    assert bot == P1_VIEW


# ---- KP question: the private answer only gets the questioner's projection --


class _GmScopedRetriever:
    """Stands in for the shared retriever after a concurrent GM round rebuilt it.

    The retriever is shared with GM rounds (its matcher is rebuilt for the GM
    view across an await), so its hits are not a permission boundary.
    """

    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self.hits = hits

    async def retrieve(self, *_args, **_kwargs) -> list[dict[str, Any]]:
        return [dict(hit) for hit in self.hits]


class _Composer:
    def __init__(self) -> None:
        self.lore: list[dict[str, Any]] = []

    def load_rule_context(self, *_args, **_kwargs):
        return SimpleNamespace(rule_appendix="", world_data=None)

    async def build_player_safe_context(self, _instance, _prompt, lore, *_args, **_kwargs) -> str:
        self.lore = list(lore)
        return "context"


class _Llm:
    default = "fake"

    async def call(self, *_args, **_kwargs):
        return SimpleNamespace(narration="answer", content="", total_tokens=1, provider_used="fake")


def _kp(lore_store, *, projection: bool) -> tuple[KPQuestionResponder, _Composer]:
    gm_hits = [
        entry
        for book in ("world:" + WORLD, "book-p1", "book-p2")
        for entry in lore_store.list_book_entries(book)
    ]
    composer = _Composer()
    responder = KPQuestionResponder(
        _Llm(), matcher=None, prompt_composer=composer,
        load_world_template=lambda *_a: None,
        ensure_matcher_for_world=lambda *_a: None,
        lore_retriever=_GmScopedRetriever(gm_hits),
        content_projection=ContentProjectionService(lore_store) if projection else None,
    )
    return responder, composer


@pytest.mark.asyncio
async def test_kp_private_answer_uses_only_the_questioners_projection(lore_store) -> None:
    responder, composer = _kp(lore_store, projection=True)
    instance = _instance(lore_store)

    await responder.answer(instance, "p1", "where?", visibility="private")
    lore = _ids(composer.lore)
    assert lore == P1_VIEW
    assert not lore & {"vault", "gm-lore", "p2-den", "p2-book-loc"}

    await responder.answer(instance, "p2", "where?", visibility="private")
    assert _ids(composer.lore) == P2_VIEW


@pytest.mark.asyncio
async def test_kp_party_answer_uses_only_public_projection(lore_store) -> None:
    responder, composer = _kp(lore_store, projection=True)
    await responder.answer(_instance(lore_store), "p1", "where?", visibility="party")
    assert _ids(composer.lore) == PUBLIC_VIEW


@pytest.mark.asyncio
async def test_kp_without_projection_still_applies_shared_predicate(lore_store) -> None:
    responder, composer = _kp(lore_store, projection=False)
    await responder.answer(_instance(lore_store), "p1", "where?", visibility="private")
    lore = _ids(composer.lore)
    assert not lore & {"vault", "gm-lore", "p2-den"}


# ---- Built-in templates: reviewed GM-only locations stay off a seat's map ---
#
# Each of these entries is the secret half of a split (or a deliberately
# sealed site); the common knowledge about the place lives in a public parent
# location that a seat does see.  ``None`` = no public parent location.

_TEMPLATE_SECRET_LOCATIONS = [
    ("coc_horror.json", "loc_howard_house_oddities", "loc_howard_house"),
    ("coc_horror_en.json", "loc_howard_residence_oddities", "loc_howard_residence"),
    ("default_fantasy.json", "loc_ancient_tower", "loc_blackpine_forest"),
    ("greymoor.json", "loc_old_shrine", None),
    ("scifi_cyberpunk.json", "loc_shibuya_market_entrance", "loc_shibuya_market"),
    ("scifi_cyberpunk.json", "loc_mkg_datacenter", "loc_cloud_tower"),
    ("scifi_cyberpunk_en.json", "loc_shibuya_market_entrance", "loc_shibuya_market"),
    ("scifi_cyberpunk_en.json", "loc_mkg_datacenter", "loc_cloudspire"),
    ("zhongshi_fantasy.json", "loc_ancient_cave", "loc_kumu_cliff"),
    ("zhongshi_fantasy_en.json", "loc_deadwood_cliff_caves", "loc_deadwood_cliff"),
]


@pytest.mark.parametrize(("filename", "secret_id", "public_parent"), _TEMPLATE_SECRET_LOCATIONS)
def test_builtin_template_secret_locations_stay_off_seat_map(
    tmp_path, filename, secret_id, public_parent,
) -> None:
    import json
    from pathlib import Path

    from src.lorebook.bootstrap import ensure_world_from_template

    template = json.loads(
        (Path(__file__).resolve().parents[1] / "templates" / "worlds" / filename)
        .read_text(encoding="utf-8")
    )
    world_id = str(template["world_id"])
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    try:
        ensure_world_from_template(store, world_id, template)
        instance = GameInstance(game_key=("web", "tpl", "web"), world_id=world_id)
        instance.gm_uid = "gm_user"
        instance.players = {"p1": {"character_name": "甲", "character_sheet": {}}}
        deps = _map_dependencies(store, instance, projection=True)

        seat = {
            loc["id"] for loc in map_service.get_map_locations(
                deps, "g", viewer=Viewer("seat", "p1"),
            )["locations"]
        }
        gm = {
            loc["id"] for loc in map_service.get_map_locations(
                deps, "g", viewer=Viewer("gm", "gm_user"),
            )["locations"]
        }
    finally:
        store.close()

    assert secret_id in gm
    assert secret_id not in seat
    if public_parent is not None:
        assert public_parent in seat


# ---- Map: visibility hints and plugin stand-ins -----------------------------


def _plugin_map_dependencies(store, instance, plugin_locations):
    deps = _map_dependencies(store, instance, projection=True)
    return dataclasses.replace(
        deps,
        list_map_assets=lambda _world_id: {
            "maps": [], "locations": plugin_locations, "icons": [], "scenes": [],
        },
    )


def test_plugin_location_cannot_stand_in_for_hidden_lore_location(lore_store) -> None:
    instance = _instance(lore_store)
    deps = _plugin_map_dependencies(lore_store, instance, [
        {"id": "vault", "name": "Vault (plugin)", "content": "plugin art"},
        {"id": "x", "name": "Hidden Vault", "content": "same name"},
        {"id": "harbor", "name": "Harbor", "content": "plugin harbor"},
    ])

    seat = {loc["id"] for loc in map_service.get_map_locations(
        deps, "g", viewer=Viewer("seat", "p1"))["locations"]}
    gm = map_service.get_map_locations(deps, "g", viewer=Viewer("gm", "gm_user"))["locations"]

    assert "vault" not in seat and "x" not in seat
    assert "harbor" in seat
    vault = next(loc for loc in gm if loc["id"] == "vault")
    assert vault["source"] == "lorebook"


def test_map_visibility_hints_for_empty_player_view(tmp_path) -> None:
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    try:
        store.create_world(WORLD, WORLD)
        store.add_book_entry(f"world:{WORLD}", {
            "id": "keep", "name": "Keep", "type": "location", "content": "GM only",
        })
        instance = _instance(store)
        deps = _map_dependencies(store, instance, projection=True)

        seat = map_service.get_map_locations(deps, "g", viewer=Viewer("seat", "p1"))
        gm = map_service.get_map_locations(deps, "g", viewer=Viewer("gm", "gm_user"))
        assert seat["locations"] == []
        assert seat["visibility_hint"] == "no_visible_locations"
        assert {loc["id"] for loc in gm["locations"]} == {"keep"}
        assert gm["visibility_hint"] == "players_see_no_locations"

        store.add_book_entry(f"world:{WORLD}", {
            "id": "square", "name": "Square", "type": "location", "visible_to": ["*"],
            "content": "Public",
        })
        assert map_service.get_map_locations(
            deps, "g", viewer=Viewer("gm", "gm_user"))["visibility_hint"] == ""
        assert map_service.get_map_locations(
            deps, "g", viewer=Viewer("seat", "p1"))["visibility_hint"] == ""
    finally:
        store.close()


# ---- Projection on a store without any binding (legacy) --------------------


class _UnboundStore:
    """A store exposing Book CRUD but holding no binding at all (legacy)."""

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self.entries = entries

    def list_bindings(self, **_filters) -> list[dict[str, Any]]:
        return []

    def primary_world_book_id(self, world_id: str) -> str:
        return f"world:{world_id}"

    def list_book_entries(self, book_id: str) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self.entries] if book_id == f"world:{WORLD}" else []


_UNBOUND_ENTRIES = [
    {"id": "pub", "name": "Square", "type": "location", "visible_to": ["*"]},
    {"id": "mine", "name": "Den", "type": "location", "visible_to": ["p1"]},
    {"id": "theirs", "name": "Lair", "type": "location", "visible_to": ["p2"]},
    {"id": "secret", "name": "Vault", "type": "location"},
]


def test_projection_falls_back_to_world_entries_on_unbound_store() -> None:
    service = ContentProjectionService(_UnboundStore(_UNBOUND_ENTRIES))
    instance = _instance(None)  # type: ignore[arg-type]

    assert _ids(service.for_game(instance)) == {"pub", "mine", "theirs", "secret"}
    assert _ids(service.for_character(instance, "p1", viewer_name="甲")) == {"pub", "mine"}
    assert _ids(service.for_party(instance)) == {"pub"}


@pytest.mark.asyncio
async def test_kp_keeps_visible_lore_on_unbound_store() -> None:
    composer = _Composer()
    responder = KPQuestionResponder(
        _Llm(), matcher=None, prompt_composer=composer,
        load_world_template=lambda *_a: None,
        ensure_matcher_for_world=lambda *_a: None,
        lore_retriever=_GmScopedRetriever(_UNBOUND_ENTRIES),
        content_projection=ContentProjectionService(_UnboundStore(_UNBOUND_ENTRIES)),
    )
    instance = _instance(None)  # type: ignore[arg-type]

    await responder.answer(instance, "p1", "where?", visibility="private")
    assert _ids(composer.lore) == {"pub", "mine"}
    await responder.answer(instance, "p1", "where?", visibility="party")
    assert _ids(composer.lore) == {"pub"}
