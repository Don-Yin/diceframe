"""Unified content sync API (PR G2d): ``/api/content/import|export``.

Protected contracts:
- owner-only: master password or paired-device token; anonymous, bot/plugin
  tokens and share callers are refused;
- a paired device may declare only its own install id (registered at pairing
  or bound on first use; the owner can clear it); the master-password owner
  may declare any device;
- limits are enforced before any planning with 413 and an error code;
- push -> re-push (unchanged) -> modify -> update, across kinds in one plan;
- two installs keep two copies; canonical_hint adopts an owner card;
- export returns portable documents with an origin envelope, and importing
  that export back is ``unchanged``.
"""

from __future__ import annotations

import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import web_server
from src.content_modules.adapters.character_card_v3 import write_card_v3
from src.webui.access_password import hash_access_password
from src.webui.device_tokens import DEVICE_TOKENS_KEY, DeviceTokenStore
from src.webui.login_audit import LOGIN_AUDIT_KEY, LoginAuditStore
from src.webui.pairing import PairingService
from src.webui.routes.content import register_content
from src.webui.routes.pairing import PAIRING_SERVICE_KEY, register_pairing
from src.webui.server_identity import SERVER_IDENTITY_KEY, ServerIdentityStore
from src.webui.services import character_cards

pytest_plugins = ["tests.webapi_harness"]

PASSWORD = "correct-password"
CONFIRM = {"X-TRPG-Confirm": "true"}
OWNER = {"Authorization": f"Bearer {PASSWORD}", **CONFIRM}
PHONE = {"kind": "device", "id": "install-a"}
TABLET = {"kind": "device", "id": "install-b"}

CARD = {
    "schema_version": 2, "character_name": "Mira", "race": "Elf", "class": "Ranger",
    "background": "Border woods.", "attributes": {"str": 12}, "skills": [], "gold": 30,
    "rule_id": "freeform_fantasy", "language": "en",
}
BOOK_ENTRIES = {"town": "Town lore", "keep": "Keep lore"}


def _lorebook(name: str, entries: dict[str, str]) -> dict:
    return {"spec": "lorebook_v3", "data": {"lorebook": {"name": name, "entries": [
        {"id": key, "name": key, "content": content, "keys": [key]} for key, content in entries.items()
    ]}}}


def _card_doc(body: dict = CARD, *, book: dict | None = None) -> dict:
    return write_card_v3(body, character_book=book)


def _items(card: dict | None = None, book: dict | None = None) -> list[dict]:
    return [
        {"client_ref": "card-1", "kind": "character_template", "format": "chara_card_v3",
         "document": card or _card_doc()},
        {"client_ref": "book-1", "kind": "lorebook", "format": "lorebook_v3",
         "document": book or _lorebook("Atlas", BOOK_ENTRIES)},
    ]


@pytest.fixture
def sync_app(web_api, tmp_path, monkeypatch):
    api, lorebook, *_ = web_api
    monkeypatch.setitem(web_server.STATE, "access_token", hash_access_password(PASSWORD))
    monkeypatch.setitem(web_server.STATE, "bot_token", "bot-secret")
    app = web.Application(middlewares=[web_server.auth_middleware])
    app["api"] = api
    app[LOGIN_AUDIT_KEY] = LoginAuditStore(tmp_path)
    app[DEVICE_TOKENS_KEY] = DeviceTokenStore(tmp_path)
    app[SERVER_IDENTITY_KEY] = ServerIdentityStore(tmp_path)
    app[PAIRING_SERVICE_KEY] = PairingService(app[DEVICE_TOKENS_KEY], audit=app[LOGIN_AUDIT_KEY])
    register_content(app)
    register_pairing(app)
    return app, api, lorebook


async def _post(client, path: str, body: dict, headers: dict | None = None):
    response = await client.post(path, json=body, headers=headers if headers is not None else OWNER)
    return response.status, await response.json()


async def _preview(client, items: list[dict], *, source: dict = PHONE, headers: dict | None = None):
    return await _post(client, "/api/content/import/preview", {"source": source, "items": items}, headers)


async def _push(client, items: list[dict], *, source: dict = PHONE, decisions: dict | None = None,
                headers: dict | None = None):
    status, preview = await _preview(client, items, source=source, headers=headers)
    assert status == 200, preview
    body = {"source": source, "items": items, "plan_digest": preview["plan_digest"],
            "decisions": decisions or {}}
    status, result = await _post(client, "/api/content/import/commit", body, headers)
    return status, result, preview


def _by_ref(rows: list[dict]) -> dict[str, dict]:
    return {row["client_ref"]: row for row in rows}


# ---- Auth ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_matrix(sync_app) -> None:
    app, *_ = sync_app
    token, _device = app[DEVICE_TOKENS_KEY].issue("phone", "install-a")
    body = {"source": PHONE, "items": _items()}
    async with TestClient(TestServer(app)) as client:
        anonymous, _ = await _post(client, "/api/content/import/preview", body, CONFIRM)
        wrong, _ = await _post(client, "/api/content/import/preview", body,
                               {"Authorization": "Bearer nope", **CONFIRM})
        bot, _ = await _post(client, "/api/content/import/preview", body,
                             {"X-Bot-Token": "bot-secret", **CONFIRM})
        seat, _ = await _post(client, "/api/content/export", {"items": []},
                              {"X-Seat-Token": "seat-token", **CONFIRM})
        owner, _ = await _post(client, "/api/content/import/preview", body)
        device, _ = await _post(client, "/api/content/import/preview", body,
                                {"Authorization": f"Bearer {token}", **CONFIRM})

    assert anonymous == 401 and wrong == 401 and seat == 401
    assert bot == 403
    assert owner == 200 and device == 200


# ---- Limits ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_limits_are_413_with_codes(sync_app, monkeypatch) -> None:
    from src.webui.routes import content as content_routes

    app, *_ = sync_app
    huge_entry = {"town": "x" * (33 * 1024)}
    many_entries = {f"e{i}": "lore" for i in range(2001)}
    async with TestClient(TestServer(app)) as client:
        # The real 8 MB limit, checked on a body that is just over it.
        assert content_routes.MAX_BODY_BYTES == 8 * 1024 * 1024
        monkeypatch.setattr(content_routes, "MAX_BODY_BYTES", 1024)
        big = await client.post(
            "/api/content/import/preview", data=b"{" + b" " * 2048 + b"}",
            headers={**OWNER, "Content-Type": "application/json"},
        )
        big_body = await big.json()
        monkeypatch.setattr(content_routes, "MAX_BODY_BYTES", 8 * 1024 * 1024)
        too_many_items = await _preview(client, [_items()[1] | {"client_ref": f"b{i}"} for i in range(51)])
        too_many_entries = await _preview(client, [_items(book=_lorebook("Big", many_entries))[1]])
        entry_too_large = await _preview(client, [_items(book=_lorebook("Big", huge_entry))[1]])
        card_book_entries = await _preview(
            client, [_items(card=_card_doc(book={"entries": [{"id": f"e{i}", "content": "x"} for i in range(2001)]}))[0]],
        )
        export_items = await _post(client, "/api/content/export",
                                   {"items": [{"kind": "lorebook", "canonical_id": "x"}] * 51})

    assert big.status == 413 and big_body["error_code"] == "BODY_TOO_LARGE"
    assert too_many_items == (413, too_many_items[1]) and too_many_items[1]["error_code"] == "TOO_MANY_ITEMS"
    assert too_many_entries[0] == 413 and too_many_entries[1]["error_code"] == "TOO_MANY_ENTRIES"
    assert entry_too_large[0] == 413 and entry_too_large[1]["error_code"] == "ENTRY_TOO_LARGE"
    assert card_book_entries[0] == 413 and card_book_entries[1]["error_code"] == "TOO_MANY_ENTRIES"
    assert export_items[0] == 413 and export_items[1]["error_code"] == "TOO_MANY_ITEMS"


