"""Seat model routing: persistence, invalid references and in-flight fences."""
from __future__ import annotations

from legacy_save_fixtures import legacy_table_payload

import copy
import asyncio
import json
from types import SimpleNamespace

import pytest
from aiohttp import ClientConnectionError, ClientResponseError

from src.commands.ai_player import fill_ai_player_actions
from src.engine.game_instance import GameInstance, GameState
from src.engine.modules.ai_seats import effective_settings, update_settings
from src.engine.player_control import set_control
from src.migrations.instance import migrate_game_state_payload, CURRENT_INSTANCE_SCHEMA_VERSION
from src.webui.services.ai_seats import AISeatRuntime, AISeatService, AISeatDependencies


def table() -> GameInstance:
    inst = GameInstance(game_key=("web", "seats", "bot"), rule_id="freeform_fantasy")
    inst.state = GameState.ACTIVE_ACTION
    inst.round_number = 1
    inst.gm_uid = "h"
    for uid in ("h", "a", "b"):
        inst.put_player(uid, {"user_id": uid, "character_name": uid,
                              "character_sheet": {"hp": 10, "max_hp": 10}})
    for uid in ("a", "b"):
        set_control(inst, uid, "ai")
    inst.ready_players.add("h")
    return inst


def config() -> dict:
    return {"ai_providers": [
        {"id": "local", "name": "Local", "base_url": "http://localhost:1234/v1",
         "api_format": "openai", "models": ["small"], "model_capabilities": {"small": "chat"}},
        {"id": "other", "name": "Other", "base_url": "https://example.invalid/v1",
         "api_format": "anthropic", "models": ["large", "image"],
         "model_capabilities": {"large": "chat", "image": "image"}},
    ], "llm_provider_ref": "local", "model": "small", "ai_provider_key_other": "SECRET-KEY"}


class Client:
    def __init__(self, **kwargs):
        self.provider = kwargs["providers"][0]
        self.default = self.provider.provider_name
        self.calls = []
        self.closed = False
        self.during_call = None

    async def call(self, system, context, **_kwargs):
        self.calls.append((system, context))
        if self.during_call:
            self.during_call()
        return SimpleNamespace(narration="I check the window.", total_tokens=5)

    async def close(self):
        self.closed = True


def runtime(state, clients):
    def factory(**kwargs):
        client = Client(**kwargs)
        clients.append(client)
        return client
    return AISeatRuntime(config_state=lambda: state, client_factory=factory)


def set_settings(inst, settings, uid=None):
    update_settings(inst, settings, uid=uid, expected_revision=inst.modules["ai_seats"]["revision"])


def test_inheritance_round_trip_and_no_credentials_in_save():
    inst = table()
    set_settings(inst, {"provider_ref": "other", "model": "large", "style": "cautious"})
    set_settings(inst, {"style": "bold"}, "a")
    restored = GameInstance.from_dict(copy.deepcopy(inst.to_dict()))
    assert effective_settings(restored, "a") == {"provider_ref": "other", "model": "large", "style": "bold"}
    assert effective_settings(restored, "b")["style"] == "cautious"
    clients = []
    view = runtime(config(), clients).project(restored)
    assert view["seats"]["a"]["model"] == "large"
    assert "SECRET-KEY" not in json.dumps(restored.to_dict())
    assert "base_url" not in json.dumps(view)
    assert "api_key" not in json.dumps(view)


@pytest.mark.parametrize("settings", [
    {"base_url": "http://old"}, {"api_key": "secret"}, {"api_format": "openai"},
    {"provider_ref": False}, {"model": " "}, {"style": "invented"},
])
def test_reject_bad_or_legacy_fields_without_mutating(settings):
    inst = table()
    before = copy.deepcopy(inst.modules)
    with pytest.raises(ValueError):
        set_settings(inst, settings, "a")
    assert inst.modules == before


def test_stale_edit_and_future_schema_fail_closed():
    inst = table()
    set_settings(inst, {"style": "cautious"}, "a")
    with pytest.raises(ValueError, match="revision"):
        update_settings(inst, {"style": "bold"}, uid="a", expected_revision=0)
    unknown = {"schema_version": 91, "future": {"x": 3}}
    inst.modules["ai_seats"] = copy.deepcopy(unknown)
    view = runtime(config(), []).project(inst)
    assert view["seats"]["a"]["reason"] == "unsupported_settings"
    assert not view["seats"]["a"]["ready"]
    restored = GameInstance.from_dict(copy.deepcopy(inst.to_dict()))
    assert restored.modules["ai_seats"] == unknown


