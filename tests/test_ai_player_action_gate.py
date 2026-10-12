"""R4-b1: narrative AI fill must respect authoritative-intent admission."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.commands.ai_player import AI_ACTION_SOURCE, fill_ai_player_actions
from src.commands.game_handler import GameHandler
from src.engine.action_gate import STRUCTURED_INTENT_REQUIRED
from src.engine.game_state import GameState
from src.engine.player_control import get_control, set_control
from src.rulesets.contracts import RulesetCapabilities
from src.rulesets.registry import RulesetRuntimeRegistry
from src.webui.services import turns
from tests.test_ai_player_combat import _setup, _start
from tests.test_ai_player_exploration import FakePlayerLLM, make_dependencies, make_instance
from src.engine.modules import ruleset_runtime


def production_dependencies(instance, llm, runtime):
    handler = SimpleNamespace(llm_client=llm, _prompt=None)
    return replace(
        make_dependencies(instance, llm_client=llm),
        load_rule_for_game=lambda _instance: SimpleNamespace(
            template={"runtime": runtime.runtime_id},
        ),
        ruleset_registry=RulesetRuntimeRegistry([runtime]),
        fill_ai_player_actions=GameHandler.fill_ai_player_actions.__get__(handler),
    )


def commit_arguments(instance, uid="a1"):
    return dict(
        source=AI_ACTION_SOURCE,
        expected_run_id=instance.run_id,
        expected_round_number=instance.round_number,
        expected_control_revision=get_control(instance, uid)["revision"],
        action_metadata={"source": AI_ACTION_SOURCE, "generated_for_round": instance.round_number},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("all_ai", [False, True])
async def test_service_fill_during_real_authoritative_combat_does_not_enqueue(all_ai):
    runtime, engine, instance = _setup()
    instance.state = GameState.ACTIVE_ACTION
    instance.round_number = 1
    if all_ai:
        set_control(instance, "gm", "ai")
    else:
        assert await instance.add_action("gm", "I watch the door.")
    _start(engine, instance, rolls=[15, 10, 5])
    assert ruleset_runtime.state(instance)["combat"]["status"] == "active"
    assert runtime.capabilities.authoritative_intents
    before = list(instance.action_queue)
    llm = FakePlayerLLM()
    # Exercise the production facade as well as the real command and commit.
    deps = production_dependencies(instance, llm, runtime)

    wrote = await turns._fill_ai_player_actions(deps, instance, game_key="test")

    assert instance.action_queue == before
    assert wrote is False
    assert not llm.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("all_ai", [False, True])
@pytest.mark.parametrize("authoritative,narrative,active,blocked", [
    (True, True, True, True),
    (True, True, False, False),
    (True, False, False, True),
    (True, False, True, True),
    (False, True, True, False),
    (False, True, False, False),
    (False, False, True, False),
    (False, False, False, False),
])
async def test_service_uses_capabilities_not_ruleset_identity(
    all_ai, authoritative, narrative, active, blocked,
):
    instance = make_instance(humans=() if all_ai else ("h1",), ai=("a1",))
    if not all_ai:
        assert await instance.add_action("h1", "I watch.")
    ruleset_runtime.replace_state(instance, {"combat": {"status": "active" if active else "ended"}})
    runtime = SimpleNamespace(
        runtime_id="test:other-ruleset", runtime_version=1,
        capabilities=RulesetCapabilities(
            authoritative_intents=authoritative, narrative_turns=narrative,
        ),
    )
    llm = FakePlayerLLM()
    deps = production_dependencies(instance, llm, runtime)
    before = list(instance.action_queue)

    wrote = await turns._fill_ai_player_actions(deps, instance, game_key="test")

    assert wrote is not blocked
    assert len(llm.calls) == (0 if blocked else 1)
    assert len(instance.action_queue) == len(before) + (0 if blocked else 1)
    assert instance.action_queue[:len(before)] == before


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unknown", "incompatible", "missing-rule"])
@pytest.mark.parametrize("during_generation", [False, True])
async def test_service_runtime_unavailable_fails_closed(failure, during_generation):
    runtime, _engine, instance = _setup()
    instance.state = GameState.ACTIVE_ACTION
    set_control(instance, "gm", "ai")
    template = {"runtime": runtime.runtime_id}
    rule = SimpleNamespace(template=template)

    def invalidate(*_args):
        nonlocal rule
        if failure == "unknown":
            template["runtime"] = "test:not-installed"
        elif failure == "incompatible":
            template["runtime"] = {"id": runtime.runtime_id, "minimum_version": 999}
        else:
            rule = None

    llm = FakePlayerLLM(on_call=invalidate if during_generation else None)
    deps = replace(
        production_dependencies(instance, llm, runtime),
        load_rule_for_game=lambda _instance: rule,
    )
    if not during_generation:
        invalidate()

    assert not await turns._fill_ai_player_actions(deps, instance, game_key="test")
    assert not instance.action_queue
    assert len(llm.calls) == int(during_generation)


@pytest.mark.asyncio
@pytest.mark.parametrize("all_ai", [False, True])
async def test_service_discards_generation_when_real_combat_starts_during_await(all_ai):
    runtime, engine, instance = _setup()
    instance.state = GameState.ACTIVE_ACTION
    instance.round_number = 1
    if all_ai:
        set_control(instance, "gm", "ai")
    else:
        assert await instance.add_action("gm", "I watch.")
    before = list(instance.action_queue)
    started, release = asyncio.Event(), asyncio.Event()

    class DelayedLLM(FakePlayerLLM):
        async def call(self, *args, **kwargs):
            started.set()
            await release.wait()
            return await super().call(*args, **kwargs)

    llm = DelayedLLM()
    deps = production_dependencies(instance, llm, runtime)
    task = asyncio.create_task(turns._fill_ai_player_actions(deps, instance, game_key="test"))
    try:
        await asyncio.wait_for(started.wait(), 5)
        async with instance.authoritative_write() as entered, instance._lock:
            assert entered
            _start(engine, instance, rolls=[15, 10, 5])
        release.set()
        assert not await asyncio.wait_for(task, 5)
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert ruleset_runtime.state(instance)["combat"]["status"] == "active"
    assert instance.action_queue == before
    # On an all-AI table the second seat is blocked before another model call.
    assert len(llm.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("requirement", [False, None, lambda: False, True, lambda: True])
async def test_direct_commit_optional_requirement(requirement):
    instance = make_instance(humans=(), ai=("a1",))
    reason = await instance.commit_ai_player_action(
        "a1", "I watch.", **commit_arguments(instance),
        requires_structured_intent=requirement,
    )
    blocked = requirement() if callable(requirement) else bool(requirement)
    assert reason == (STRUCTURED_INTENT_REQUIRED if blocked else "")
    assert len(instance.action_queue) == (0 if blocked else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [
    "run_changed", "round_changed", "seat_removed", "control_changed",
    "phase_changed", "human_gate_changed", "duplicate",
])
async def test_direct_commit_existing_reason_precedes_structured_guard(reason):
    instance = make_instance(humans=(), ai=("a1",))
    args = commit_arguments(instance)
    if reason == "run_changed":
        args["expected_run_id"] = "old-run"
    elif reason == "round_changed":
        args["expected_round_number"] -= 1
    elif reason == "seat_removed":
        instance.players.pop("a1")
    elif reason == "control_changed":
        set_control(instance, "a1", "human")
    elif reason == "phase_changed":
        instance.state = GameState.ACTIVE_JUDGMENT
    elif reason == "human_gate_changed":
        instance.put_player("h1", {"character_name": "Human", "character_sheet": {"hp": 10}})
    elif reason == "duplicate":
        assert not await instance.commit_ai_player_action("a1", "First", **args)
    before = list(instance.action_queue)

    def requirement():
        pytest.fail("Earlier rejection must short-circuit the structured-intent query")

    assert await instance.commit_ai_player_action(
        "a1", "Second", **args, requires_structured_intent=requirement,
    ) == reason
    assert instance.action_queue == before


@pytest.mark.asyncio
async def test_commit_rechecks_after_waiting_for_authority_lock():
    instance = make_instance(humans=(), ai=("a1",))
    required = False
    checks = []

    def requirement():
        assert instance._authority_lock.locked()
        assert instance._lock.locked()
        checks.append(required)
        return required

    async with instance.authoritative_write() as entered:
        assert entered
        task = asyncio.create_task(instance.commit_ai_player_action(
            "a1", "I watch.", **commit_arguments(instance),
            requires_structured_intent=requirement,
        ))
        await asyncio.sleep(0)
        assert not task.done()
        assert not checks
        required = True
    assert await asyncio.wait_for(task, 5) == STRUCTURED_INTENT_REQUIRED
    assert checks == [True]
    assert not instance.action_queue


@pytest.mark.asyncio
@pytest.mark.parametrize("requirement", [True, lambda: True, False, None])
async def test_direct_command_initial_guard_avoids_model_call(requirement):
    instance = make_instance(humans=(), ai=("a1",))
    llm = FakePlayerLLM()
    records = await fill_ai_player_actions(
        instance, llm_client=llm, requires_structured_intent=requirement,
    )
    blocked = requirement() if callable(requirement) else bool(requirement)
    assert records[0]["status"] == ("skipped" if blocked else "added")
    assert records[0]["reason"] == (STRUCTURED_INTENT_REQUIRED if blocked else "")
    assert len(llm.calls) == (0 if blocked else 1)
    assert len(instance.action_queue) == (0 if blocked else 1)


@pytest.mark.asyncio
async def test_process_lock_rejection_precedes_guard():
    instance = make_instance(humans=(), ai=("a1",))

    def requirement():
        pytest.fail("Process lock rejection must precede the query")

    async with instance._process_lock:
        assert await instance.commit_ai_player_action(
            "a1", "I watch.", **commit_arguments(instance),
            requires_structured_intent=requirement,
        ) == "rejected"
    assert not instance.action_queue


@pytest.mark.asyncio
async def test_direct_command_recomputes_guard_after_generation():
    instance = make_instance(humans=(), ai=("a1",))
    required = False

    def start_combat(_index):
        nonlocal required
        required = True

    llm = FakePlayerLLM(on_call=start_combat)
    records = await fill_ai_player_actions(
        instance, llm_client=llm, requires_structured_intent=lambda: required,
    )
    assert records[0]["status"] == "discarded"
    assert records[0]["reason"] == STRUCTURED_INTENT_REQUIRED
    assert len(llm.calls) == 1
    assert not instance.action_queue
