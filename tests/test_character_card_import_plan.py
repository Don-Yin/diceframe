"""Confirmable character card imports (PR G2c).

Protected contracts:
- a portable card is a ``chara_card_v3`` envelope with the DiceFrame body in
  ``data.extensions.diceframe``; free-form and CoC cards round-trip;
- the push is planned with the shared plan vocabulary: ``plan_digest``,
  per-item decisions, ``PLAN_STALE`` with a fresh preview;
- imports write by id under the library lock: one identity is tracked by at
  most one card, even under concurrent pushes; nothing is signature-merged;
- update keeps server-side fields; duplicate detaches the old card; plugin
  and foreign-tracked cards offer no update; rules-aware cards are
  unsupported with a clear code; server-local portraits are dropped with a
  warning; an embedded book becomes a linked, unbound Lorebook item.
"""

from __future__ import annotations

import json
import threading
import time

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.content_modules.adapters.character_card_v3 import read_card_v3, write_card_v3
from src.webui.services import character_card_import, character_cards
from src.webui.routes.character_cards import register_character_cards

pytest_plugins = ["tests.webapi_harness"]

DEVICE_A = {"kind": "device", "id": "install-a"}
DEVICE_B = {"kind": "device", "id": "install-b"}

FREEFORM = {
    "schema_version": 2, "character_name": "Mira", "race": "Elf", "class": "Ranger",
    "background": "Raised in the border woods.", "attributes": {"str": 12, "dex": 16},
    "skills": [{"name": "Tracking", "value": 40}], "equipment": ["Longbow"],
    "gold": 30, "rule_id": "freeform_fantasy", "language": "en",
}
COC = {
    "schema_version": 2, "character_name": "Harvey Walters", "race": "Human",
    "class": "Journalist", "background": "Arkham Advertiser.",
    "attributes": {"STR": 50, "CON": 60, "POW": 65, "INT": 70},
    "skills": [{"name": "Library Use", "value": 60}], "gold": 0,
    "rule_id": "freeform_coc", "mechanics": "coc", "language": "en",
}
DND = {
    **FREEFORM, "character_name": "Thorn", "rule_id": "dnd2024",
    "rule_binding": {"runtime_id": "dnd2024", "runtime_version": 1},
    "ruleset_character": {"rule_binding": {"runtime_id": "dnd2024", "runtime_version": 1}},
}


def _push(body: dict, *, local: str = "card-1", source: dict | None = None,
          book: dict | None = None, **extra) -> dict:
    return {
        "document": write_card_v3(body, character_book=book),
        "source": source or DEVICE_A, "external_id": local, **extra,
    }


def _preview(api, request: dict) -> dict:
    result = api.preview_character_card_import(request)
    assert result["ok"], result
    return result


def _commit(api, request: dict, *, decision: str | None = None, digest: str | None = None,
            decisions: dict | None = None) -> dict:
    preview = _preview(api, request)
    body = {**request, "plan_digest": digest or preview["plan"]["plan_digest"]}
    if decision is not None:
        body["decisions"] = {preview["plan"]["items"][0]["client_ref"]: decision}
    if decisions is not None:
        body["decisions"] = decisions
    return api.commit_character_card_plan(body)


def _card_item(preview: dict) -> dict:
    return preview["plan"]["items"][0]


def _library(api) -> list[dict]:
    path = api._character_cards_path
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _card(api, card_id: str) -> dict:
    return next(card for card in _library(api) if card["id"] == card_id)


def _portable(card: dict) -> dict:
    return {k: v for k, v in card.items() if k not in {"id", "provenance"}}


@pytest.mark.parametrize("body", [FREEFORM, COC], ids=["freeform", "coc"])
def test_free_form_and_coc_cards_round_trip(web_api, body) -> None:
    api, *_ = web_api
    request = _push(body)
    assert _card_item(_preview(api, request))["action"] == "create"

    created = _commit(api, request)

    assert created["ok"] and created["items"][0]["status"] == "created"
    stored = _card(api, created["card_id"])
    for key, value in body.items():
        assert stored[key] == value
    provenance = stored["provenance"]
    assert (provenance["source_id"], provenance["external_id"], provenance["link"]) == ("install-a", "card-1", "tracked")

    # Library card -> portable v3 -> re-push is recognised as the same card.
    exported = write_card_v3(_portable(stored))
    assert read_card_v3(exported).body == _portable(stored)
    again = _preview(api, {**request, "document": exported})
    assert _card_item(again)["action"] == "unchanged"
    assert _card_item(again)["existing"]["canonical_id"] == created["card_id"]
    assert _commit(api, request, decision="update")["items"][0]["status"] == "unchanged"