@pytest.mark.asyncio
async def test_each_seat_uses_its_provider_model_and_style():
    inst, clients = table(), []
    set_settings(inst, {"provider_ref": "other", "model": "large", "style": "cautious"}, "a")
    engine = runtime(config(), clients)
    outcomes = await fill_ai_player_actions(inst, llm_client=None, seat_runtime=engine)
    assert [row["status"] for row in outcomes] == ["added", "added"]
    assert [c.provider.model_name for c in clients] == ["large", "small"]
    assert clients[0].provider.api_key == "SECRET-KEY"
    assert clients[1].provider.api_key == ""  # local provider permits an empty key
    assert "cautious" in clients[0].calls[0][0].lower()
    assert "Do not act, speak or decide" in clients[0].calls[0][0] or "不替其他角色" in clients[0].calls[0][0]
    assert all(c.closed for c in clients)
    assert engine.project(inst)["seats"]["a"]["last_outcome"]["status"] == "added"


@pytest.mark.asyncio
@pytest.mark.parametrize("change,reason", [
    ("delete", "provider_missing"), ("capability", "model_not_chat"), ("model", "model_missing"),
])
async def test_invalid_reference_never_calls_shared_client(change, reason):
    inst, state, clients = table(), config(), []
    set_settings(inst, {"provider_ref": "other", "model": "large"}, "a")
    if change == "delete":
        state["ai_providers"].pop()
    elif change == "capability":
        state["ai_providers"][1]["model_capabilities"]["large"] = "image"
    else:
        state["ai_providers"][1]["models"].remove("large")
    shared = Client(providers=[SimpleNamespace(provider_name="shared")])
    engine = runtime(state, clients)
    outcomes = await fill_ai_player_actions(inst, llm_client=shared, seat_runtime=engine)
    assert outcomes[0]["status"] == "skipped"
    assert outcomes[0]["reason"] == reason
    assert not shared.calls
    assert len(clients) == 1 and clients[0].provider.model_name == "small"
    assert not engine.project(inst)["seats"]["a"]["ready"]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["seat", "default", "provider"])
async def test_config_changed_during_generation_discards_action(change):
    inst, state, clients = table(), config(), []
    def factory(**kwargs):
        client = Client(**kwargs)
        clients.append(client)
        if len(clients) == 1:
            def mutate():
                if change == "provider":
                    state["ai_providers"].clear()
                else:
                    set_settings(inst, {"style": "cautious"}, "a" if change == "seat" else None)
            client.during_call = mutate
        return client
    engine = AISeatRuntime(config_state=lambda: state, client_factory=factory)
    outcomes = await fill_ai_player_actions(inst, llm_client=None, seat_runtime=engine)
    assert outcomes[0]["status"] == "discarded"
    assert outcomes[0]["reason"] == "ai_config_changed"
    assert not any(row["user_id"] == "a" for row in inst.action_queue)
    assert clients[0].closed


@pytest.mark.asyncio
async def test_retry_respects_human_gate_and_never_replaces_committed_action():
    inst, state = table(), config()
    calls = []
    async def save(_inst):
        pass
    async def resume(game_key, uid):
        calls.append((game_key, uid))
        return {"payload": {"ok": True, "resumed": False}}
    service = AISeatService(AISeatDependencies(lambda _key: inst, save, resume), runtime(state, []))
    assert (await service.retry("g", "a"))["ok"]
    await inst.add_action("a", "Already committed.")
    assert (await service.retry("g", "a"))["error_code"] == "already_declared"
    inst.ready_players.clear()
    assert (await service.retry("g", "b"))["error_code"] == "waiting_humans"
    assert calls == [("g", "a")]


def test_corrupt_known_schema_does_not_leak_unrecognized_fields():
    inst = table()
    slot = inst.modules["ai_seats"]
    slot["seats"]["a"] = {"api_key": "IMPORTED-SECRET"}
    slot["outcomes"]["a"] = {"run_id": inst.run_id, "status": "skipped", "reason": "IMPORTED-SECRET", "raw": "IMPORTED-SECRET"}
    view = runtime(config(), []).project(inst)
    assert not view["seats"]["a"]["ready"]
    assert "IMPORTED-SECRET" not in json.dumps(view)


@pytest.mark.asyncio
async def test_provider_removal_after_response_before_locked_commit_is_rejected():
    inst, state = table(), config()
    returned = asyncio.Event()
    def factory(**kwargs):
        client = Client(**kwargs)
        client.during_call = returned.set
        return client
    engine = AISeatRuntime(config_state=lambda: state, client_factory=factory)
    await inst._lock.acquire()
    task = asyncio.create_task(fill_ai_player_actions(inst, llm_client=None, seat_runtime=engine))
    try:
        await asyncio.wait_for(returned.wait(), 2)
        state["ai_providers"].clear()
    finally:
        inst._lock.release()
    rows = await task
    assert rows[0]["reason"] == "ai_config_changed"
    assert not inst.action_queue


