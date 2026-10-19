from __future__ import annotations

import io
import json

import pytest

from src.plugin_sdk import ToolRuntime


def test_tool_runtime_initializes_and_dispatches_calls():
    requests = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocol_version": 1}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tool.call", "params": {
            "name": "sum", "arguments": {"a": 2, "b": 3}, "context": {"game_key": "demo"},
        }}),
    ]) + "\n"
    output = io.StringIO()
    runtime = ToolRuntime(stdin=io.StringIO(requests), stdout=output)

    @runtime.tool(
        name="sum",
        title="Sum",
        description="Adds two numbers.",
        input_schema={"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}},
    )
    def add(arguments, context):
        return {"value": arguments["a"] + arguments["b"], "game_key": context["game_key"]}

    runtime.run()
    responses = [json.loads(line) for line in output.getvalue().splitlines()]

    assert responses[0]["result"]["tools"][0]["name"] == "sum"
    assert responses[1]["result"] == {"value": 5, "game_key": "demo"}


@pytest.mark.parametrize("effect", ["read_only", "mutation", "destructive"])
def test_tool_runtime_initializes_with_declared_agent_effect(effect):
    runtime = ToolRuntime(stdin=io.StringIO(), stdout=io.StringIO())

    @runtime.tool(name="inspect", title="Inspect", description="", agent_effect=effect)
    def inspect(arguments, context):
        return {}

    result = runtime._dispatch("initialize", {"protocol_version": 1})
    assert result["tools"][0]["agent_effect"] == effect


@pytest.mark.parametrize("effect", ["unknown", "READ_ONLY", 1, [], {}])
def test_tool_runtime_rejects_invalid_agent_effect(effect):
    runtime = ToolRuntime(stdin=io.StringIO(), stdout=io.StringIO())
    with pytest.raises(ValueError, match="agent_effect"):
        runtime.tool(name="bad", title="Bad", description="", agent_effect=effect)


def test_tool_runtime_omits_agent_effect_for_legacy_registration():
    runtime = ToolRuntime(stdin=io.StringIO(), stdout=io.StringIO())

    @runtime.tool(name="legacy", title="Legacy", description="")
    def legacy(arguments, context):
        return {}

    descriptor = runtime._dispatch("initialize", {"protocol_version": 1})["tools"][0]
    assert "agent_effect" not in descriptor