# ---- Push lifecycle ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_repush_unchanged_modify_update(sync_app) -> None:
    app, api, lorebook = sync_app
    async with TestClient(TestServer(app)) as client:
        status, created, preview = await _push(client, _items())
        assert status == 200, created
        assert [row["action"] for row in preview["items"]] == ["create", "create"]
        rows = _by_ref(created["items"])
        card_id, book_id = rows["card-1"]["canonical_id"], rows["book-1"]["canonical_id"]
        assert rows["card-1"]["status"] == rows["book-1"]["status"] == "created"
        assert rows["card-1"]["state_token"] and rows["book-1"]["state_token"]

        status, again = await _preview(client, _items())
        assert [row["action"] for row in again["items"]] == ["unchanged", "unchanged"]

        edited = _items(card=_card_doc({**CARD, "gold": 99}), book=_lorebook("Atlas", {"town": "Town v2"}))
        status, preview_edit = await _preview(client, edited)
        assert [row["action"] for row in preview_edit["items"]] == ["update", "update"]
        assert _by_ref(preview_edit["items"])["book-1"]["existing"]["entries_remove"] == 1
        missing = await _post(client, "/api/content/import/commit", {
            "source": PHONE, "items": edited, "plan_digest": preview_edit["plan_digest"],
        })
        assert missing[0] == 400 and missing[1]["error_code"] == "DECISION_REQUIRED"

        status, updated, _ = await _push(client, edited, decisions={"card-1": "update", "book-1": "update"})

    assert status == 200, updated
    rows = _by_ref(updated["items"])
    assert rows["card-1"]["canonical_id"] == card_id and rows["card-1"]["status"] == "updated"
    assert rows["book-1"]["canonical_id"] == book_id and rows["book-1"]["entries_removed"] == 1
    assert next(c for c in api.list_character_cards()["cards"] if c["id"] == card_id)["gold"] == 99
    assert [row["content"] for row in lorebook.list_book_entries(book_id)] == ["Town v2"]


@pytest.mark.asyncio
async def test_a_stale_plan_is_409_with_a_fresh_preview(sync_app) -> None:
    app, api, _lorebook = sync_app
    async with TestClient(TestServer(app)) as client:
        _status, created, _ = await _push(client, _items())
        card_id = _by_ref(created["items"])["card-1"]["canonical_id"]
        edited = _items(card=_card_doc({**CARD, "gold": 5}))
        _status, seen = await _preview(client, edited)
        api.update_character_card(card_id, {"background": "Edited on the server"})
        status, stale = await _post(client, "/api/content/import/commit", {
            "source": PHONE, "items": edited, "plan_digest": seen["plan_digest"],
            "decisions": {"card-1": "update", "book-1": "update"},
        })

    assert status == 409 and stale["error_code"] == "PLAN_STALE"
    assert stale["preview"]["plan_digest"] != seen["plan_digest"]
    assert _by_ref(stale["preview"]["items"])["card-1"]["existing"]["server_modified"] is True


@pytest.mark.asyncio
async def test_two_installs_keep_two_copies(sync_app) -> None:
    app, api, lorebook = sync_app
    async with TestClient(TestServer(app)) as client:
        _s, first, _ = await _push(client, _items(), source=PHONE)
        _s, second, _ = await _push(client, _items(), source=TABLET)

    first_rows, second_rows = _by_ref(first["items"]), _by_ref(second["items"])
    assert second_rows["card-1"]["status"] == second_rows["book-1"]["status"] == "created"
    assert first_rows["card-1"]["canonical_id"] != second_rows["card-1"]["canonical_id"]
    assert len(api.list_character_cards()["cards"]) == 2
    assert len(lorebook.list_lorebooks()) == 2


@pytest.mark.asyncio
async def test_canonical_hint_adopts_an_owner_card(sync_app) -> None:
    app, api, _lorebook = sync_app
    saved = character_cards.save_character_card(api._character_card_dependencies, dict(CARD))
    owner_card = saved["card"]["id"]
    item = {"client_ref": "card-1", "kind": "character_template",
            "document": _card_doc({**CARD, "gold": 12}), "canonical_hint": owner_card}
    async with TestClient(TestServer(app)) as client:
        _s, preview = await _preview(client, [item])
        assert preview["items"][0]["existing"]["matched_by"] == "hint"
        assert preview["items"][0]["allowed"] == ["update", "duplicate", "skip"]
        _s, adopted, _ = await _push(client, [item], decisions={"card-1": "update"})
        plain = {k: v for k, v in item.items() if k != "canonical_hint"}
        _s, followed = await _preview(client, [plain])

    assert adopted["items"][0]["canonical_id"] == owner_card
    card = next(c for c in api.list_character_cards()["cards"] if c["id"] == owner_card)
    assert card["gold"] == 12 and card["provenance"]["link"] == "tracked"
    assert followed["items"][0]["existing"]["matched_by"] == "identity"
    assert followed["items"][0]["action"] == "unchanged"