@pytest.mark.asyncio
async def test_other_seat_edit_does_not_invalidate_this_seat_generation():
    inst, clients = table(), []
    def factory(**kwargs):
        client = Client(**kwargs)
        clients.append(client)
        if len(clients) == 1:
            client.during_call = lambda: set_settings(inst, {"style": "bold"}, "b")
        return client
    engine = AISeatRuntime(config_state=config, client_factory=factory)
    rows = await fill_ai_player_actions(inst, llm_client=None, seat_runtime=engine)
    assert [row["status"] for row in rows] == ["added", "added"]
    assert "bold" in clients[1].calls[0][0]


@pytest.mark.asyncio
async def test_reset_keeps_game_defaults_but_removes_seat_overrides_and_failure_history():
    inst = table()
    set_settings(inst, {"style": "cautious"})
    set_settings(inst, {"style": "bold"}, "a")
    engine = runtime(config(), [])
    await fill_ai_player_actions(inst, llm_client=None, seat_runtime=engine)
    await inst.reset()
    assert inst.modules["ai_seats"]["defaults"]["style"] == "cautious"
    assert inst.modules["ai_seats"]["seats"] == {}
    assert inst.modules["ai_seats"]["outcomes"] == {}


@pytest.mark.asyncio
async def test_removed_seat_does_not_leave_an_override_for_a_reused_uid():
    inst = table()
    set_settings(inst, {"style": "bold"}, "a")
    engine = runtime(config(), [])
    await fill_ai_player_actions(inst, llm_client=None, seat_runtime=engine)
    assert await inst.remove_player("a")
    assert "a" not in inst.modules["ai_seats"]["seats"]
    assert "a" not in inst.modules["ai_seats"]["outcomes"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,reason", [
    (TimeoutError("SECRET"), "provider_timeout"),
    (ClientConnectionError("SECRET"), "provider_connection_failed"),
    (ClientResponseError(SimpleNamespace(real_url="SECRET"), (), status=401, message="SECRET"), "provider_auth_failed"),
    (ClientResponseError(SimpleNamespace(real_url="SECRET"), (), status=429, message="SECRET"), "provider_rate_limited"),
])
async def test_failure_causes_are_safe_readable_codes_and_survive_reload(failure, reason):
    inst = table()
    def factory(**kwargs):
        client = Client(**kwargs)
        def fail():
            raise RuntimeError("provider failure SECRET") from failure
        client.during_call = fail
        return client
    engine = AISeatRuntime(config_state=config, client_factory=factory)
    records = await fill_ai_player_actions(inst, llm_client=None, seat_runtime=engine)
    assert records[0]["reason"] == reason
    restored = GameInstance.from_dict(copy.deepcopy(inst.to_dict()))
    view = runtime(config(), []).project(restored)
    assert view["seats"]["a"]["last_outcome"]["reason"] == reason
    assert not view["seats"]["a"]["generating"]
    assert "SECRET" not in json.dumps(view)


@pytest.mark.asyncio
async def test_failed_settings_save_restores_the_previous_policy():
    inst = table()
    before = copy.deepcopy(inst.modules["ai_seats"])
    async def fail_save(_inst):
        raise OSError("disk failed")
    async def resume(_key, _uid):
        raise AssertionError("Settings save must not advance the game")
    service = AISeatService(AISeatDependencies(lambda _key: inst, fail_save, resume), runtime(config(), []))
    with pytest.raises(OSError):
        await service.update("g", {"settings": {"style": "bold"}, "expected_revision": 0}, "a")
    assert inst.modules["ai_seats"] == before


def test_v35_migration_materializes_reference_only_policy_and_preserves_future_slot():
    old = copy.deepcopy(table().to_dict())
    old = legacy_table_payload(old)
    old["instance_schema_version"] = 35
    old["modules"].pop("ai_seats")
    migrated = migrate_game_state_payload(old)
    assert migrated["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert migrated["modules"]["ai_seats"]["defaults"] == {"provider_ref": None, "model": None, "style": "character"}
    assert migrated["players"] == old["players"]
    assert migrate_game_state_payload(migrated) == migrated
    old["modules"]["ai_seats"] = {"schema_version": 91, "future": [1, 2]}
    assert migrate_game_state_payload(old)["modules"]["ai_seats"] == old["modules"]["ai_seats"]
