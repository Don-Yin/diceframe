"""Future round-safety slots reject transactions before any live mutation."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.engine import instance_lifecycle, round_recovery, round_snapshots, turn_state
from src.engine.game_instance import GameRegistry, GameState
from src.engine.module_state import ModuleStateError
from src.engine.modules import round_safety
from src.engine.modules import combat_extension_state
from tests.test_game_instance_reset_characterization import _make_populated_instance


def live_state(instance):
    return {key: value for key, value in vars(instance).items() if not isinstance(value, asyncio.Lock)}


def unsupported_instance():
    instance = _make_populated_instance()
    instance.modules["round_safety"]["schema_version"] = 99
    # Reject before materializing unrelated slots, not only before gameplay writes.
    instance.modules.pop("economy", None)
    return instance


@pytest.mark.parametrize("raw", [None, [], "corrupt", {"schema_version": 1, "round_start_snapshot": None}])
def test_preflight_does_not_repair_slot(raw):
    instance = _make_populated_instance()
    instance.modules["round_safety"] = deepcopy(raw)
    before = deepcopy(live_state(instance))
    round_safety.require_writable(instance)
    assert live_state(instance) == before


def test_preflight_does_not_materialize_missing_slot():
    instance = _make_populated_instance()
    del instance.modules["round_safety"]
    before = deepcopy(live_state(instance))
    round_safety.require_writable(instance)
    assert live_state(instance) == before


@pytest.mark.parametrize("schema", [99, None, "1"])
def test_preflight_rejects_unknown_schema_without_mutation(schema):
    instance = unsupported_instance()
    instance.modules["round_safety"]["schema_version"] = schema
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match="unsupported round_safety module schema"):
        round_safety.require_writable(instance)
    assert live_state(instance) == before


@pytest.mark.parametrize("direct", [False, True], ids=["public", "locked"])
@pytest.mark.parametrize("operation", [
    "reset", "start_round", "finish_judgment", "rollback_last_round", "abort_round_processing",
])
@pytest.mark.asyncio
async def test_transaction_rejection_preserves_all_live_state(operation, direct):
    instance = unsupported_instance()
    combat_extension_state.current(instance)["pending_summaries"] = ["must remain pending"]
    args = ("new narration",) if operation == "finish_judgment" else ()
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match="unsupported round_safety module schema"):
        if direct:
            owner = (
                instance_lifecycle if operation == "reset"
                else turn_state if operation == "start_round" else round_recovery
            )
            async with instance._lock:
                getattr(owner, operation + "_locked")(instance, *args)
        else:
            await getattr(instance, operation)(*args)
    assert live_state(instance) == before


@pytest.mark.parametrize("operation", ["advance_round", "try_advance", "aggregate_locked", "owner_locked"])
@pytest.mark.asyncio
async def test_advance_rejects_before_readiness_snapshots_or_economy_materialization(operation):
    instance = unsupported_instance()
    instance.state = GameState.ACTIVE_ACTION
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match="unsupported round_safety module schema"):
        if operation == "aggregate_locked":
            async with instance._lock:
                instance._do_advance_locked()
        elif operation == "owner_locked":
            async with instance._lock:
                turn_state.do_advance_locked(instance)
        else:
            await getattr(instance, operation)()
    assert live_state(instance) == before


@pytest.mark.parametrize("operation,args", [
    ("capture_players", ({"u1": {"hp": 5}},)),
    ("replace_entity_snapshot", ({"npcs": {}},)),
    ("replace_death_save_outcomes", ({"3": {}},)),
    ("clear_snapshots", ()), ("discard_round", ()),
    ("keep_death_saves_for", ("3",)), ("death_save_cache", ("3",)),
])
def test_owner_entries_reject_before_mutation(operation, args):
    instance = unsupported_instance()
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match="unsupported round_safety module schema"):
        getattr(round_safety, operation)(instance, *args)
    assert live_state(instance) == before


@pytest.mark.parametrize("key", ["round_start_snapshot", "round_entity_snapshot", "death_save_outcomes"])
def test_ruleset_restore_preflights_snapshot_keys_before_other_restoration(key):
    instance = unsupported_instance()
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match="unsupported round_safety module schema"):
        instance.restore_ruleset_transaction({key: None, "ruleset_state": {"changed": True}})
    assert live_state(instance) == before


@pytest.mark.parametrize("direct", [False, True], ids=["aggregate", "owner"])
def test_entity_capture_rejects_without_modifying_snapshots_or_entities(direct):
    instance = unsupported_instance()
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match="unsupported round_safety module schema"):
        if direct:
            round_snapshots.capture_round_entity_snapshot(instance)
        else:
            instance.capture_round_entity_snapshot()
    assert live_state(instance) == before


def test_death_save_resolution_rejects_before_rng_cache_or_character_changes(monkeypatch):
    from src.commands import death_save_tracker

    instance = unsupported_instance()
    instance.players["u1"]["character_sheet"].update({"status": "downed", "hp": 0})
    before = deepcopy(live_state(instance))

    def forbidden_roll(*args):
        raise AssertionError("must not consume RNG before preflight")

    monkeypatch.setattr(death_save_tracker, "roll", forbidden_roll)
    rule = SimpleNamespace(death_mechanic={"hp_zero": "downed_death_saves"})
    with pytest.raises(ModuleStateError, match="unsupported round_safety module schema"):
        death_save_tracker.resolve_round_death_saves(instance, rule)
    assert live_state(instance) == before


@pytest.mark.parametrize("rule", [None, SimpleNamespace(death_mechanic={"hp_zero": "dead"})])
def test_death_save_read_only_early_return_precedes_preflight(rule):
    from src.commands.death_save_tracker import resolve_round_death_saves

    instance = unsupported_instance()
    before = deepcopy(live_state(instance))
    assert resolve_round_death_saves(instance, rule) == ""
    assert live_state(instance) == before


@pytest.mark.parametrize("operation", ["rollback", "abort", "advance", "stale_start"])
@pytest.mark.asyncio
async def test_existing_noop_guards_remain_before_preflight(operation):
    instance = unsupported_instance()
    if operation == "rollback":
        instance.log.clear()
    if operation in {"abort", "advance"}:
        instance.state = GameState.WAITING
    before = deepcopy(live_state(instance))
    if operation == "rollback":
        assert await instance.rollback_last_round() is None
    elif operation == "abort":
        assert await instance.abort_round_processing() is False
    elif operation == "advance":
        async with instance._lock:
            assert turn_state.do_advance_locked(instance) is False
    else:
        assert await instance.start_round(expected_run_id="stale") is None
    assert live_state(instance) == before


@pytest.mark.parametrize("operation", ["process_round", "process_round_impl"])
@pytest.mark.asyncio
async def test_round_processor_rejects_before_checks_death_saves_or_generation(tmp_path, operation):
    from src.commands.round_processor import RoundProcessor

    instance = unsupported_instance()
    registry = GameRegistry(tmp_path)
    registry.register(instance)
    processor = object.__new__(RoundProcessor)
    processor.registry = registry
    processor.llm_client = SimpleNamespace(call=AsyncMock())
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match="unsupported round_safety module schema"):
        await getattr(processor, operation)(instance)
    assert live_state(instance) == before
    processor.llm_client.call.assert_not_called()


@pytest.mark.asyncio
async def test_start_game_rejects_before_activation():
    from src.commands.game_lifecycle import GameLifecycle

    instance = unsupported_instance()
    lifecycle = object.__new__(GameLifecycle)
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match="unsupported round_safety module schema"):
        await lifecycle.start_game(instance)
    assert live_state(instance) == before


@pytest.mark.parametrize("operation", ["submit", "advance", "resume", "progression"])
@pytest.mark.asyncio
async def test_turn_services_reject_before_outbox_or_ai(tmp_path, monkeypatch, operation):
    from src.webui.services import turns

    instance = unsupported_instance()
    instance.state = GameState.ACTIVE_ACTION
    instance.gm_uid = "u1"
    registry = GameRegistry(tmp_path)
    registry.register(instance)
    dependencies = SimpleNamespace(
        get_instance=registry.get, parse_game_key=lambda key: instance.game_key,
        load_rule_for_game=lambda instance: None, resume_authoritative_combat=None,
    )
    retry = AsyncMock(side_effect=AssertionError("must not drain outbox"))
    fill = AsyncMock(side_effect=AssertionError("must not call AI"))
    monkeypatch.setattr(turns, "_retry_external_economy_effects", retry)
    monkeypatch.setattr(turns, "_fill_ai_player_actions", fill)
    instance.players["u1"]["control"] = {
        "mode": "human", "revision": 3, "temporary": False, "resume_mode": "human",
    }
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match="unsupported round_safety module schema"):
        if operation == "submit":
            await turns.submit_action(dependencies, "game", "u1", "Look")
        elif operation == "advance":
            await turns.advance_round(dependencies, "game", "u1", force=True)
        elif operation == "resume":
            await turns.resume_after_control_change(dependencies, "game")
        else:
            await turns._advance_progression(dependencies, instance, game_key="game")
    assert live_state(instance) == before
    retry.assert_not_called()
    fill.assert_not_called()