@pytest.mark.asyncio
async def test_request_level_errors_fail_closed(sync_app) -> None:
    app, *_ = sync_app
    world = {"client_ref": "w1", "kind": "world", "document": {}}
    duplicate = [_items()[1], _items()[1]]
    clash = [_items(card=_card_doc(book={"entries": []}))[0], _items()[1] | {"client_ref": "card-1.book"}]
    async with TestClient(TestServer(app)) as client:
        kind = await _preview(client, [world])
        twice = await _preview(client, duplicate)
        book_ref = await _preview(client, clash)
        bad_ref = await _preview(client, [_items()[1] | {"client_ref": "has space"}])
        bad_source = await _preview(client, _items(), source={"kind": "plugin", "id": "x"})

    assert kind[0] == 400 and kind[1]["error_code"] == "KIND_NOT_SUPPORTED"
    assert twice[1]["error_code"] == "DUPLICATE_CLIENT_REF"
    assert book_ref[1]["error_code"] == "DUPLICATE_CLIENT_REF"
    assert bad_ref[1]["error_code"] == "CLIENT_REF_INVALID"
    assert bad_source[1]["error_code"] == "IMPORT_SOURCE_INVALID"


# ---- Paired-device identity ------------------------------------------------------


async def _pair(client, install_id: str | None = None) -> tuple[str, str]:
    issued = await client.post("/api/pairing", headers=OWNER)
    code = (await issued.json())["code"]
    body = {"code": code, **({"install_id": install_id} if install_id is not None else {})}
    claimed = await client.post("/api/pairing/claim", json=body, headers=CONFIRM)
    payload = await claimed.json()
    return payload["device_token"], payload["device_id"]


