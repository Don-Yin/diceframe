"""Future narrative_notes slots reject scene-writing transactions before any mutation."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.engine import instance_lifecycle
from src.engine.game_instance import GameRegistry
from src.engine.module_state import ModuleStateError
from src.engine.modules import narrative_notes
from tests.test_game_instance_reset_characterization import _make_populated_instance
from webapi_harness import web_api  # noqa: F401

MATCH = "unsupported narrative_notes module schema"


def live_state(instance):
    return {key: value for key, value in vars(instance).items() if not isinstance(value, asyncio.Lock)}


def unsupported_instance():
    instance = _make_populated_instance()
    instance.modules["narrative_notes"]["schema_version"] = 99
    # Reject before materializing unrelated slots, not only before gameplay writes.
    instance.modules.pop("economy", None)
    return instance


@pytest.mark.parametrize("raw", [None, [], "corrupt", {"schema_version": 2, "scene": None}])
def test_preflight_does_not_repair_slot(raw):
    instance = _make_populated_instance()
    instance.modules["narrative_notes"] = deepcopy(raw)
    before = deepcopy(live_state(instance))
    narrative_notes.require_writable(instance)
    assert live_state(instance) == before


def test_preflight_does_not_materialize_missing_slot():
    instance = _make_populated_instance()
    del instance.modules["narrative_notes"]
    before = deepcopy(live_state(instance))
    narrative_notes.require_writable(instance)
    assert live_state(instance) == before


@pytest.mark.parametrize("schema", [99, 1, None, "2"])
def test_preflight_rejects_unknown_schema_without_mutation(schema):
    instance = unsupported_instance()
    instance.modules["narrative_notes"]["schema_version"] = schema
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match=MATCH):
        narrative_notes.require_writable(instance)
    assert live_state(instance) == before


@pytest.mark.parametrize("write", ["replace_scene", "set_scene"])
def test_scene_writes_reject_before_mutation(write):
    instance = unsupported_instance()
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match=MATCH):
        if write == "set_scene":
            instance.set_scene("elsewhere")
        else:
            narrative_notes.replace_scene(instance, "elsewhere")
    assert live_state(instance) == before


@pytest.mark.parametrize("direct", [False, True], ids=["public", "locked"])
@pytest.mark.asyncio
async def test_reset_rejects_before_rotating_or_clearing(direct):
    instance = unsupported_instance()
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match=MATCH):
        if direct:
            async with instance._lock:
                instance_lifecycle.reset_locked(instance)
        else:
            await instance.reset()
    assert live_state(instance) == before


def test_ruleset_restore_with_scene_rejects_before_other_restoration():
    instance = unsupported_instance()
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match=MATCH):
        instance.restore_ruleset_transaction({"scene": "x", "ruleset_state": {"changed": True}, "players": {}})
    assert live_state(instance) == before


@pytest.mark.parametrize("operation", ["process_round", "process_round_impl"])
@pytest.mark.asyncio
async def test_round_processor_rejects_before_generation(tmp_path, operation):
    from src.commands.round_processor import RoundProcessor

    instance = unsupported_instance()
    registry = GameRegistry(tmp_path)
    registry.register(instance)
    processor = object.__new__(RoundProcessor)
    processor.registry = registry
    processor.llm_client = SimpleNamespace(call=AsyncMock())
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match=MATCH):
        await getattr(processor, operation)(instance)
    assert live_state(instance) == before
    processor.llm_client.call.assert_not_called()


@pytest.mark.parametrize("operation", ["start_game", "_start_reset_instance"])
@pytest.mark.asyncio
async def test_run_opening_rejects_before_activation(operation):
    from src.commands.game_lifecycle import GameLifecycle

    instance = unsupported_instance()
    lifecycle = object.__new__(GameLifecycle)
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match=MATCH):
        await getattr(lifecycle, operation)(instance)
    assert live_state(instance) == before


@pytest.mark.asyncio
async def test_swipe_rejects_before_staging_or_generation():
    from src.commands.swipe_generator import SwipeGenerator

    instance = unsupported_instance()
    generator = object.__new__(SwipeGenerator)
    generator._generate_locked = AsyncMock(side_effect=AssertionError("must not generate"))
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match=MATCH):
        await generator.generate(instance, 1)
    assert live_state(instance) == before
    generator._generate_locked.assert_not_called()


def test_director_automation_rejects_before_any_batch():
    from src.rulesets.automation import apply_director_automation

    class _Runtime:
        def director_automatic_intent(self, instance, proposal):
            return {"type": "start"}

        def resolve_intent(self, instance, intent, rng):
            raise AssertionError("must not resolve")

        def apply_event_batch(self, instance, batch):
            raise AssertionError("must not apply")

    instance = unsupported_instance()
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match=MATCH):
        apply_director_automation(_Runtime(), instance, {"kind": "combat"}, object())
    assert live_state(instance) == before


def test_dnd_event_batch_rejects_before_ruleset_state_changes():
    from src.rulesets.dnd2024.runtime import Dnd2024Runtime

    instance = unsupported_instance()
    runtime = object.__new__(Dnd2024Runtime)
    runtime.load_bundle = Mock(side_effect=AssertionError("must not load"))
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match=MATCH):
        runtime.apply_event_batch(instance, {"intent_type": "dnd2024.campaign.choose"})
    assert live_state(instance) == before


@pytest.mark.asyncio
async def test_legacy_state_update_shim_rejects_before_any_write(web_api):
    api, _lorebook, _registry, _llm, _worlds = web_api
    instance = unsupported_instance()
    instance.players["u1"]["character_sheet"]["hp"] = 10
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match=MATCH):
        api._handler._apply_state_update(instance, {
            "players": {"u1": {"hp": 1}}, "scene_change": "elsewhere",
        })
    assert live_state(instance) == before