def test_update_overwrites_portable_fields_and_keeps_server_fields(web_api) -> None:
    api, *_ = web_api
    created = _commit(api, _push(FREEFORM))
    cards = _library(api)
    for card in cards:
        if card["id"] == created["card_id"]:
            card.update({"portrait": {"kind": "upload", "asset_id": "a1"}, "ruleset_revision": 4})
    api._character_cards_path.write_text(json.dumps(cards), encoding="utf-8")

    edited = {**FREEFORM, "background": "Now a guide in the capital.", "gold": 99}
    item = _card_item(_preview(api, _push(edited)))
    assert item["action"] == "update" and item["existing"]["server_modified"] is True

    result = _commit(api, _push(edited), decision="update")

    assert result["items"][0]["status"] == "updated" and result["card_id"] == created["card_id"]
    stored = _card(api, created["card_id"])
    assert (stored["background"], stored["gold"]) == ("Now a guide in the capital.", 99)
    assert stored["ruleset_revision"] == 4
    assert stored["portrait"] == {"kind": "upload", "asset_id": "a1"}
    assert len(_library(api)) == 1


def test_pushed_server_only_fields_are_ignored(web_api) -> None:
    api, *_ = web_api
    forged = {
        **FREEFORM, "id": "card_forged", "source_plugin": "evil",
        "provenance": {"source_kind": "device", "source_id": "x", "external_id": "y", "link": "tracked"},
    }
    created = _commit(api, _push(forged))

    stored = _card(api, created["card_id"])
    assert stored["id"] != "card_forged"
    assert "source_plugin" not in stored
    assert stored["provenance"]["source_id"] == "install-a"


def test_plugin_card_can_be_duplicated_but_never_updated(web_api) -> None:
    api, *_ = web_api
    plugin_card = {**FREEFORM, "id": "plugin_pack_mira", "source_plugin": "pack", "plugin_content_id": "mira"}
    api._character_cards_path.write_text(json.dumps([plugin_card]), encoding="utf-8")
    request = _push({**FREEFORM, "background": "Edited"}, canonical_hint="plugin_pack_mira")

    item = _card_item(_preview(api, request))
    assert item["allowed"] == ["duplicate", "skip"] and item["reason"] == "PLUGIN_CARD"
    refused = _commit(api, request, decision="update")
    assert refused["error_code"] == "DECISION_NOT_ALLOWED"

    copied = _commit(api, request, decision="duplicate")
    assert copied["items"][0]["status"] == "duplicated"
    assert _card(api, "plugin_pack_mira") == plugin_card
    assert _card(api, copied["card_id"])["provenance"]["link"] == "tracked"


def test_a_card_tracked_by_another_install_is_not_updatable(web_api) -> None:
    api, *_ = web_api
    other = _commit(api, _push(FREEFORM, source=DEVICE_B))
    request = _push(FREEFORM, canonical_hint=other["card_id"])

    item = _card_item(_preview(api, request))

    assert item["allowed"] == ["duplicate", "skip"]
    assert item["reason"] == "TRACKED_BY_OTHER_SOURCE"


def test_rules_aware_cards_are_unsupported_with_a_clear_code(web_api) -> None:
    api, *_ = web_api
    request = _push(DND)

    item = _card_item(_preview(api, request))
    result = _commit(api, request)

    assert item["action"] == "unsupported" and item["reason"] == "RULESET_CARD_UNSUPPORTED"
    assert item["allowed"] == []
    assert result["ok"] is False and result["error_code"] == "RULESET_CARD_UNSUPPORTED"
    assert _library(api) == []


def test_two_devices_produce_two_cards_and_nothing_is_signature_merged(web_api) -> None:
    api, *_ = web_api
    character_cards.save_character_card(api._character_card_dependencies, dict(FREEFORM))

    first = _commit(api, _push(FREEFORM, source=DEVICE_A))
    second = _commit(api, _push(FREEFORM, source=DEVICE_B))

    assert first["card_id"] != second["card_id"]
    listed = api.list_character_cards()["cards"]
    assert len(listed) == 3
    assert {first["card_id"], second["card_id"]} <= {card["id"] for card in listed}


