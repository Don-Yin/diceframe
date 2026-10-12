"""Content sync identity storage (PR G2a).

Protected contracts:
- Lorebook schema v10 separates a Book's external identity from its source;
  legacy rows are untouched, the migration is idempotent and an unknown future
  schema fails closed; one external identity is held by at most one Book.
- A library card's import provenance is server bookkeeping: it survives every
  re-shaping of the card, clients cannot write it, and a card carrying it is
  never merged by signature nor overwritten by a table auto-save.
- Import receipts are keyed by (source_kind, source_id); old plugin receipts
  at the pre-kind path are still honoured by uninstall.
- The server instance id is random, persisted in the data dir and stable
  across restarts; a damaged id file is never silently replaced.
- The access-control middleware records which paired device authenticated a
  request, for audit only.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import web_server
from src.content_modules.receipts import ImportReceiptStore
from src.lorebook.store import SCHEMA, LorebookStore
from src.migrations import lorebook as lorebook_migrations
from src.migrations.sqlite import MigrationError, run_migrations
from src.webui.access_control import PAIRED_DEVICE_ID_KEY
from src.webui.access_password import hash_access_password
from src.webui.character_card_projection import dedupe_cards, is_tracked_card
from src.webui.device_tokens import DEVICE_TOKENS_KEY, DeviceTokenStore
from src.webui.server_identity import (
    SERVER_IDENTITY_KEY,
    ServerIdentityError,
    ServerIdentityStore,
)
from src.webui.services import character_cards, plugins


# ---- Lorebook schema v10 ---------------------------------------------------


def _fresh_connection() -> sqlite3.Connection:
    # The same bootstrap LorebookStore.open() runs before migrating.
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    return conn


def _v9_database() -> sqlite3.Connection:
    conn = _fresh_connection()
    assert lorebook_migrations.migrate(conn, upto=9) == 9
    conn.execute(
        "INSERT INTO lorebooks (id, name, source_kind, source_id) "
        "VALUES ('legacy', 'Legacy', 'device', 'import-abc')"
    )
    conn.commit()
    return conn


def test_v10_adds_external_id_and_leaves_legacy_rows_untouched():
    conn = _v9_database()

    assert lorebook_migrations.migrate(conn, upto=10) == 10

    row = conn.execute(
        "SELECT source_kind, source_id, external_id FROM lorebooks WHERE id = 'legacy'"
    ).fetchone()
    assert row == ("device", "import-abc", "")
    index_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'idx_lorebooks_external_identity'"
    ).fetchone()[0]
    assert "UNIQUE" in index_sql.upper() and "external_id <> ''" in index_sql


def test_v10_is_idempotent():
    conn = _v9_database()
    assert lorebook_migrations.migrate(conn, upto=10) == 10
    # A second startup is a no-op, and replaying the step itself is harmless.
    assert lorebook_migrations.migrate(conn, upto=10) == 10
    lorebook_migrations._v10(conn)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(lorebooks)")]
    assert columns.count("external_id") == 1


def test_unknown_future_schema_fails_closed():
    conn = _v9_database()
    conn.execute(f"PRAGMA user_version = {lorebook_migrations.CURRENT_LOREBOOK_SCHEMA_VERSION + 1}")

    with pytest.raises(MigrationError):
        lorebook_migrations.migrate(conn)
    assert "external_id" not in [row[1] for row in conn.execute("PRAGMA table_info(lorebooks)")]


def test_external_identity_is_unique_but_legacy_rows_may_share_a_source():
    conn = _fresh_connection()
    run_migrations(conn, lorebook_migrations.MIGRATIONS)
    insert = (
        "INSERT INTO lorebooks (id, name, source_kind, source_id, external_id) "
        "VALUES (?, ?, 'device', 'install-1', ?)"
    )
    conn.execute(insert, ("a", "A", "book-1"))
    conn.execute(insert, ("legacy-1", "L1", ""))
    conn.execute(insert, ("legacy-2", "L2", ""))
    conn.execute(insert, ("b", "B", "book-2"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert, ("c", "C", "book-1"))


def test_store_refuses_to_silently_drop_a_book_holding_a_taken_identity(tmp_path: Path):
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    try:
        identity = {"source_kind": "device", "source_id": "install-1", "external_id": "book-1"}
        store.create_lorebook({"id": "first", "name": "First", **identity})
        assert store.get_lorebook("first")["external_id"] == "book-1"

        with pytest.raises(ValueError, match="already tracked"):
            store.create_lorebook({"id": "second", "name": "Second", **identity})
        assert store.get_lorebook("second") is None

        # The same Book re-created under its own id stays an idempotent no-op.
        store.create_lorebook({"id": "first", "name": "First", **identity})
        # Another install's identically named local id is a different identity.
        store.create_lorebook({
            "id": "other", "name": "Other",
            "source_kind": "device", "source_id": "install-2", "external_id": "book-1",
        })
        assert store.get_lorebook("other") is not None
    finally:
        store.close()


# ---- Library card provenance ------------------------------------------------


def _provenance(install: str = "install-1", local: str = "card-1", link: str = "tracked") -> dict:
    return {
        "source_kind": "device", "source_id": install, "external_id": local,
        "link": link, "source_digest": "sha256:abc",
    }


def _card(card_id: str, name: str = "Alice", **extra) -> dict:
    return {
        "id": card_id, "schema_version": 2, "character_name": name,
        "race": "Human", "class": "Fighter", "background": "Farmhand",
        "attributes": {}, "skills": [], "equipment": [], "source": "test", **extra,
    }


def _deps(tmp_path: Path, cards: list[dict] | None = None) -> character_cards.CharacterCardDependencies:
    deps = character_cards.CharacterCardDependencies(cards_path=tmp_path / "cards.json")
    if cards is not None:
        character_cards._write_cards(deps, cards)
    return deps


def _stored(deps) -> list[dict]:
    return json.loads(deps.cards_path.read_text(encoding="utf-8"))


def test_provenance_survives_card_reshaping_in_validated_form():
    card = character_cards._to_character_card(_card("c1", provenance={**_provenance(), "extra": "x"}))
    assert card["provenance"] == _provenance()

    nested = character_cards._to_character_card(
        {"character_name": "Alice", "character_sheet": {"provenance": _provenance()}},
    )
    assert nested["provenance"] == _provenance()


@pytest.mark.parametrize("bad", [
    {**_provenance(), "link": "owned"},
    {**_provenance(), "source_kind": "nonsense"},
    {**_provenance(), "external_id": "has space"},
    {k: v for k, v in _provenance().items() if k != "source_id"},
    "device:install-1",
])
def test_malformed_provenance_is_dropped_not_repaired(bad):
    card = character_cards._to_character_card(_card("c1", provenance=bad))
    assert "provenance" not in card


def test_two_same_signature_device_cards_are_not_merged(tmp_path: Path):
    first = _card("c1", provenance=_provenance(install="install-1"))
    second = _card("c2", provenance=_provenance(install="install-2"))
    deps = _deps(tmp_path, [first, second])

    listed = character_cards.list_character_cards(deps)

    assert [card["id"] for card in listed["cards"]] == ["c1", "c2"]
    assert [card["id"] for card in _stored(deps)] == ["c1", "c2"]
    # A detached copy next to its tracked successor is kept too.
    detached = _card("c3", provenance=_provenance(link="detached"))
    assert len(dedupe_cards([first, detached])) == 2


def test_plain_cards_still_dedupe_by_signature(tmp_path: Path):
    assert len(dedupe_cards([_card("c1"), _card("c2")])) == 1


def test_client_saves_cannot_write_provenance(tmp_path: Path):
    deps = _deps(tmp_path, [])

    saved = character_cards.save_character_card(deps, _card("c1", provenance=_provenance()))
    assert saved["ok"] and "provenance" not in saved["card"]

    nested = character_cards.save_character_card(deps, {
        "character_name": "Bob", "character_sheet": {"provenance": _provenance(local="card-2")},
    })
    assert nested["ok"] and "provenance" not in nested["card"]
    assert all("provenance" not in card for card in _stored(deps))


def test_update_cannot_write_provenance_and_keeps_the_recorded_one(tmp_path: Path):
    deps = _deps(tmp_path, [_card("c1", provenance=_provenance())])

    result = character_cards.update_character_card(deps, "c1", {
        "background": "Edited", "provenance": _provenance(install="forged"),
    })

    assert result["ok"]
    assert result["card"]["provenance"] == _provenance()
    assert _stored(deps)[0]["provenance"] == _provenance()


def test_signature_save_does_not_merge_into_a_tracked_card(tmp_path: Path):
    deps = _deps(tmp_path, [_card("c1", provenance=_provenance())])

    saved = character_cards.save_character_card(deps, _card("new-id"))

    assert saved["ok"]
    stored = {card["id"]: card for card in _stored(deps)}
    assert set(stored) == {"c1", "new-id"}
    assert stored["c1"]["provenance"] == _provenance()
    assert "provenance" not in stored["new-id"]


def test_save_by_id_keeps_the_recorded_provenance(tmp_path: Path):
    deps = _deps(tmp_path, [_card("c1", provenance=_provenance())])

    saved = character_cards.save_character_card(deps, _card("c1", background="Edited"))

    assert saved["ok"]
    [stored] = _stored(deps)
    assert stored["background"] == "Edited"
    assert stored["provenance"] == _provenance()


def test_from_game_save_cannot_overwrite_a_tracked_card(tmp_path: Path):
    tracked = _card("c1", provenance=_provenance())
    deps = _deps(tmp_path, [tracked])

    saved = character_cards.save_character_card(
        deps,
        {**_card("c1"), "card_id": "c1", "provenance": _provenance(install="forged")},
        from_game=True,
    )

    assert saved["ok"]
    stored = {card["id"]: card for card in _stored(deps)}
    assert stored["c1"] == tracked
    [table_copy] = [card for card_id, card in stored.items() if card_id != "c1"]
    assert "provenance" not in table_copy
    assert is_tracked_card(stored["c1"]) and not is_tracked_card(table_copy)


def test_legacy_export_omits_server_provenance(tmp_path: Path):
    deps = _deps(tmp_path, [_card("c1", provenance=_provenance())])

    exported = character_cards.export_character_cards(deps, ["c1"])

    assert "provenance" not in json.loads(exported["payload"].decode("utf-8"))


# ---- Import receipts --------------------------------------------------------


def test_receipts_do_not_cross_kinds(tmp_path: Path):
    store = ImportReceiptStore(tmp_path)
    store.record("same-id", source_kind="plugin", object_type="character_card", object_id="p1")
    store.record("same-id", source_kind="device", object_type="character_card", object_id="d1")

    plugin = store.load("same-id", source_kind="plugin")
    device = store.load("same-id", source_kind="device")
    assert plugin.source_kind == "plugin" and device.source_kind == "device"
    assert [item["id"] for item in plugin.created_objects] == ["p1"]
    assert [item["id"] for item in device.created_objects] == ["d1"]

    store.discard("same-id", source_kind="device")
    assert store.load("same-id", source_kind="device") is None
    assert store.load("same-id", source_kind="plugin") is not None


def _write_legacy_plugin_receipt(root: Path, plugin_id: str, objects: list[dict]) -> Path:
    path = root / "content-receipts" / f"{plugin_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "source_kind": "module", "source_id": plugin_id, "source_version": "1.0.0",
        "source_digest": "", "created_objects": objects, "updated_objects": [],
        "user_detached_objects": [],
    }), encoding="utf-8")
    return path


def test_legacy_flat_receipt_is_a_plugin_receipt_only(tmp_path: Path):
    legacy = _write_legacy_plugin_receipt(tmp_path, "pack", [{"type": "lorebook_entry", "id": "e1"}])
    store = ImportReceiptStore(tmp_path)

    loaded = store.load("pack", source_kind="plugin")
    assert loaded is not None and loaded.source_kind == "plugin"
    assert loaded.created_objects == [{"type": "lorebook_entry", "id": "e1"}]
    assert store.load("pack", source_kind="device") is None
    assert store.load("pack", source_kind="module") is None

    # Recording moves the receipt to its keyed path without losing objects.
    store.record("pack", source_kind="plugin", object_type="lorebook_entry", object_id="e2")
    assert not legacy.exists()
    moved = store.load("pack", source_kind="plugin")
    assert [item["id"] for item in moved.created_objects] == ["e1", "e2"]


def test_uninstall_still_honours_an_old_plugin_receipt(tmp_path: Path):
    class Lore:
        def __init__(self) -> None:
            self.entries = {
                "owned": {"id": "owned", "source_plugin": "pack"},
                "not-receipted": {"id": "not-receipted", "source_plugin": "pack"},
            }

        def list_plugin_worlds(self, _plugin_id):
            return []

        def get_entry(self, entry_id):
            return self.entries.get(entry_id)

        def delete_entry(self, entry_id):
            return self.entries.pop(entry_id, None) is not None

        def delete_entries_by_plugin(self, _plugin_id):
            raise AssertionError("an existing receipt must be honoured, not bypassed")

    lore = Lore()
    deleted_cards: list[str] = []
    deps = plugins.PluginContentDependencies(
        plugin_host=SimpleNamespace(data_dir=tmp_path),
        store=plugins.PluginContentStoreDependencies(
            lorebook=lore,
            list_games=lambda: [],
            list_character_cards=lambda: {"cards": [
                {"id": "card-owned", "source_plugin": "pack"},
                {"id": "card-other", "source_plugin": "pack"},
            ]},
            save_character_card=lambda _card: {"ok": True},
            delete_character_card=lambda card_id: deleted_cards.append(card_id) or {"ok": True},
            save_entry=lambda _entry: {"ok": True},
        ),
        portraits=plugins.PluginPortraitDependencies(
            plugin_asset_path=lambda _plugin_id, _path: tmp_path,
            avatar_file=lambda _asset_id: None,
            generated_image_file=lambda _asset_id: None,
            save_avatar_upload=lambda _data, _name: {"ok": True},
        ),
    )
    legacy = _write_legacy_plugin_receipt(tmp_path, "pack", [
        {"type": "lorebook_entry", "id": "owned"},
        {"type": "character_card", "id": "card-owned"},
    ])

    result = plugins.cleanup_plugin_lorebook(deps, "pack")

    assert result["removed"] == 1
    assert set(lore.entries) == {"not-receipted"}
    assert deleted_cards == ["card-owned"]
    assert not legacy.exists()


# ---- Server instance id ------------------------------------------------------


def test_server_instance_id_is_stable_across_restarts(tmp_path: Path):
    first = ServerIdentityStore(tmp_path).instance_id()
    second = ServerIdentityStore(tmp_path).instance_id()

    assert first == second
    assert first.startswith("srv-")
    assert ServerIdentityStore(tmp_path / "other").instance_id() != first


@pytest.mark.parametrize("content", ["not json", '{"version": 1, "instance_id": "host-name"}', '{"version": 2}'])
def test_damaged_server_identity_is_never_replaced(tmp_path: Path, content: str):
    path = tmp_path / "server_identity.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ServerIdentityError):
        ServerIdentityStore(tmp_path).instance_id()
    assert path.read_text(encoding="utf-8") == content


PASSWORD = "correct-password"


def _identity_app(tmp_path: Path) -> web.Application:
    app = web.Application(middlewares=[web_server.auth_middleware])
    app[DEVICE_TOKENS_KEY] = DeviceTokenStore(tmp_path)
    app[SERVER_IDENTITY_KEY] = ServerIdentityStore(tmp_path)

    async def probe(request: web.Request) -> web.Response:
        return web.json_response({"paired_device_id": request.get(PAIRED_DEVICE_ID_KEY)})

    app.router.add_get("/api/config", web_server.api_config_get)
    app.router.add_get("/api/test-probe", probe)
    return app


@pytest.mark.asyncio
async def test_config_gives_the_instance_id_to_the_owner_only(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(web_server.STATE, "access_token", hash_access_password(PASSWORD))
    app = _identity_app(tmp_path)
    expected = ServerIdentityStore(tmp_path).instance_id()

    async with TestClient(TestServer(app)) as client:
        owner = await (await client.get(
            "/api/config", headers={"Authorization": f"Bearer {PASSWORD}"},
        )).json()
        anonymous = await (await client.get("/api/config")).json()

    assert owner["server_instance_id"] == expected
    assert "server_instance_id" not in anonymous


@pytest.mark.asyncio
async def test_middleware_records_the_paired_device_for_audit(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(web_server.STATE, "access_token", hash_access_password(PASSWORD))
    app = _identity_app(tmp_path)
    token, device = app[DEVICE_TOKENS_KEY].issue("phone")

    async with TestClient(TestServer(app)) as client:
        by_device = await (await client.get(
            "/api/test-probe", headers={"Authorization": f"Bearer {token}"},
        )).json()
        by_password = await (await client.get(
            "/api/test-probe", headers={"Authorization": f"Bearer {PASSWORD}"},
        )).json()
        anonymous = await client.get("/api/test-probe")

    assert by_device["paired_device_id"] == device["id"]
    assert by_password["paired_device_id"] == ""
    assert anonymous.status == 401


# ---- Review fixes: identity is server-only; robust instance id ---------------


def _lorebook_service(tmp_path: Path):
    from src.webui.services import lorebooks as lorebook_service

    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    deps = lorebook_service.LorebookDependencies(
        lorebook=store, get_instance=lambda _key: None, get_lore_retriever=lambda: None,
    )
    return lorebook_service, store, deps


_CLIENT_IDENTITY = {
    "source_kind": "device", "source_id": "install-1", "external_id": "book-1",
    "source_version": "9", "source_digest": "sha256:forged",
}


def test_generic_create_ignores_client_supplied_identity(tmp_path: Path):
    service, store, deps = _lorebook_service(tmp_path)
    try:
        result = service.create_lorebook(deps, {"id": "b1", "name": "B1", **_CLIENT_IDENTITY})

        assert result["ok"]
        book = store.get_lorebook("b1")
        assert (book["source_kind"], book["source_id"], book["external_id"]) == ("native", "", "")
        assert (book["source_version"], book["source_digest"]) == ("", "")
    finally:
        store.close()


def test_generic_update_ignores_client_supplied_identity(tmp_path: Path):
    service, store, deps = _lorebook_service(tmp_path)
    try:
        store.create_lorebook({
            "id": "b1", "name": "B1", "source_kind": "device", "source_id": "install-1",
            "external_id": "book-1", "source_version": "1", "source_digest": "sha256:real",
        })
        result = service.update_lorebook(deps, "b1", {
            "name": "Renamed", "source_kind": "plugin", "source_id": "other",
            "external_id": "squat", "source_version": "9", "source_digest": "sha256:forged",
        })

        assert result["ok"]
        book = store.get_lorebook("b1")
        assert book["name"] == "Renamed"
        assert (book["source_kind"], book["source_id"], book["external_id"]) == (
            "device", "install-1", "book-1",
        )
        assert (book["source_version"], book["source_digest"]) == ("1", "sha256:real")
    finally:
        store.close()


def test_identity_collision_is_a_structured_conflict(tmp_path: Path):
    from src.lorebook.store import LorebookIdentityConflict
    from src.webui.routes.lorebooks import _result_response

    service, store, deps = _lorebook_service(tmp_path)
    try:
        store.create_lorebook({
            "id": "first", "name": "First", "source_kind": "device",
            "source_id": "install-1", "external_id": "book-1",
        })
        with pytest.raises(LorebookIdentityConflict):
            store.create_lorebook({
                "id": "second", "name": "Second", "source_kind": "device",
                "source_id": "install-1", "external_id": "book-1",
            })

        class ConflictingStore:
            def get_lorebook(self, _book_id):
                return None

            def create_lorebook(self, _book):
                raise LorebookIdentityConflict("external identity is already tracked")

        result = service.create_lorebook(
            service.LorebookDependencies(
                lorebook=ConflictingStore(), get_instance=lambda _key: None,
                get_lore_retriever=lambda: None,
            ),
            {"id": "x", "name": "X"},
        )

        assert result["ok"] is False
        assert result["error_code"] == "LOREBOOK_IDENTITY_CONFLICT"
        assert _result_response(result).status == 409
    finally:
        store.close()


def test_damaged_identity_is_read_and_logged_once(tmp_path: Path, caplog):
    from src.webui.server_identity import server_instance_id

    path = tmp_path / "server_identity.json"
    path.write_text("not json", encoding="utf-8")
    app = web.Application()
    app[SERVER_IDENTITY_KEY] = ServerIdentityStore(tmp_path)

    with caplog.at_level("ERROR", logger="trpg"):
        results = [server_instance_id(app) for _ in range(3)]
        # The failure is remembered: a later repair needs a restart, not a re-read.
        path.write_text(json.dumps({"version": 1, "instance_id": "srv-" + "0" * 32}), encoding="utf-8")
        results.append(server_instance_id(app))

    assert results == [None, None, None, None]
    assert len([r for r in caplog.records if r.levelname == "ERROR"]) == 1


def test_concurrent_first_start_keeps_the_first_published_id(tmp_path: Path, monkeypatch):
    winner = ServerIdentityStore(tmp_path).instance_id()
    late = ServerIdentityStore(tmp_path)
    # The late process checked for the file before the winner published it.
    monkeypatch.setattr(type(late.path), "exists", lambda _self: False)

    assert late.instance_id() == winner
    monkeypatch.undo()
    assert json.loads((tmp_path / "server_identity.json").read_text(encoding="utf-8"))["instance_id"] == winner
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []
