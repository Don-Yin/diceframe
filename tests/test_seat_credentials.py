"""Per-seat share credentials: storage contract only (hash-only, never exported)."""

from __future__ import annotations

import json
import zipfile
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.commands.game_lifecycle import GameLifecycle
from src.engine.game_instance import GameInstance
from src.engine.module_state import ModuleStateError
from src.engine.modules import room_access as module
from src.migrations.instance import (
    CURRENT_INSTANCE_SCHEMA_VERSION,
    _migrate_v36_to_v37,
    migrate_game_state_payload,
    rebind_imported_game_state_payload,
)
from src.webui.services import game_packages

pytest_plugins = ["tests.webapi_harness"]

V1_SLOT = {
    "schema_version": 1,
    "max_players": 4,
    "player_access_open": False,
    "bot_bind_token": "bind",
    "room_password": "pw",
    "room_token": "rt",
}


def _instance() -> GameInstance:
    instance = GameInstance(game_key=("web", "seat", "bot"), gm_uid="gm")
    instance.players = {
        uid: {"character_name": uid, "character_sheet": {}} for uid in ("p1", "p2")
    }
    return instance


# ---- v36 -> v37 migration ------------------------------------------------


V2_FRESH = {
    "schema_version": 2,
    "max_players": 6,
    "player_access_open": True,
    "bot_bind_token": "",
    "room_password": "",
    "room_token": "",
    "seat_credentials": {},
}


def test_v36_save_gets_empty_credentials_without_mutating_input() -> None:
    original = {"instance_schema_version": 36, "modules": {"room_access": deepcopy(V1_SLOT)}}
    before = deepcopy(original)
    step = _migrate_v36_to_v37(deepcopy(original))
    assert step["instance_schema_version"] == 37
    assert step["modules"]["room_access"] == {**V1_SLOT, "schema_version": 2, "seat_credentials": {}}
    migrated = migrate_game_state_payload(original)
    assert original == before
    assert migrated["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert migrated["modules"]["room_access"]["seat_credentials"] == {}
    assert migrate_game_state_payload(migrated) == migrated


@pytest.mark.parametrize("slot", [
    {"schema_version": 2, "seat_credentials": {"p1": {"hash": "x", "issued_at": "t", "epoch": 3}}},
    {"schema_version": 9, "opaque": True},
])
def test_migration_never_touches_a_v2_or_future_slot(slot) -> None:
    payload = {"instance_schema_version": 36, "modules": {"room_access": deepcopy(slot)}}
    assert _migrate_v36_to_v37(payload)["modules"]["room_access"] == slot


@pytest.mark.parametrize("modules", [None, [], "corrupt", {}])
def test_migration_tolerates_missing_or_non_dict_modules(modules) -> None:
    migrated = _migrate_v36_to_v37({"instance_schema_version": 36, "modules": modules})
    slot = migrated["modules"]["room_access"]
    assert slot == V2_FRESH
    assert migrated["instance_schema_version"] == 37


# ---- issue / verify / revoke ----------------------------------------------


def test_issue_verify_round_trip_and_only_digest_is_stored() -> None:
    instance = _instance()
    token = module.issue_seat_token(instance, "p1")
    assert len(token) >= 32
    assert module.verify_seat_token(instance, token) == "p1"
    record = instance.modules["room_access"]["seat_credentials"]["p1"]
    assert set(record) == {"hash", "issued_at", "epoch"}
    assert record["epoch"] == 1
    assert token not in json.dumps(instance.to_dict())


@pytest.mark.parametrize("bad", ["", "nope", None, 123])
def test_wrong_or_malformed_tokens_do_not_verify(bad) -> None:
    instance = _instance()
    module.issue_seat_token(instance, "p1")
    assert module.verify_seat_token(instance, bad) is None  # type: ignore[arg-type]


def test_tokens_are_per_seat() -> None:
    instance = _instance()
    first = module.issue_seat_token(instance, "p1")
    second = module.issue_seat_token(instance, "p2")
    assert first != second
    assert module.verify_seat_token(instance, first) == "p1"
    assert module.verify_seat_token(instance, second) == "p2"


def test_reissue_invalidates_the_old_token_and_bumps_epoch() -> None:
    instance = _instance()
    old = module.issue_seat_token(instance, "p1")
    new = module.issue_seat_token(instance, "p1")
    assert module.verify_seat_token(instance, old) is None
    assert module.verify_seat_token(instance, new) == "p1"
    assert instance.modules["room_access"]["seat_credentials"]["p1"]["epoch"] == 2


def test_revoke_removes_the_credential() -> None:
    instance = _instance()
    token = module.issue_seat_token(instance, "p1")
    assert module.revoke_seat_token(instance, "p1") is True
    assert module.verify_seat_token(instance, token) is None
    assert module.revoke_seat_token(instance, "p1") is False
    assert module.has_seat_token(instance, "p1") is False


def test_issue_requires_a_uid() -> None:
    with pytest.raises(ValueError):
        module.issue_seat_token(_instance(), "")


def test_tokens_from_another_game_do_not_verify() -> None:
    other = GameInstance(game_key=("web", "other", "bot"))
    token = module.issue_seat_token(other, "p1")
    instance = _instance()
    module.issue_seat_token(instance, "p1")
    assert module.verify_seat_token(instance, token) is None


# ---- persistence / lifecycle ----------------------------------------------


def test_codec_round_trip_keeps_digest_and_still_verifies() -> None:
    instance = _instance()
    token = module.issue_seat_token(instance, "p1")
    payload = instance.to_dict()
    assert token not in json.dumps(payload)
    restored = GameInstance.from_dict(payload)
    assert module.verify_seat_token(restored, token) == "p1"


@pytest.mark.asyncio
async def test_reset_empties_seats_so_their_credentials_stop_verifying() -> None:
    instance = _instance()
    token = module.issue_seat_token(instance, "p1")
    await instance.reset()
    assert instance.players == {}
    # A credential never outlives its seat.
    assert module.verify_seat_token(instance, token) is None


def _lifecycle(candidate: GameInstance) -> GameLifecycle:
    return GameLifecycle(
        registry=Mock(), llm_client=Mock(), prompt=Mock(), state_applier=Mock(),
        ensure_matcher_for_world=Mock(), create_game=AsyncMock(return_value=candidate),
        load_world_template=Mock(), narrative_max_tokens=100, brief_max_tokens=100,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("preserve_players, carried", [(True, True), (False, False)])
async def test_new_run_carries_credentials_only_when_seats_are_kept(preserve_players, carried) -> None:
    source = _instance()
    token = module.issue_seat_token(source, "p1")
    candidate = GameInstance(game_key=source.game_key)
    result = await _lifecycle(candidate)._new_run_candidate(source, preserve_players=preserve_players)
    assert (module.verify_seat_token(result, token) == "p1") is carried


def test_writers_reject_future_schema_without_mutation() -> None:
    slot = {"schema_version": 9, "opaque": True}
    instance = GameInstance(game_key=("web", "future", "bot"), modules={"room_access": deepcopy(slot)})
    for call in (
        lambda: module.issue_seat_token(instance, "p1"),
        lambda: module.revoke_seat_token(instance, "p1"),
    ):
        with pytest.raises(ModuleStateError, match="unsupported room_access module schema"):
            call()
    assert instance.modules["room_access"] == slot


@pytest.mark.parametrize("raw", [None, [], "corrupt"])
def test_preflight_does_not_repair_or_materialize(raw) -> None:
    instance = SimpleNamespace(modules={"room_access": deepcopy(raw)})
    module.require_writable(instance)
    assert instance.modules == {"room_access": raw}
    empty = SimpleNamespace(modules={})
    module.require_writable(empty)
    assert empty.modules == {}


# ---- never leaves this host -----------------------------------------------


def test_import_drops_credentials_minted_elsewhere() -> None:
    instance = _instance()
    module.issue_seat_token(instance, "p1")
    payload = rebind_imported_game_state_payload(
        instance.to_dict(), game_key=("web", "imported", "bot"), run_id="run-2",
    )
    assert payload["modules"]["room_access"]["seat_credentials"] == {}


def test_export_package_never_contains_credentials(tmp_path) -> None:
    instance = _instance()
    module.issue_seat_token(instance, "p1")
    key = ("web", "seat", "bot")
    save_path = tmp_path / "state.json"
    save_path.write_text(json.dumps(instance.to_dict()), encoding="utf-8")
    service = game_packages.GamePackageService(game_packages.GamePackageDependencies(
        parse_game_key=lambda game_key: tuple(game_key.split("|")),
        get_instance=lambda _key: SimpleNamespace(gm_uid="gm", world_name="w"),
        state_path_for=lambda _key: save_path,
        import_save_zip=AsyncMock(),
        resolve_scene_image_file=lambda _reference: None,
        resolve_map_background_file=lambda _reference: None,
        save_scene_image_upload=lambda _payload: {"ok": True},
        save_map_background_upload=lambda _payload: {"ok": True},
    ))
    result = service.export_game_package("|".join(key))
    assert result["ok"] is True
    with zipfile.ZipFile(BytesIO(result["payload"])) as archive:
        state = json.loads(archive.read("state.json"))
    assert state["modules"]["room_access"]["seat_credentials"] == {}


@pytest.mark.asyncio
async def test_game_detail_never_exposes_credentials(web_api) -> None:
    api, _lorebook, registry, _llm, _worlds_dir = web_api
    created = await api.create_game(
        "template_world",
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )
    instance = registry.get(api._parse_key(created["game_key"]))
    uid = next(iter(instance.players))
    module.issue_seat_token(instance, uid)
    digest = instance.modules["room_access"]["seat_credentials"][uid]["hash"]
    for viewer, is_gm in ((uid, False), (instance.gm_uid, True), ("", False)):
        detail = json.dumps(api.game_detail(created["game_key"], viewer, is_gm), ensure_ascii=False, default=str)
        assert "seat_credentials" not in detail
        assert digest not in detail


def test_credential_of_a_removed_seat_does_not_verify() -> None:
    instance = _instance()
    token = module.issue_seat_token(instance, "p1")
    del instance.players["p1"]
    assert module.verify_seat_token(instance, token) is None


@pytest.mark.asyncio
async def test_remove_player_revokes_its_credential() -> None:
    instance = _instance()
    token = module.issue_seat_token(instance, "p1")
    assert await instance.remove_player("p1") is True
    assert not module.has_seat_token(instance, "p1")
    instance.players["p1"] = {"character_name": "back", "character_sheet": {}}
    assert module.verify_seat_token(instance, token) is None


@pytest.mark.asyncio
async def test_new_run_copies_credentials_only_for_kept_seats() -> None:
    source = _instance()
    kept = module.issue_seat_token(source, "p1")
    gone = module.issue_seat_token(source, "p2")
    candidate = GameInstance(game_key=source.game_key)
    candidate.players = {"p1": dict(source.players["p1"])}
    module.copy_seat_credentials(candidate, source)
    assert set(candidate.modules["room_access"]["seat_credentials"]) == {"p1"}
    assert module.verify_seat_token(candidate, kept) == "p1"
    assert module.verify_seat_token(candidate, gone) is None


@pytest.mark.asyncio
async def test_game_creation_never_mints_a_token_for_the_gm_seat(web_api) -> None:
    api, _lorebook, registry, _llm, _worlds_dir = web_api
    result = await api.create_game(
        "template_world",
        players=[
            {"character_name": "GM seat", "attributes": {"str": 10}},
            {"character_name": "Party", "attributes": {"str": 11}},
        ],
    )
    assert result["ok"] is True
    instance = registry.get(api._parse_key(result["game_key"]))
    gm_uid = instance.gm_uid
    assert result["players"][0]["user_id"] == gm_uid
    assert "seat_token" not in result["players"][0]
    assert not module.has_seat_token(instance, gm_uid)
    other = result["players"][1]
    assert module.verify_seat_token(instance, other["seat_token"]) == other["user_id"]
