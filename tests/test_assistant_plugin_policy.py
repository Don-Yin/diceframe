from __future__ import annotations

import pytest

from src.plugin_host.descriptors import validate_tool_descriptors
from src.plugin_host.runtime_protocol import PluginProtocolError
from src.webui.services.assistant_plugin_policy import require_agent_read_only_tool


def _initialized(*tools: dict[str, object]) -> dict[str, object]:
    return {"protocol_version": 1, "tools": list(tools)}


def _tool(name: str = "inspect", **extra: object) -> dict[str, object]:
    return {
        "name": name,
        "title": "Inspect",
        "description": "Inspect something",
        "input_schema": {"type": "object", "properties": {"value": {"type": "string"}}},
        **extra,
    }


def test_descriptor_preserves_known_agent_effect_and_legacy_omission() -> None:
    classified = validate_tool_descriptors(_initialized(_tool(agent_effect="read_only")))
    assert classified[0]["agent_effect"] == "read_only"
    legacy = validate_tool_descriptors(_initialized(_tool()))
    assert "agent_effect" not in legacy[0]


@pytest.mark.parametrize("effect", ["unknown", "READ_ONLY", 1, None, ["read_only"]])
def test_descriptor_rejects_unknown_or_malformed_agent_effect(effect: object) -> None:
    with pytest.raises(PluginProtocolError, match="agent_effect"):
        validate_tool_descriptors(_initialized(_tool(agent_effect=effect)))


def test_policy_returns_detached_minimal_descriptor_for_exact_read_only_match() -> None:
    descriptors = [{
        "plugin_id": "trusted-plugin",
        **_tool(agent_effect="read_only"),
        "extra": "discarded",
    }]
    result = require_agent_read_only_tool(descriptors, "trusted-plugin", "inspect")
    assert result == {
        "plugin_id": "trusted-plugin",
        "name": "inspect",
        "title": "Inspect",
        "description": "Inspect something",
        "input_schema": {"type": "object", "properties": {"value": {"type": "string"}}},
        "agent_effect": "read_only",
    }
    result["input_schema"]["properties"]["value"]["type"] = "integer"
    assert descriptors[0]["input_schema"]["properties"]["value"]["type"] == "string"


@pytest.mark.parametrize("effect", [None, "mutation", "destructive"])
def test_policy_rejects_missing_or_non_read_only_effects(effect: object) -> None:
    descriptor = {"plugin_id": "plugin", **_tool()}
    if effect is not None:
        descriptor["agent_effect"] = effect
    with pytest.raises(PermissionError, match="unavailable to DF Agent.*manual plugin workflow"):
        require_agent_read_only_tool([descriptor], "plugin", "inspect")


def test_policy_rejects_wrong_plugin_or_tool_identity() -> None:
    descriptors = [{"plugin_id": "plugin", **_tool(agent_effect="read_only")}]
    with pytest.raises(PermissionError, match="unavailable to DF Agent"):
        require_agent_read_only_tool(descriptors, "other-plugin", "inspect")
    with pytest.raises(PermissionError, match="unavailable to DF Agent"):
        require_agent_read_only_tool(descriptors, "plugin", "different")
