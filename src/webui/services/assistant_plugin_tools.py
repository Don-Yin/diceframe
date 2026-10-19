"""Dynamic, host-mediated plugin actions for DF Agent.

Only validated descriptors returned by the plugin host become actions.  The
agent receives no process, filesystem, or generic RPC capability; every call
returns to the host's existing argument validation and permission boundary.
"""
from __future__ import annotations

import hashlib
import inspect
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from src.application_actions import ApplicationAction
from src.plugin_host.runtime_protocol import validate_tool_arguments


_EFFECTS = {"read_only", "mutation", "destructive"}


@dataclass(frozen=True)
class PluginActionDependencies:
    list_tools: Callable[[], dict[str, Any]]
    invoke: Callable[[str, str, dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]
    authorize_host: Callable[[str, str, dict[str, Any], str], Awaitable[bool] | bool] | None = None


def _action_name(plugin_id: str, tool_name: str) -> str:
    digest = hashlib.sha256(f"{plugin_id}\0{tool_name}".encode("utf-8")).hexdigest()[:24]
    return f"plugin_{digest}"


def _catalog(deps: PluginActionDependencies) -> list[dict[str, Any]]:
    raw = deps.list_tools()
    if not isinstance(raw, dict) or not isinstance(raw.get("tools"), list):
        raise ValueError("Plugin tool catalog is unavailable")
    result = []
    for descriptor in raw["tools"]:
        if not isinstance(descriptor, dict):
            raise ValueError("Invalid plugin tool descriptor")
        effect = descriptor.get("agent_effect")
        required = ("plugin_id", "name", "title", "description", "input_schema", "agent_effect")
        if effect not in _EFFECTS or any(key not in descriptor for key in required):
            # The plugin protocol already rejects malformed descriptors.  Do
            # not silently downgrade a missing/unknown effect to read-only.
            continue
        if not isinstance(descriptor["plugin_id"], str) or not isinstance(descriptor["name"], str):
            continue
        if not isinstance(descriptor["input_schema"], dict) or descriptor["input_schema"].get("type") != "object":
            continue
        result.append(deepcopy(descriptor))
    return result


def plugin_tools(deps: PluginActionDependencies) -> tuple[ApplicationAction, ...]:
    actions: list[ApplicationAction] = []
    for descriptor in _catalog(deps):
        plugin_id = descriptor["plugin_id"]
        tool_name = descriptor["name"]
        action_name = _action_name(plugin_id, tool_name)
        effect = descriptor["agent_effect"]
        # Process-plugin effect declarations are not a sandbox guarantee.
        # Preserve explicit confirmation even for a declared read-only tool.
        mutation = True
        # Plugin host calls are external side effects even when the plugin
        # declares them as ordinary mutation; destructive remains destructive.
        action_effect = 'destructive' if effect == 'destructive' else 'external'

        def current(expected=deepcopy(descriptor)) -> dict[str, Any]:
            for item in _catalog(deps):
                if item.get("plugin_id") == expected["plugin_id"] and item.get("name") == expected["name"]:
                    return item
            raise ValueError("Plugin action is unavailable; refresh the capability catalog")

        def guard(args: dict, owner: str, expected=deepcopy(descriptor)) -> str:
            item = current(expected)
            if item != expected:
                raise ValueError("Plugin action descriptor changed; refresh the capability catalog")
            validate_tool_arguments(item["input_schema"], args)
            return _descriptor_digest(item)

        async def authorize(args: dict, owner: str, expected=deepcopy(descriptor)) -> bool:
            item = current(expected)
            if item != expected:
                return False
            if deps.authorize_host is None:
                return True
            result = deps.authorize_host(item["plugin_id"], item["name"], deepcopy(args), owner)
            return bool(await result if inspect.isawaitable(result) else result)

        async def handler(args: dict, owner: str, expected=deepcopy(descriptor)) -> dict[str, Any]:
            item = current(expected)
            if item != expected:
                raise ValueError("Plugin action descriptor changed; refresh the capability catalog")
            validate_tool_arguments(item["input_schema"], args)
            result = deps.invoke(item["plugin_id"], item["name"], deepcopy(args))
            result = await result if inspect.isawaitable(result) else result
            if not isinstance(result, dict):
                raise ValueError("Plugin invocation returned an invalid result")
            # The service wrapper may be transport-ok while the plugin reports
            # an application failure. Preserve that failure for AgentRuntime.
            nested = result.get("result")
            if result.get("ok") is False or (isinstance(nested, dict) and nested.get("ok") is False):
                return {"ok": False, "plugin_id": item["plugin_id"], "tool_name": item["name"],
                        "result": deepcopy(nested if isinstance(nested, dict) else result)}
            return deepcopy(result)

        def preview(args: dict, owner: str, expected=deepcopy(descriptor)) -> dict[str, Any]:
            return {"plugin_id": expected["plugin_id"], "tool_name": expected["name"],
                    "effect": expected["agent_effect"], "arguments": deepcopy(args),
                    "irreversible": expected["agent_effect"] == "destructive",
                    "undo_supported": False}

        actions.append(ApplicationAction(
            action_name,
            str(descriptor["title"] or tool_name),
            deepcopy(descriptor["input_schema"]),
            handler,
            mutation=mutation,
            guard=guard if mutation else None,
            preview=preview if mutation else None,
            domain="plugins",
            effect=action_effect,
            version=1,
            automatic=False,
            authorize=authorize,
            instructions=str(descriptor["description"] or ""),
        ))
    return tuple(actions)


def _descriptor_digest(descriptor: dict[str, Any]) -> str:
    import json
    return "sha256:" + hashlib.sha256(json.dumps(
        descriptor, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