def _as(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", **CONFIRM}


@pytest.mark.asyncio
async def test_pairing_registers_the_install_id(sync_app) -> None:
    app, *_ = sync_app
    async with TestClient(TestServer(app)) as client:
        token, device_id = await _pair(client, "install-a")
        own = await _preview(client, _items(), source=PHONE, headers=_as(token))
        other = await _preview(client, _items(), source=TABLET, headers=_as(token))
        invalid = await client.post("/api/pairing/claim", json={"code": "x", "install_id": "has space"},
                                    headers=CONFIRM)
        invalid_body = await invalid.json()

    assert own[0] == 200
    assert other[0] == 403 and other[1]["error_code"] == "SOURCE_NOT_THIS_DEVICE"
    assert invalid.status == 400 and invalid_body["error_code"] == "INSTALL_ID_INVALID"
    assert app[DEVICE_TOKENS_KEY].entries()[0]["install_id"] == "install-a"


@pytest.mark.asyncio
async def test_a_device_paired_earlier_binds_on_first_use(sync_app) -> None:
    app, *_ = sync_app
    async with TestClient(TestServer(app)) as client:
        token, _device_id = await _pair(client)  # no install id at pairing
        assert app[DEVICE_TOKENS_KEY].entries()[0]["install_id"] == ""
        first = await _preview(client, _items(), source=TABLET, headers=_as(token))
        mismatch = await _preview(client, _items(), source=PHONE, headers=_as(token))

    assert first[0] == 200
    assert app[DEVICE_TOKENS_KEY].entries()[0]["install_id"] == "install-b"
    assert mismatch[0] == 403 and mismatch[1]["error_code"] == "SOURCE_NOT_THIS_DEVICE"


@pytest.mark.asyncio
async def test_the_password_owner_may_declare_any_device(sync_app) -> None:
    app, *_ = sync_app
    app[DEVICE_TOKENS_KEY].issue("phone", "install-a")
    async with TestClient(TestServer(app)) as client:
        phone = await _preview(client, _items(), source=PHONE)
        tablet = await _preview(client, _items(), source=TABLET)
    assert phone[0] == 200 and tablet[0] == 200


@pytest.mark.asyncio
async def test_the_owner_can_clear_a_binding_and_the_device_rebinds(sync_app) -> None:
    app, *_ = sync_app
    async with TestClient(TestServer(app)) as client:
        token, device_id = await _pair(client, "install-a")
        cleared = await client.delete(f"/api/devices/{device_id}/install-id", headers=OWNER)
        rebound = await _preview(client, _items(), source=TABLET, headers=_as(token))
        old = await _preview(client, _items(), source=PHONE, headers=_as(token))
        unknown = await client.delete("/api/devices/nope/install-id", headers=OWNER)
        anonymous = await client.delete(f"/api/devices/{device_id}/install-id", headers=CONFIRM)

    assert cleared.status == 200
    assert rebound[0] == 200 and app[DEVICE_TOKENS_KEY].entries()[0]["install_id"] == "install-b"
    assert old[0] == 403
    assert unknown.status == 404
    assert anonymous.status == 401


# ---- Export ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_then_import_is_unchanged(sync_app) -> None:
    app, api, _lorebook = sync_app
    embedded = {"name": "Mira lore", "entries": [{"id": "woods", "name": "woods", "content": "Woods", "keys": ["woods"]}]}
    pushed = _items(card=_card_doc(book=embedded))
    async with TestClient(TestServer(app)) as client:
        _s, created, _ = await _push(client, pushed)
        rows = _by_ref(created["items"])
        status, exported = await _post(client, "/api/content/export", {"items": [
            {"kind": "character_template", "canonical_id": rows["card-1"]["canonical_id"]},
            {"kind": "lorebook", "canonical_id": rows["book-1"]["canonical_id"]},
        ]})
        assert status == 200, exported
        card_export, book_export = exported["items"]
        again_items = [
            {"client_ref": "card-1", "kind": "character_template", "document": card_export["document"]},
            {"client_ref": "book-1", "kind": "lorebook", "document": book_export["document"]},
        ]
        _s, again = await _preview(client, again_items)
        missing = await _post(client, "/api/content/export",
                              {"items": [{"kind": "lorebook", "canonical_id": "nope"}]})

    origin = card_export["origin"]
    assert origin["server_instance_id"].startswith("srv-")
    assert origin["canonical_id"] == rows["card-1"]["canonical_id"]
    assert origin["state_token"] == rows["card-1"]["state_token"]
    assert origin["provenance"]["external_id"] == "card-1"
    assert origin["locked_reason"] is None and book_export["origin"]["locked_reason"] is None
    assert card_export["document"]["spec"] == "chara_card_v3"
    assert card_export["document"]["data"]["character_book"]["entries"][0]["id"] == "woods"
    assert book_export["format"] == "lorebook_v3"
    assert book_export["origin"]["provenance"]["external_id"] == "book-1"
    assert [row["action"] for row in again["items"]] == ["unchanged", "unchanged", "unchanged"]
    assert missing[0] == 404 and missing[1]["error_code"] == "NOT_FOUND"


# ---- #494 review fixes -------------------------------------------------------------


def _bare_book(entries: list[dict], *, nested: bool) -> dict:
    """A lorebook_v3 document in the shapes the adapter also accepts."""

    if nested:
        return {"spec": "lorebook_v3", "data": {"entries": entries}}
    return {"spec": "lorebook_v3", "entries": entries}


@pytest.mark.asyncio
@pytest.mark.parametrize("nested", [True, False], ids=["data.entries", "top-level entries"])
async def test_entry_limits_count_what_the_adapter_parses(sync_app, nested) -> None:
    app, _api, lorebook = sync_app
    many = [{"id": f"e{i}", "content": "x", "keys": ["k"]} for i in range(2001)]
    huge = [{"id": "big", "content": "x" * (33 * 1024), "keys": ["k"]}]
    async with TestClient(TestServer(app)) as client:
        count = await _preview(client, [{"client_ref": "b", "kind": "lorebook", "document": _bare_book(many, nested=nested)}])
        size = await _preview(client, [{"client_ref": "b", "kind": "lorebook", "document": _bare_book(huge, nested=nested)}])

    assert count[0] == 413 and count[1]["error_code"] == "TOO_MANY_ENTRIES"
    assert size[0] == 413 and size[1]["error_code"] == "ENTRY_TOO_LARGE"
    assert lorebook.list_lorebooks() == []


@pytest.mark.asyncio
async def test_a_deeply_nested_body_is_a_clean_400(sync_app) -> None:
    app, *_ = sync_app
    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/content/import/preview", data=b"[" * 200_000 + b"]" * 200_000,
            headers={**OWNER, "Content-Type": "application/json"},
        )
        body = await response.json()
    assert response.status == 400 and body["error_code"] == "REQUEST_INVALID"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/content/import/preview", "/api/content/import/commit", "/api/content/export"])
async def test_sync_routes_require_the_confirm_header(sync_app, monkeypatch, path) -> None:
    app, api, _lorebook = sync_app
    # No access password: the only cross-site barrier is the confirm header.
    monkeypatch.setitem(web_server.STATE, "access_token", "")
    body = {"source": PHONE, "items": [_items()[0]], "plan_digest": "sha256:x"}
    async with TestClient(TestServer(app)) as client:
        response = await client.post(path, data=json.dumps(body), headers={"Content-Type": "text/plain"})
    assert response.status == 403
    assert api.list_character_cards()["cards"] == []


