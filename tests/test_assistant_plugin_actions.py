from copy import deepcopy

import pytest

from src.webui.services.assistant_agent import AgentDependencies, AgentRuntime
from src.webui.services.assistant_plugin_tools import (
    PluginActionDependencies,
    _action_name,
    plugin_tools,
)
from tests.test_assistant_agent import Planner


def descriptor(*, effect="read_only", plugin_id="plug-a", name="inspect", schema=None):
    value = {"type": "object", "properties": {"value": {"type": "string"}},
             "required": ["value"], "additionalProperties": False}
    return {"plugin_id": plugin_id, "name": name, "title": name.title(),
            "description": "test plugin action", "input_schema": schema or value,
            "agent_effect": effect}


def deps(catalog, invoke, authorize=None):
    return PluginActionDependencies(
        list_tools=lambda: {"tools": deepcopy(catalog())},
        invoke=invoke,
        authorize_host=authorize,
    )


def test_factory_exposes_only_declared_effects_and_stable_hashed_names():
    catalog = [descriptor(), descriptor(effect="mutation", name="write"),
               descriptor(effect="destructive", name="remove"),
               {**descriptor(name="legacy"), "agent_effect": "unknown"},
               {key: value for key, value in descriptor(name="missing").items() if key != "agent_effect"}]
    actions = plugin_tools(deps(lambda: catalog, lambda *_: {"ok": True}))
    assert [action.name for action in actions] == [
        _action_name("plug-a", "inspect"), _action_name("plug-a", "write"), _action_name("plug-a", "remove")]
    assert actions[0].mutation is True and actions[0].effect == "external"
    assert actions[1].mutation is True and actions[1].effect == "external" and not actions[1].automatic
    assert actions[2].effect == "destructive" and not actions[2].automatic


@pytest.mark.asyncio
async def test_read_action_validates_schema_and_uses_exact_plugin_identity():
    calls = []
    catalog = [descriptor(plugin_id="exact-plugin", name="inspect")]
    async def invoke(plugin_id, tool_name, args):
        calls.append((plugin_id, tool_name, args))
        return {"ok": True, "result": {"answer": "yes"}}
    action = plugin_tools(deps(lambda: catalog, invoke))[0]
    assert await action.handler({"value": "x"}, "owner") == {"ok": True, "result": {"answer": "yes"}}
    assert calls == [("exact-plugin", "inspect", {"value": "x"})]
    with pytest.raises(Exception):
        await action.handler({"unexpected": True}, "owner")


@pytest.mark.asyncio
async def test_descriptor_change_and_disabled_plugin_disappear_and_guard_rejects():
    state = {"tools": [descriptor(effect="mutation")]}
    action = plugin_tools(deps(lambda: state["tools"], lambda *_: {"ok": True}))[0]
    args = {"value": "x"}
    original = action.guard(args, "owner")
    state["tools"][0]["description"] = "changed"
    with pytest.raises(ValueError, match="descriptor changed"):
        action.guard(args, "owner")
    state["tools"] = []
    with pytest.raises(ValueError, match="unavailable"):
        action.guard(args, "owner")
    assert original.startswith("sha256:")


@pytest.mark.asyncio
async def test_host_authorization_rechecks_descriptor_and_nested_failure_propagates():
    catalog = [descriptor(effect="mutation")]
    allowed = []
    async def authorize(plugin_id, tool_name, args, owner):
        allowed.append((plugin_id, tool_name, owner))
        return False
    action = plugin_tools(deps(lambda: catalog, lambda *_: {"ok": True}, authorize))[0]
    assert await action.authorize({"value": "x"}, "owner") is False
    assert allowed == [("plug-a", "inspect", "owner")]

    failing = plugin_tools(deps(
        lambda: [descriptor(effect="mutation")],
        lambda *_: {"ok": True, "result": {"ok": False, "error": "plugin rejected"}},
    ))[0]
    result = await failing.handler({"value": "x"}, "owner")
    assert result["ok"] is False and result["result"]["error"] == "plugin rejected"


@pytest.mark.asyncio
async def test_plugin_mutation_requires_concrete_confirmation_and_executes_once(tmp_path):
    calls = []
    async def invoke(plugin_id, tool_name, args):
        calls.append((plugin_id, tool_name, deepcopy(args)))
        return {"ok": True, "result": {"saved": True}}
    action = plugin_tools(deps(lambda: [descriptor(effect="mutation", name="write")], invoke))[0]
    planner = Planner({"tool": action.name, "arguments": {"value": "persist"}})
    agent = AgentRuntime(AgentDependencies(
        llm_client=lambda: planner, configuration_error=lambda _: None, tools=(action,), storage_dir=tmp_path,
    ))
    events = []
    async def emit(name, payload):
        events.append((name, deepcopy(payload)))
    await agent.run("owner", [{"role": "user", "content": "write"}], "en", {"route": "plugins"}, "", emit)
    approval = next(payload for name, payload in events if name == "approval")
    session_id = next(payload["session_id"] for name, payload in events if name == "session")
    assert calls == []
    result = await agent.confirm("owner", session_id, approval["approval_id"], approval["plan_digest"], True)
    assert result["ok"] and len(calls) == 1
    assert await agent.confirm("owner", session_id, approval["approval_id"], approval["plan_digest"], True) == result
    assert len(calls) == 1
