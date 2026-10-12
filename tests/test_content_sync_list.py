"""Content sync discovery: ``POST /api/content/list``.

Protected contracts:
- owner-only, confirm header required, read-only (it binds no install id);
- every card and every Book is listed, whatever a Book is bound to;
- pages are ordered by canonical id and the cursor is opaque, kind-bound and
  strictly validated, as are kind and limit;
- each row carries the same ``state_token`` as ``/status`` and the
  ``locked_reason`` a push of its export gets from preview; export carries
  the same ``locked_reason`` in ``origin``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

import web_server
from src.webui.device_tokens import DEVICE_TOKENS_KEY
from tests.test_content_sync_api import (  # noqa: F401 - sync_app is a fixture
    CARD,
    CONFIRM,
    OWNER,
    PASSWORD,
    _items,
    _post,
    _push,
    _server_book,
    sync_app,
)

pytest_plugins = ["tests.webapi_harness"]

LIST = "/api/content/list"
DND_BODY = json.loads(
    (Path(__file__).resolve().parents[1] / "docs" / "content-sync" / "fixtures" / "card-dnd2024.chara_card_v3.json")
    .read_text(encoding="utf-8")
)["data"]["extensions"]["diceframe"]


def _write_cards(api, cards: list[dict]) -> None:
    api._character_cards_path.write_text(json.dumps(cards), encoding="utf-8")


async def _list_all(client, kind: str, *, limit: int | None = None) -> list[dict]:
    rows: list[dict] = []
    cursor = None
    for _ in range(100):
        body = {"kind": kind, "cursor": cursor, **({"limit": limit} if limit is not None else {})}
        status, page = await _post(client, LIST, body)
        assert status == 200, page
        rows.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            return rows
    raise AssertionError("pagination did not terminate")


# ---- Auth ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_auth_matrix(sync_app) -> None:
    app, *_ = sync_app
    token, _device = app[DEVICE_TOKENS_KEY].issue("phone", "install-a")
    body = {"kind": "lorebook"}
    async with TestClient(TestServer(app)) as client:
        owner, owner_body = await _post(client, LIST, body)
        device, _ = await _post(client, LIST, body, {"Authorization": f"Bearer {token}", **CONFIRM})
        anonymous, _ = await _post(client, LIST, body, CONFIRM)
        wrong, _ = await _post(client, LIST, body, {"Authorization": "Bearer nope", **CONFIRM})
        seat, _ = await _post(client, LIST, body, {"X-Seat-Token": "seat-token", **CONFIRM})
        room, _ = await _post(client, LIST, body, {"X-Room-Token": "room-token", **CONFIRM})
        share = await client.post(f"{LIST}?share=1&user=u1", json=body, headers=CONFIRM)
        bot, _ = await _post(client, LIST, body, {"X-Bot-Token": "bot-secret", **CONFIRM})
        unconfirmed = await client.post(LIST, json=body, headers={"Authorization": f"Bearer {PASSWORD}"})

    assert owner == 200 and owner_body["server_instance_id"].startswith("srv-")
    assert owner_body == {"ok": True, "items": [], "next_cursor": None,
                          "server_instance_id": owner_body["server_instance_id"]}
    assert device == 200
    assert anonymous == wrong == seat == room == share.status == 401
    assert bot == 403
    assert unconfirmed.status == 403


@pytest.mark.asyncio
async def test_list_requires_the_confirm_header_without_a_password(sync_app, monkeypatch) -> None:
    app, *_ = sync_app
    monkeypatch.setitem(web_server.STATE, "access_token", "")
    async with TestClient(TestServer(app)) as client:
        response = await client.post(LIST, data=json.dumps({"kind": "lorebook"}),
                                     headers={"Content-Type": "text/plain"})
        confirmed = await client.post(LIST, json={"kind": "lorebook"}, headers=CONFIRM)
    assert response.status == 403
    assert confirmed.status == 200


@pytest.mark.asyncio
async def test_list_reports_an_unavailable_server_identity(sync_app, tmp_path) -> None:
    app, *_ = sync_app
    (tmp_path / "server_identity.json").write_text("not json", encoding="utf-8")
    async with TestClient(TestServer(app)) as client:
        status, body = await _post(client, LIST, {"kind": "lorebook"})
    assert status == 503 and body["error_code"] == "SERVER_IDENTITY_UNAVAILABLE"


# ---- Coverage ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_book_is_listed_whatever_it_is_bound_to(sync_app) -> None:
    app, _api, lorebook = sync_app
    for book_id, scope in (
        ("book-world", ("world", "w1")), ("book-game", ("game", "web|room|gm")),
        ("book-character", ("character", "u1")), ("book-global", ("global", "")), ("book-unbound", None),
    ):
        _server_book(lorebook, book_id, entries={"town": "Town", "keep": "Keep"})
        if scope is not None:
            lorebook.bind_lorebook({"id": f"bind-{book_id}", "book_id": book_id,
                                    "scope_kind": scope[0], "scope_id": scope[1]})
    async with TestClient(TestServer(app)) as client:
        rows = await _list_all(client, "lorebook")

    assert [row["canonical_id"] for row in rows] == sorted(
        ["book-character", "book-game", "book-global", "book-unbound", "book-world"]
    )
    assert rows[0] == {
        "kind": "lorebook", "canonical_id": "book-character", "name": "Server book",
        "state_token": rows[0]["state_token"], "provenance": None, "locked_reason": None, "entries": 2,
    }


@pytest.mark.asyncio
async def test_every_card_is_listed_with_status_tokens(sync_app) -> None:
    app, *_ = sync_app
    async with TestClient(TestServer(app)) as client:
        _s, created, _ = await _push(client, _items())
        _s, second, _ = await _push(client, [_items()[0] | {"client_ref": "card-2"}])
        cards = await _list_all(client, "character_template")
        books = await _list_all(client, "lorebook")
        _s, status = await _post(client, "/api/content/status", {"items": [
            {"kind": row["kind"], "canonical_id": row["canonical_id"]} for row in [*cards, *books]
        ]})

    card_ids = sorted([created["items"][0]["canonical_id"], second["items"][0]["canonical_id"]])
    assert [row["canonical_id"] for row in cards] == card_ids
    assert {row["name"] for row in cards} == {CARD["character_name"]}
    assert all("entries" not in row and row["locked_reason"] is None for row in cards)
    assert [row["state_token"] for row in [*cards, *books]] == [row["state_token"] for row in status["items"]]
    assert [row["provenance"] for row in [*cards, *books]] == [row["provenance"] for row in status["items"]]
    assert cards[0]["provenance"]["source_id"] == "install-a"


# ---- Pagination ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_pages_are_ordered_and_never_repeat_an_item(sync_app) -> None:
    app, _api, lorebook = sync_app
    for name in ("b3", "b1", "b5", "b2", "b4"):
        _server_book(lorebook, name, entries={"town": "Town"})
    async with TestClient(TestServer(app)) as client:
        everything = await _list_all(client, "lorebook", limit=2)
        _s, first = await _post(client, LIST, {"kind": "lorebook", "limit": 2})
        # Between pages: one Book is added before the cursor, one after, and
        # one not yet listed is removed.
        _server_book(lorebook, "b0", entries={"town": "Town"})
        _server_book(lorebook, "b6", entries={"town": "Town"})
        lorebook.delete_lorebook("b4")
        rest: list[dict] = []
        cursor = first["next_cursor"]
        while cursor is not None:
            _s, page = await _post(client, LIST, {"kind": "lorebook", "limit": 2, "cursor": cursor})
            rest.extend(page["items"])
            cursor = page["next_cursor"]
        _s, last_page = await _post(client, LIST, {"kind": "lorebook", "limit": 5})

    assert [row["canonical_id"] for row in everything] == ["b1", "b2", "b3", "b4", "b5"]
    assert [row["canonical_id"] for row in first["items"]] == ["b1", "b2"]
    assert isinstance(first["next_cursor"], str)
    # b0 sorts before the cursor: missed until the next full pass. b4 is gone.
    assert [row["canonical_id"] for row in rest] == ["b3", "b5", "b6"]
    assert len(last_page["items"]) == 5 and isinstance(last_page["next_cursor"], str)


@pytest.mark.asyncio
async def test_list_requests_are_validated_strictly(sync_app) -> None:
    app, _api, lorebook = sync_app
    for name in ("b1", "b2"):
        _server_book(lorebook, name, entries={"town": "Town"})
    async with TestClient(TestServer(app)) as client:
        _s, page = await _post(client, LIST, {"kind": "lorebook", "limit": 1})
        book_cursor = page["next_cursor"]
        cases = {
            "cursor garbage": {"kind": "lorebook", "cursor": "not a cursor!"},
            "cursor base64 of junk": {"kind": "lorebook", "cursor": "e30"},
            "cursor not a string": {"kind": "lorebook", "cursor": 5},
            "cursor empty": {"kind": "lorebook", "cursor": ""},
            "cursor of another kind": {"kind": "character_template", "cursor": book_cursor},
            "kind unknown": {"kind": "world"},
            "kind not a kind": {"kind": "spaceship"},
            "kind missing": {},
            "kind not a string": {"kind": 3},
            "limit zero": {"kind": "lorebook", "limit": 0},
            "limit too large": {"kind": "lorebook", "limit": 501},
            "limit a string": {"kind": "lorebook", "limit": "5"},
            "limit a bool": {"kind": "lorebook", "limit": True},
            "limit a float": {"kind": "lorebook", "limit": 1.5},
            "unknown field": {"kind": "lorebook", "items": []},
        }
        results = {name: await _post(client, LIST, body) for name, body in cases.items()}
        smallest = await _post(client, LIST, {"kind": "lorebook", "limit": 1, "cursor": book_cursor})
        largest = await _post(client, LIST, {"kind": "lorebook", "limit": 500, "cursor": None})
        not_object = await client.post(LIST, json=["lorebook"], headers=OWNER)

    expected = {
        **{name: "CURSOR_INVALID" for name in cases if name.startswith("cursor")},
        "kind unknown": "KIND_NOT_SUPPORTED", "kind not a kind": "KIND_NOT_SUPPORTED",
        **{name: "REQUEST_INVALID" for name in cases
           if name.startswith(("limit", "unknown", "kind missing", "kind not a string"))},
    }
    assert {name: (status, body["error_code"]) for name, (status, body) in results.items()} == {
        name: (400, code) for name, code in expected.items()
    }
    assert all(body["server_instance_id"].startswith("srv-") for _status, body in results.values())
    assert smallest[0] == 200 and [row["canonical_id"] for row in smallest[1]["items"]] == ["b2"]
    assert smallest[1]["next_cursor"] is None
    assert largest[0] == 200 and len(largest[1]["items"]) == 2
    assert not_object.status == 400


# ---- Locks ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_locked_reason_matches_what_a_push_of_the_export_gets(sync_app) -> None:
    app, api, lorebook = sync_app
    free = {**CARD, "id": "card_free", "schema_version": 2}
    plugin = {**CARD, "id": "card_plugin", "character_name": "Pack hero",
              "source_plugin": "pack", "plugin_content_id": "hero"}
    ruleset = {**DND_BODY, "id": "card_ruleset"}
    _write_cards(api, [free, plugin, ruleset])
    _server_book(lorebook, "plugin-book", entries={"plugin": "From a pack"})
    _server_book(lorebook, "free-book", entries={"town": "Town"})
    async with TestClient(TestServer(app)) as client:
        cards = {row["canonical_id"]: row for row in await _list_all(client, "character_template")}
        books = {row["canonical_id"]: row for row in await _list_all(client, "lorebook")}
        _s, exported = await _post(client, "/api/content/export", {"items": [
            *({"kind": "character_template", "canonical_id": card_id} for card_id in sorted(cards)),
            *({"kind": "lorebook", "canonical_id": book_id} for book_id in sorted(books)),
        ]})
        pushed = [
            {"client_ref": f"pulled-{index}", "kind": row["kind"], "document": row["document"],
             "canonical_hint": row["origin"]["canonical_id"]}
            for index, row in enumerate(exported["items"])
        ]
        _s, preview = await _post(client, "/api/content/import/preview",
                                  {"source": {"kind": "device", "id": "install-z"}, "items": pushed})

    assert {card_id: row["locked_reason"] for card_id, row in cards.items()} == {
        "card_free": None, "card_plugin": "PLUGIN_CARD", "card_ruleset": "RULESET_CARD_UNSUPPORTED",
    }
    assert {book_id: row["locked_reason"] for book_id, row in books.items()} == {
        "free-book": None, "plugin-book": "PLUGIN_BOOK",
    }
    origins = {row["origin"]["canonical_id"]: row["origin"]["locked_reason"] for row in exported["items"]}
    assert origins == {**{k: v["locked_reason"] for k, v in cards.items()},
                       **{k: v["locked_reason"] for k, v in books.items()}}
    pushed_ids = {item["client_ref"]: item["canonical_hint"] for item in pushed}
    reasons = {
        pushed_ids[plan["client_ref"]]: plan["reason"] or None
        for plan in preview["items"] if plan["client_ref"] in pushed_ids
    }
    assert reasons == origins


@pytest.mark.asyncio
async def test_a_hinted_rules_aware_server_card_is_ruleset_card(sync_app) -> None:
    """The push order is shared: a free draft hinted at a rules-aware card is
    ``RULESET_CARD``; the rules-aware export itself is unsupported first."""

    app, api, _lorebook = sync_app
    _write_cards(api, [{**DND_BODY, "id": "card_ruleset"}])
    item = {"client_ref": "c", "kind": "character_template",
            "document": _items()[0]["document"], "canonical_hint": "card_ruleset"}
    async with TestClient(TestServer(app)) as client:
        _s, preview = await _post(client, "/api/content/import/preview",
                                  {"source": {"kind": "device", "id": "install-z"}, "items": [item]})
    assert preview["items"][0]["reason"] == "RULESET_CARD"
    assert preview["items"][0]["allowed"] == ["duplicate", "skip"]


@pytest.mark.asyncio
async def test_a_plugin_lock_wins_over_a_rules_aware_server_copy(sync_app) -> None:
    """Push order: a free draft hinted at a rules-aware plugin card is
    ``PLUGIN_CARD``, not ``RULESET_CARD``."""

    app, api, _lorebook = sync_app
    _write_cards(api, [{**DND_BODY, "id": "card_pack", "source_plugin": "pack", "plugin_content_id": "thorn"}])
    item = {"client_ref": "c", "kind": "character_template",
            "document": _items()[0]["document"], "canonical_hint": "card_pack"}
    async with TestClient(TestServer(app)) as client:
        _s, preview = await _post(client, "/api/content/import/preview",
                                  {"source": {"kind": "device", "id": "install-z"}, "items": [item]})
    assert preview["items"][0]["reason"] == "PLUGIN_CARD"
    assert preview["items"][0]["allowed"] == ["duplicate", "skip"]


def test_book_store_helpers_agree_with_the_entries(web_api) -> None:
    _api, lorebook, *_ = web_api
    _server_book(lorebook, "plugin-book", entries={"plugin": "From a pack", "town": "Town"})
    _server_book(lorebook, "free-book", entries={"town": "Town", "keep": "Keep"})
    lorebook.create_lorebook({"id": "empty-book", "name": "Empty"})
    for book_id in ("plugin-book", "free-book", "empty-book", "missing"):
        entries = lorebook.list_book_entries(book_id)
        assert lorebook.count_book_entries(book_id) == len(entries)
        assert lorebook.book_has_plugin_entries(book_id) == any(
            str(row.get("source_plugin") or "") for row in entries
        )
    assert lorebook.book_has_plugin_entries("plugin-book") is True


# ---- Read-only -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_writes_nothing(sync_app) -> None:
    app, api, lorebook = sync_app
    devices = app[DEVICE_TOKENS_KEY]
    token, device = devices.issue("phone")  # paired before install ids existed
    _write_cards(api, [{**CARD, "id": "card_free"}])
    _server_book(lorebook, "book", entries={"town": "Town"})
    cards_before = api._character_cards_path.read_bytes()
    revision_before = lorebook.get_lorebook("book")["revision"]
    headers = {"Authorization": f"Bearer {token}", **CONFIRM}
    async with TestClient(TestServer(app)) as client:
        for kind in ("character_template", "lorebook"):
            status, _body = await _post(client, LIST, {"kind": kind}, headers)
            assert status == 200

    assert next(row for row in devices.entries() if row["id"] == device["id"])["install_id"] == ""
    assert api._character_cards_path.read_bytes() == cards_before
    assert lorebook.get_lorebook("book")["revision"] == revision_before
