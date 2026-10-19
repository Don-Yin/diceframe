"""Fail-closed policy for plugin tools invoked by DF Agent."""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from typing import Any


_UNAVAILABLE_MESSAGE = (
    "Plugin tool unavailable to DF Agent: only tools explicitly declaring "
    "agent_effect=read_only may be invoked by DF Agent; this tool must be used "
    "through the manual plugin workflow."
)


def require_agent_read_only_tool(
    descriptors: list[dict[str, Any]],
    plugin_id: str,
    tool_name: str,
) -> dict[str, Any]:
    """Return a detached, minimal descriptor approved for DF Agent invocation.

    Eligibility requires the validated extension declaration; names,
    descriptions and schemas never imply a safe effect. This declared extension
    contract does not sandbox a native plugin process or prove its behavior.
    """
    for descriptor in descriptors:
        if not isinstance(descriptor, Mapping):
            continue
        if descriptor.get("plugin_id") != plugin_id or descriptor.get("name") != tool_name:
            continue
        if descriptor.get("agent_effect") != "read_only":
            raise PermissionError(_UNAVAILABLE_MESSAGE)
        required = ("plugin_id", "name", "title", "description", "input_schema", "agent_effect")
        if any(key not in descriptor for key in required):
            raise PermissionError(_UNAVAILABLE_MESSAGE)
        return deepcopy({key: descriptor[key] for key in required})
    raise PermissionError(_UNAVAILABLE_MESSAGE)