def test_concurrent_pushes_of_one_identity_track_one_card(web_api) -> None:
    api, *_ = web_api
    request = _push(FREEFORM)
    digest = _preview(api, request)["plan"]["plan_digest"]
    base = api._card_import_dependencies()

    def slow_read() -> list[dict]:
        cards = base.read_cards()
        time.sleep(0.05)  # widen the read -> write window
        return cards

    deps = character_card_import.CardImportDependencies(
        read_cards=slow_read, write_cards=base.write_cards, lock=base.lock,
        to_card=base.to_card, new_card_id=base.new_card_id,
        is_ruleset_card=base.is_ruleset_card, lorebook=base.lorebook,
    )
    barrier = threading.Barrier(2)
    results: list[dict] = []

    def push() -> None:
        barrier.wait()
        results.append(character_card_import.commit_card_import(deps, {**request, "plan_digest": digest}))

    threads = [threading.Thread(target=push) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(str(r.get("error_code") or r["items"][0]["status"]) for r in results) == ["PLAN_STALE", "created"]
    tracked = [card for card in _library(api) if card.get("provenance", {}).get("link") == "tracked"]
    assert len(tracked) == 1


def test_a_stale_plan_is_refused_with_a_fresh_preview(web_api) -> None:
    api, *_ = web_api
    created = _commit(api, _push(FREEFORM))
    edited = _push({**FREEFORM, "gold": 5})
    seen = _preview(api, edited)["plan"]["plan_digest"]
    api.update_character_card(created["card_id"], {"background": "Edited on the server"})

    stale = _commit(api, edited, decision="update", digest=seen)

    assert stale["ok"] is False and stale["error_code"] == "PLAN_STALE"
    fresh = stale["preview"]["plan"]
    assert fresh["plan_digest"] != seen
    assert fresh["items"][0]["existing"]["server_modified"] is True
    assert _card(api, created["card_id"])["background"] == "Edited on the server"


def test_duplicate_detaches_the_old_card(web_api) -> None:
    api, *_ = web_api
    created = _commit(api, _push(FREEFORM))
    edited = _push({**FREEFORM, "gold": 77})

    copied = _commit(api, edited, decision="duplicate")

    assert copied["items"][0]["status"] == "duplicated"
    assert copied["items"][0]["detached_card_id"] == created["card_id"]
    old, new = _card(api, created["card_id"]), _card(api, copied["card_id"])
    assert old["provenance"]["link"] == "detached" and old["gold"] == 30
    assert new["provenance"]["link"] == "tracked" and new["gold"] == 77
    assert _card_item(_preview(api, edited))["existing"]["canonical_id"] == copied["card_id"]


def test_skip_writes_nothing(web_api) -> None:
    api, *_ = web_api
    created = _commit(api, _push(FREEFORM))
    before = _library(api)

    skipped = _commit(api, _push({**FREEFORM, "gold": 1}), decision="skip")

    assert skipped["items"][0]["status"] == "skipped" and skipped["card_id"] == created["card_id"]
    assert _library(api) == before


def test_the_embedded_book_is_a_linked_unbound_lorebook(web_api) -> None:
    api, lorebook, *_ = web_api
    book = {"name": "Mira's lore", "entries": [{"id": "e1", "name": "Woods", "content": "Border woods", "keys": ["woods"]}]}
    request = _push(FREEFORM, book=book)

    items = _preview(api, request)["plan"]["items"]
    assert [item["kind"] for item in items] == ["character_template", "lorebook"]

    result = _commit(api, request)

    stored_book = lorebook.get_lorebook(result["book_id"])
    assert (stored_book["source_id"], stored_book["external_id"]) == ("install-a", "card-1.book")
    assert [b for b in lorebook.list_bindings() if b["book_id"] == result["book_id"]] == []
    assert _card(api, result["card_id"])["provenance"]["book_id"] == result["book_id"]
    # Both items are recognised on the next push.
    assert [item["action"] for item in _preview(api, request)["plan"]["items"]] == ["unchanged", "unchanged"]


def test_server_local_portraits_are_dropped_with_a_warning(web_api) -> None:
    api, *_ = web_api
    uploaded = _preview(api, _push({**FREEFORM, "portrait": {"kind": "upload", "asset_id": "a1"}}))
    builtin = _preview(api, _push({**FREEFORM, "portrait": {"kind": "builtin", "id": "elf_f"}}))

    assert [w["code"] for w in uploaded["warnings"]] == ["PORTRAIT_NOT_PORTABLE"]
    assert uploaded["card"]["portrait"] == {}
    assert builtin["warnings"] == [] and builtin["card"]["portrait"] == {"kind": "builtin", "id": "elf_f"}


@pytest.mark.parametrize("request_body, code", [
    ({"document": write_card_v3(FREEFORM)}, "IMPORT_SOURCE_INVALID"),
    ({"document": {"spec": "chara_card_v2", "data": {}}, "source": DEVICE_A, "external_id": "c"}, "CARD_V3_INVALID"),
    ({"document": {"spec": "chara_card_v3", "data": {"name": "x"}}, "source": DEVICE_A, "external_id": "c"}, "CARD_V3_INVALID"),
])
def test_malformed_pushes_fail_closed(web_api, request_body, code) -> None:
    api, *_ = web_api
    assert api.preview_character_card_import(request_body)["error_code"] == code
    assert api.commit_character_card_plan({**request_body, "plan_digest": "sha256:x"})["error_code"] == code
    assert _library(api) == []


# ---- Routes ---------------------------------------------------------------------


class _CardApi:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls: list[tuple[dict, str]] = []

    def preview_character_card_import(self, body):
        return {"ok": True, "plan": {"plan_digest": "sha256:x", "items": []}}

    def commit_character_card_plan(self, body, *, pushed_by_device=""):
        self.calls.append((body, pushed_by_device))
        return self.result

    async def import_character_card(self, **_kwargs):
        raise AssertionError("a plan commit must not reach the file import")


@pytest.mark.asyncio
@pytest.mark.parametrize("code, status", [
    ("PLAN_STALE", 409), ("CARD_IDENTITY_CONFLICT", 409), ("DECISION_REQUIRED", 400),
])
async def test_card_plan_routes(code, status) -> None:
    api = _CardApi({"ok": False, "error_code": code})
    app = web.Application()
    app["api"] = api
    register_character_cards(app)
    async with TestClient(TestServer(app)) as client:
        preview = await client.post("/api/character-cards/import/preview", json={"document": {}})
        commit = await client.post("/api/character-cards/import", json={"plan_digest": "sha256:x"})
    assert preview.status == 200
    assert commit.status == status
    assert api.calls == [({"plan_digest": "sha256:x"}, "")]


# ---- #488 review fixes ------------------------------------------------------------


def test_hint_update_keeps_the_raw_tavern_original(web_api) -> None:
    api, *_ = web_api
    raw = {"name": "Mira", "description": "Tavern original", "first_mes": "Hello."}
    tavern_card = {**FREEFORM, "id": "st_mira", "raw_sillytavern": raw}
    api._character_cards_path.write_text(json.dumps([tavern_card]), encoding="utf-8")
    request = _push({**FREEFORM, "gold": 12}, canonical_hint="st_mira")

    result = _commit(api, request, decision="update")

    assert result["items"][0]["status"] == "updated"
    stored = _card(api, "st_mira")
    assert stored["gold"] == 12
    assert stored["raw_sillytavern"] == raw


def test_a_card_detached_from_another_source_cannot_be_retracked_by_hint(web_api) -> None:
    api, *_ = web_api
    first = _commit(api, _push(FREEFORM, source=DEVICE_B))
    _commit(api, _push({**FREEFORM, "gold": 1}, source=DEVICE_B), decision="duplicate")
    assert _card(api, first["card_id"])["provenance"]["link"] == "detached"
    request = _push(FREEFORM, canonical_hint=first["card_id"])

    item = _card_item(_preview(api, request))
    refused = _commit(api, request, decision="update")

    assert item["allowed"] == ["duplicate", "skip"]
    assert item["reason"] == "DETACHED_FROM_OTHER_SOURCE"
    assert refused["error_code"] == "DECISION_NOT_ALLOWED"
    assert _card(api, first["card_id"])["provenance"]["source_id"] == "install-b"