@pytest.mark.asyncio
async def test_re_pairing_the_same_install_takes_over_its_binding(sync_app, caplog) -> None:
    app, *_ = sync_app
    async with TestClient(TestServer(app)) as client:
        old_token, old_id = await _pair(client, "install-a")
        issued = await client.post("/api/pairing", headers=OWNER)
        code = (await issued.json())["code"]
        with caplog.at_level("WARNING", logger="trpg"):
            claimed = await client.post(
                "/api/pairing/claim", json={"code": code, "install_id": "install-a"}, headers=CONFIRM,
            )
            claimed_body = await claimed.json()
        new_token = claimed_body["device_token"]
        old_push = await client.post(
            "/api/content/import/preview", json={"source": PHONE, "items": _items()}, headers=_as(old_token),
        )
        new_push = await _preview(client, _items(), source=PHONE, headers=_as(new_token))

    assert claimed.status == 200
    assert claimed_body["install_id"] == "install-a"
    assert claimed_body["replaced_device_id"] == old_id
    # The old token belonged to the same install: it is revoked, not kept.
    assert old_push.status == 401
    assert new_push[0] == 200
    devices = app[DEVICE_TOKENS_KEY].entries()
    assert [(d["id"], d["install_id"]) for d in devices] == [(claimed_body["device_id"], "install-a")]
    assert any("install_id=install-a" in r.getMessage() and old_id in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_a_content_push_never_takes_over_another_devices_install_id(sync_app) -> None:
    app, *_ = sync_app
    async with TestClient(TestServer(app)) as client:
        holder_token, _holder_id = await _pair(client, "install-a")
        other_token, _other_id = await _pair(client)  # no install id at pairing
        first_use = await _preview(client, _items(), source=PHONE, headers=_as(other_token))
        holder = await _preview(client, _items(), source=PHONE, headers=_as(holder_token))

    assert first_use[0] == 403 and first_use[1]["error_code"] == "INSTALL_ID_IN_USE"
    assert holder[0] == 200


@pytest.mark.asyncio
async def test_documents_are_parsed_once_and_outside_the_library_lock(sync_app, monkeypatch) -> None:
    from contextlib import contextmanager

    from src.lorebook import importer as lorebook_importer
    from src.webui.services import character_cards as card_service

    app, *_ = sync_app
    state = {"locked": 0}
    parses: list[int] = []
    real_lock = card_service.library_lock
    real_parse = lorebook_importer.from_lorebook_v3

    @contextmanager
    def tracking_lock(dependencies):
        with real_lock(dependencies):
            state["locked"] += 1
            try:
                yield
            finally:
                state["locked"] -= 1

    def tracking_parse(payload):
        parses.append(state["locked"])
        return real_parse(payload)

    monkeypatch.setattr(card_service, "library_lock", tracking_lock)
    monkeypatch.setattr(lorebook_importer, "from_lorebook_v3", tracking_parse)
    embedded = {"name": "Mira lore", "entries": [{"id": "w", "content": "Woods", "keys": ["w"]}]}
    items = _items(card=_card_doc(book=embedded))
    body = {"source": PHONE, "items": items}
    async with TestClient(TestServer(app)) as client:
        _status, preview = await _post(client, "/api/content/import/preview", body)
        parses.clear()
        status, result = await _post(client, "/api/content/import/commit", {
            **body, "plan_digest": preview["plan_digest"],
        })

    assert status == 200, result
    # Two books (the card's embedded one and the standalone one), one parse
    # each, and none of them while the card library lock is held.
    assert parses == [0, 0]


@pytest.mark.asyncio
async def test_an_unexpected_item_failure_reports_exactly_what_was_written(sync_app, monkeypatch) -> None:
    from src.webui.services import character_card_import

    app, api, lorebook = sync_app

    def broken(*_args, **_kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(character_card_import, "_execute_card", broken)
    items = [_items()[1], _items()[0], _items()[1] | {"client_ref": "book-2"}]
    async with TestClient(TestServer(app)) as client:
        status, result, _ = await _push(client, items)

    rows = _by_ref(result["items"])
    assert status == 500 and result["ok"] is False
    assert rows["book-1"]["status"] == "created"
    assert rows["card-1"]["status"] == "error" and rows["card-1"]["error_code"] == "IMPORT_FAILED"
    assert rows["book-2"]["status"] == "not_attempted"
    assert [book["external_id"] for book in lorebook.list_lorebooks()] == ["book-1"]
    assert api.list_character_cards()["cards"] == []


# ---- Mobile contract gaps ----------------------------------------------------------


def _server_book(lorebook, book_id: str, *, entries: dict[str, str], **fields) -> None:
    lorebook.create_lorebook({"id": book_id, "name": "Server book", **fields})
    for key, content in entries.items():
        lorebook.add_book_entry(book_id, {"id": f"{book_id}:{key}", "name": key, "content": content,
                                          "keywords": [key], **({} if key != "plugin" else {"source_plugin": "pack"})})


def _hinted_book(hint: str, *, client_ref: str = "book-1", entries: dict[str, str] | None = None) -> dict:
    return {"client_ref": client_ref, "kind": "lorebook",
            "document": _lorebook("Pulled", entries or {"town": "Town"}), "canonical_hint": hint}


@pytest.mark.asyncio
async def test_canonical_hint_adopts_a_server_book(sync_app) -> None:
    app, _api, lorebook = sync_app
    _server_book(lorebook, "server-book", entries={"town": "Old town"})
    async with TestClient(TestServer(app)) as client:
        _s, preview = await _preview(client, [_hinted_book("server-book")])
        item = preview["items"][0]
        assert item["existing"]["canonical_id"] == "server-book"
        assert item["existing"]["matched_by"] == "hint" and item["existing"]["server_modified"] is None
        assert item["allowed"] == ["update", "duplicate", "skip"]
        _s, adopted, _ = await _push(client, [_hinted_book("server-book")], decisions={"book-1": "update"})
        plain = {k: v for k, v in _hinted_book("server-book").items() if k != "canonical_hint"}
        _s, followed = await _preview(client, [plain])

    assert adopted["items"][0]["canonical_id"] == "server-book"
    book = lorebook.get_lorebook("server-book")
    assert (book["source_id"], book["external_id"], book["import_link"]) == ("install-a", "book-1", "tracked")
    assert followed["items"][0]["existing"]["matched_by"] == "identity"
    assert followed["items"][0]["action"] == "unchanged"


@pytest.mark.asyncio
async def test_a_hinted_book_of_someone_else_offers_duplicate_or_skip(sync_app) -> None:
    app, _api, lorebook = sync_app
    _server_book(lorebook, "plugin-book", entries={"plugin": "From a pack"})
    async with TestClient(TestServer(app)) as client:
        _s, other, _ = await _push(client, [_hinted_book("x", client_ref="theirs")], source=TABLET)
        theirs = other["items"][0]["canonical_id"]
        _s, kept, _ = await _push(client, [_hinted_book("x", client_ref="theirs", entries={"town": "v2"})],
                                  source=TABLET, decisions={"theirs": "duplicate"})
        detached = kept["items"][0]["detached_id"]
        plugin = await _preview(client, [_hinted_book("plugin-book")])
        tracked = await _preview(client, [_hinted_book(kept["items"][0]["canonical_id"])])
        detached_hint = await _preview(client, [_hinted_book(detached)])
        _s, copied, _ = await _push(client, [_hinted_book("plugin-book")], decisions={"book-1": "duplicate"})

    assert detached == theirs
    for (_status, body), reason in (
        (plugin, "PLUGIN_BOOK"), (tracked, "TRACKED_BY_OTHER_SOURCE"), (detached_hint, "DETACHED_FROM_OTHER_SOURCE"),
    ):
        assert body["items"][0]["allowed"] == ["duplicate", "skip"]
        assert body["items"][0]["reason"] == reason
    # Keeping both never detaches someone else's book.
    assert copied["items"][0]["status"] == "duplicated" and "detached_id" not in copied["items"][0]
    assert lorebook.get_lorebook("plugin-book")["import_link"] == ""


@pytest.mark.asyncio
async def test_a_hint_never_overrides_an_identity_match(sync_app) -> None:
    app, _api, lorebook = sync_app
    _server_book(lorebook, "server-book", entries={"town": "Old town"})
    async with TestClient(TestServer(app)) as client:
        _s, created, _ = await _push(client, [_hinted_book("nope")])
        _s, preview = await _preview(client, [_hinted_book("server-book", entries={"town": "v2"})])

    existing = preview["items"][0]["existing"]
    assert existing["matched_by"] == "identity"
    assert existing["canonical_id"] == created["items"][0]["canonical_id"] != "server-book"


@pytest.mark.asyncio
async def test_status_reports_state_tokens_and_provenance(sync_app) -> None:
    app, api, _lorebook = sync_app
    async with TestClient(TestServer(app)) as client:
        _s, created, _ = await _push(client, _items())
        rows = _by_ref(created["items"])
        query = {"items": [
            {"kind": "character_template", "canonical_id": rows["card-1"]["canonical_id"]},
            {"kind": "lorebook", "canonical_id": rows["book-1"]["canonical_id"]},
            {"kind": "lorebook", "canonical_id": "gone"},
        ]}
        status, before = await _post(client, "/api/content/status", query)
        api.update_character_card(rows["card-1"]["canonical_id"], {"gold": 1})
        _s, after = await _post(client, "/api/content/status", query)
        anonymous, _ = await _post(client, "/api/content/status", query, CONFIRM)
        unconfirmed = await client.post("/api/content/status", json=query, headers={"Authorization": f"Bearer {PASSWORD}"})
        too_many, _ = await _post(client, "/api/content/status",
                                  {"items": [{"kind": "lorebook", "canonical_id": "x"}] * 501})

    card, book, gone = before["items"]
    assert status == 200 and before["server_instance_id"].startswith("srv-")
    assert card["state_token"] == rows["card-1"]["state_token"]
    assert book["state_token"] == rows["book-1"]["state_token"]
    assert card["provenance"]["external_id"] == "card-1" and book["provenance"]["external_id"] == "book-1"
    assert gone == {"kind": "lorebook", "canonical_id": "gone", "exists": False, "state_token": "", "provenance": None}
    assert after["items"][0]["state_token"] != card["state_token"]
    assert anonymous == 401 and unconfirmed.status == 403 and too_many == 413


@pytest.mark.asyncio
async def test_an_unavailable_server_identity_is_an_explicit_error(sync_app, tmp_path) -> None:
    app, *_ = sync_app
    (tmp_path / "server_identity.json").write_text("not json", encoding="utf-8")
    app.router.add_get("/api/config", web_server.api_config_get)
    async with TestClient(TestServer(app)) as client:
        preview = await _preview(client, _items())
        status = await _post(client, "/api/content/status", {"items": [{"kind": "lorebook", "canonical_id": "x"}]})
        config = await (await client.get("/api/config", headers=OWNER)).json()

    assert preview[0] == 503 and preview[1]["error_code"] == "SERVER_IDENTITY_UNAVAILABLE"
    assert status[0] == 503 and status[1]["error_code"] == "SERVER_IDENTITY_UNAVAILABLE"
    assert "server_instance_id" not in config
    assert config["server_identity_error"] == "SERVER_IDENTITY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_status_reads_the_card_library_once_per_request(sync_app, monkeypatch) -> None:
    app, *_ = sync_app
    reads: list[int] = []
    real_read = character_cards.read_library

    def counting_read(dependencies):
        reads.append(1)
        return real_read(dependencies)

    async with TestClient(TestServer(app)) as client:
        _s, first, _ = await _push(client, [_items()[0]])
        _s, second, _ = await _push(client, [_items()[0] | {"client_ref": "card-2"}])
        ids = [first["items"][0]["canonical_id"], second["items"][0]["canonical_id"], "missing"]
        monkeypatch.setattr(character_cards, "read_library", counting_read)
        status, body = await _post(client, "/api/content/status", {"items": [
            {"kind": "character_template", "canonical_id": card_id} for card_id in ids
        ]})

    assert status == 200 and [row["exists"] for row in body["items"]] == [True, True, False]
    assert len(reads) == 1


@pytest.mark.asyncio
async def test_a_hinted_book_reports_where_it_is_bound(sync_app) -> None:
    app, _api, lorebook = sync_app
    _server_book(lorebook, "server-book", entries={"town": "Old town"})
    lorebook.bind_lorebook({"id": "b:game", "book_id": "server-book", "scope_kind": "game", "scope_id": "web|room|gm"})
    lorebook.bind_lorebook({"id": "b:char", "book_id": "server-book", "scope_kind": "character", "scope_id": "u1"})
    _server_book(lorebook, "free-book", entries={"town": "Town"})
    async with TestClient(TestServer(app)) as client:
        _s, bound = await _preview(client, [_hinted_book("server-book")])
        _s, unbound = await _preview(client, [_hinted_book("free-book")])

    bindings = bound["items"][0]["existing"]["bindings"]
    assert sorted((b["scope_kind"], b["scope_id"]) for b in bindings) == [
        ("character", "u1"), ("game", "web|room|gm"),
    ]
    assert unbound["items"][0]["existing"]["bindings"] == []
