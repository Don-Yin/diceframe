from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.webui.services.assistant_agent import AgentDependencies, AgentRuntime
from src.webui.services.assistant_gameplay_tools import GameplayToolDependencies, gameplay_tools
from tests.test_assistant_agent import Planner


class _Game:
    run_id = "run-1"
    state = "active_action"
    players = {"gm": {"character_name": "GM"}}

    def get_character_sheet(self, uid):
        return {"ruleset_revision": 2, "hp": 8}


async def _run(agent, session_id, planner_text="do it"):
    events = []

    async def emit(name, payload):
        events.append((name, deepcopy(payload)))

    await agent.run("gm", [{"role": "user", "content": planner_text}], "en", {}, session_id, emit)
    return events


def _runtime(tmp_path, planner, *, room_writes=None, rest_writes=None, intent_writes=None):
    game = _Game()
    room_writes = room_writes if room_writes is not None else []
    rest_writes = rest_writes if rest_writes is not None else []
    intent_writes = intent_writes if intent_writes is not None else []
    viewers = {"gm": SimpleNamespace(is_member=True, is_gm=True, uid="gm")}
    current = {"quick_actions_enabled": False, "advancement_authority": "gm"}

    async def write_room(key, viewer, values):
        room_writes.append(deepcopy(values))
        current.update(values)
        return {"ok": True}

    async def rest(key, uid, body):
        rest_writes.append(deepcopy(body))
        return {"ok": True, "rest": body["rest"]}

    async def intent(key, uid, is_gm, body):
        intent_writes.append(deepcopy(body))
        return {"ok": True}

    deps = GameplayToolDependencies(
        get_game=lambda key: game if key == "game" else None,
        viewer_for=lambda instance, owner: viewers[owner],
        room_preferences=lambda key, viewer: {'ok': True, 'preferences': dict(current)},
        set_room_preferences=write_room,
        rest=rest,
        submit_ruleset_intent=intent,
    )
    tools = gameplay_tools(deps)
    runtime = AgentRuntime(AgentDependencies(
        llm_client=lambda: planner, configuration_error=lambda language: None,
        tools=tools, storage_dir=tmp_path / "agent",
    ))
    return runtime, tools, room_writes, rest_writes, intent_writes


@pytest.mark.asyncio
async def test_routine_presentation_change_executes_once(tmp_path):
    planner = Planner({"tool": "set_room_preferences", "arguments": {
        "game_key": "game", "run_id": "run-1",
        "preferences": {"quick_actions_enabled": True}},
    }, {"tool": "respond", "answer": "done"})
    runtime, _tools, writes, _rests, _intents = _runtime(tmp_path, planner)
    grant = runtime.authorize("gm", "", "routine", {"game_key": "game"}, ["settings"], 4)
    events = await _run(runtime, grant["session_id"])
    assert writes == [{"quick_actions_enabled": True}]
    assert not any(name == "approval" for name, _ in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["routine", "task"])
async def test_policy_never_auto_executes_and_confirmation_replay_is_once(tmp_path, mode):
    planner = Planner({"tool": "set_room_policy", "arguments": {
        "game_key": "game", "run_id": "run-1",
        "preferences": {"advancement_authority": "ai_gm"}},
    })
    runtime, _tools, writes, _rests, _intents = _runtime(tmp_path, planner)
    grant = runtime.authorize("gm", "", mode, {"game_key": "game"}, ["settings"], 4)
    events = await _run(runtime, grant["session_id"])
    approval = next(value for name, value in events if name == "approval")
    assert writes == []
    assert approval["preview"]["changed_keys"] == ["advancement_authority"]
    result = await runtime.confirm("gm", grant["session_id"], approval["approval_id"], approval["plan_digest"], True)
    assert result["ok"] and len(writes) == 1
    assert await runtime.confirm("gm", grant["session_id"], approval["approval_id"], approval["plan_digest"], True) == result
    assert len(writes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['routine', 'task'])
@pytest.mark.parametrize('confirmation', [None, False])
async def test_rest_without_explicit_elapsed_confirmation_never_reaches_owner(tmp_path, mode, confirmation):
    confirmation_args = {} if confirmation is None else {'confirm_elapsed_time': confirmation}
    planner = Planner({"tool": "perform_ruleset_rest", "arguments": {
        "game_key": "game", "run_id": "run-1", "rest": "short", "expected_revision": 2,
        "hit_dice": {"d8": 1}, **confirmation_args},
    }, {"tool": "respond", "answer": "confirmation required"})
    runtime, _tools, _room, rests, _intents = _runtime(tmp_path, planner)
    grant = runtime.authorize("gm", "", mode, {"game_key": "game"}, ["ruleset"], 4)
    events = await _run(runtime, grant["session_id"])
    assert rests == []
    assert not any(name == "approval" for name, _ in events)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['routine', 'task'])
async def test_confirmed_rest_is_external_with_preview_and_replay_once(tmp_path, mode):
    planner = Planner({"tool": "perform_ruleset_rest", "arguments": {
        "game_key": "game", "run_id": "run-1", "rest": "short", "expected_revision": 2,
        "confirm_elapsed_time": True, "hit_dice": {"d8": 1}},
    })
    runtime, _tools, _room, rests, _intents = _runtime(tmp_path, planner)
    grant = runtime.authorize("gm", "", mode, {"game_key": "game"}, ["ruleset"], 4)
    events = await _run(runtime, grant["session_id"])
    approval = next(value for name, value in events if name == "approval")
    assert rests == []
    preview = approval["preview"]
    assert preview["rest_type"] == "short"
    assert preview["target_character"] == {"uid": "gm", "name": "GM"}
    assert preview["confirm_elapsed_time"] is True
    assert preview["hit_dice"] == {"d8": 1}
    result = await runtime.confirm("gm", grant["session_id"], approval["approval_id"], approval["plan_digest"], True)
    assert result["ok"] and len(rests) == 1
    assert await runtime.confirm("gm", grant["session_id"], approval["approval_id"], approval["plan_digest"], True) == result
    assert len(rests) == 1


@pytest.mark.asyncio
async def test_generic_ruleset_intent_is_manual_external_even_for_task(tmp_path):
    planner = Planner({"tool": "submit_ruleset_intent", "arguments": {
        "game_key": "game", "run_id": "run-1", "intent": {"type": "automation.set", "mode": "manual"}},
    })
    runtime, tools, _room, _rests, intents = _runtime(tmp_path, planner)
    tool = next(item for item in tools if item.name == "submit_ruleset_intent")
    assert tool.version == 2 and tool.effect == "external" and not tool.automatic
    grant = runtime.authorize("gm", "", "task", {"game_key": "game"}, ["games"], 4)
    events = await _run(runtime, grant["session_id"])
    approval = next(value for name, value in events if name == "approval")
    assert intents == []
    result = await runtime.confirm("gm", grant["session_id"], approval["approval_id"], approval["plan_digest"], True)
    assert result["ok"] and len(intents) == 1
    assert await runtime.confirm("gm", grant["session_id"], approval["approval_id"], approval["plan_digest"], True) == result
    assert len(intents) == 1
