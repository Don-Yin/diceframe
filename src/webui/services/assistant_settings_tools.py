"""Bounded settings and plugin administration tools for DF Agent.

This module is deliberately an adapter: configuration ownership remains with
``prepare_config_update``/the composition root and plugin ownership remains
with ``PluginHost``.  Callers inject those public operations explicitly.
"""
from __future__ import annotations

import inspect
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.ai_providers import PROVIDER_REF_KEYS, UNSUPPORTED_AI_CONFIG_KEYS
from src.assistant_agent_limits import MIN_TASK_MAX_TOKENS, MAX_TASK_MAX_TOKENS
from src.application_actions import ApplicationAction
from src.webui.config_update import CONFIG_KEYS, prepare_config_update
from src.webui.services.assistant_agent import AgentTool


_SECRET_RE = re.compile(r"password|api.?key|token|credential|authorization|secret", re.I)
_SAFE_SETTINGS = frozenset({
    "game_defaults", "llm_generation_options", "context_recent_rounds",
    "check_model_enabled", "check_model", "model", "embedding_enabled",
    "embedding_model", "embedding_max_input", "fallback1_enabled", "fallback1_model",
    "fallback2_enabled", "fallback2_model", "narrative_max_tokens",
    "character_gen_max_tokens", "summary_max_tokens", "brief_max_tokens",
    "analysis_max_tokens", "text_gen_max_tokens", "assistant_agent_max_tokens",
    "assistant_agent_task_max_tokens",
    "model_request_timeout_seconds", "ai_providers", *PROVIDER_REF_KEYS,
})
# The list is intersected with the owner schema rather than being an alternate
# schema.  This makes a removed ConfigStore key disappear from the tool too.
SETTINGS_FIELDS = tuple(sorted(_SAFE_SETTINGS & set(CONFIG_KEYS)))
_BUDGET_FIELDS = frozenset({
    "narrative_max_tokens", "character_gen_max_tokens", "summary_max_tokens",
    "brief_max_tokens", "analysis_max_tokens", "text_gen_max_tokens",
    "assistant_agent_max_tokens",
    "assistant_agent_task_max_tokens",
})


@dataclass(frozen=True)
class SettingsToolCallbacks:
    """Explicit composition-root callbacks used by this capability pack.

    ``apply_config`` should call the same runtime application path used by the
    settings UI.  If omitted, the adapter performs pure validation and calls
    ``write_config`` with the prepared state, which is useful for small hosts
    and tests.
    """

    read_config: Callable[[], Mapping[str, Any]]
    write_config: Callable[[dict[str, Any]], Any] | None = None
    apply_config: Callable[[dict[str, Any]], Any] | None = None
    apply_config_guarded: Callable[[dict[str, Any], str], Any] | None = None
    list_plugins: Callable[[], Any] | None = None
    plugin_detail: Callable[[str], Any] | None = None
    activate_plugin: Callable[[str], Any] | None = None
    authorize: Callable[[str, dict[str, Any], str], Any] | None = None


def _safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_RE.search(key_text) and key_text not in _BUDGET_FIELDS:
                continue
            result[key_text] = _safe(item)
        return result
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_safe(item) for item in value]
    if isinstance(value, str) and ("://" in value or "@" in value):
        try:
            parsed = urlsplit(value)
            authority = parsed.netloc
            if parsed.hostname and parsed.username is not None:
                host = parsed.hostname
                if ":" in host and not host.startswith("["):
                    host = f"[{host}]"
                port = f":{parsed.port}" if parsed.port else ""
                authority = f"***:***@{host}{port}"
            query = urlencode([(key, "***" if _SECRET_RE.search(key) else item)
                               for key, item in parse_qsl(parsed.query, keep_blank_values=True)])
            fragment = "***" if parsed.fragment and _SECRET_RE.search(parsed.fragment) else parsed.fragment
            value = urlunsplit((parsed.scheme, authority, parsed.path, query, fragment))
        except ValueError:
            value = re.sub(r"(?<=://)[^/@]+@", "***@", value)
    return value


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def config_digest(value: Mapping[str, Any]) -> str:
    return _digest(dict(value))


def _public_config(config: Mapping[str, Any]) -> dict[str, Any]:
    result = {key: _safe(config[key]) for key in SETTINGS_FIELDS if key in config}
    providers = []
    for raw in config.get("ai_providers") or []:
        if not isinstance(raw, Mapping):
            continue
        providers.append({key: _safe(raw[key]) for key in
                          ("id", "name", "base_url", "api_format", "models", "model_capabilities")
                          if key in raw})
    if "ai_providers" in config:
        result["ai_providers"] = providers
    return result


def _authorize(callbacks: SettingsToolCallbacks, operation: str, args: dict[str, Any], owner: str) -> None:
    if callbacks.authorize is None:
        return
    verdict = callbacks.authorize(operation, args, owner)
    if inspect.isawaitable(verdict):
        raise TypeError("settings authorize callback must be synchronous")
    if verdict is False:
        raise PermissionError("Settings operation is not authorized")


def _validate_changes(changes: Any) -> dict[str, Any]:
    if not isinstance(changes, dict) or not changes:
        raise ValueError("changes must be a non-empty object")
    legacy = set(changes) & UNSUPPORTED_AI_CONFIG_KEYS
    if legacy:
        raise ValueError("unsupported AI config fields: " + ", ".join(sorted(legacy)) + "; use ai_providers and *_provider_ref")
    unknown = set(changes) - set(SETTINGS_FIELDS)
    if unknown:
        raise ValueError("unknown settings fields: " + ", ".join(sorted(unknown)))
    for key, value in changes.items():
        if key == "assistant_agent_task_max_tokens":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{key} must be an integer")
            if not MIN_TASK_MAX_TOKENS <= value <= MAX_TASK_MAX_TOKENS:
                raise ValueError(f"{key} must be between {MIN_TASK_MAX_TOKENS} and {MAX_TASK_MAX_TOKENS}")
        elif key in _BUDGET_FIELDS and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
            raise ValueError(f"{key} must be an integer greater than 0")
    return dict(changes)


def _settings_schema() -> dict[str, Any]:
    # The outer schema is strict; nested values are checked by the owner
    # validator, which is the source of truth for their actual shape.
    boolean_fields = {"check_model_enabled", "embedding_enabled", "fallback1_enabled", "fallback2_enabled"}
    object_fields = {"game_defaults", "llm_generation_options", "ai_providers"}
    integer_fields = {"context_recent_rounds", "embedding_max_input", *_BUDGET_FIELDS}
    properties: dict[str, dict[str, Any]] = {}
    for key in SETTINGS_FIELDS:
        if key in boolean_fields:
            properties[key] = {"type": "boolean"}
        elif key in object_fields:
            properties[key] = {"type": "array", "items": {"type": "object", "additionalProperties": True}} if key == "ai_providers" else {"type": "object", "additionalProperties": True}
        elif key == "model_request_timeout_seconds":
            properties[key] = {"type": "number", "minimum": 10, "maximum": 600}
        elif key in integer_fields:
            properties[key] = {"type": "integer", "minimum": 0 if key == "context_recent_rounds" else 1}
        else:
            properties[key] = {"type": "string", "maxLength": 12000}
    return {"type": "object", "properties": {
        "changes": {"type": "object", "properties": properties,
                    "minProperties": 1, "additionalProperties": False}},
        "required": ["changes"], "additionalProperties": False}


def build_settings_tools(callbacks: SettingsToolCallbacks) -> tuple[AgentTool, ...]:
    """Return AgentTool contracts; no WebAPI or private host lookup occurs."""
    async def read(args: dict[str, Any], owner: str) -> dict[str, Any]:
        del args, owner
        current = callbacks.read_config()
        return {"ok": True, "settings": _public_config(current), "config_digest": config_digest(current)}

    async def patch(args: dict[str, Any], owner: str) -> dict[str, Any]:
        changes = _validate_changes(args.get("changes"))
        _authorize(callbacks, "settings.patch", args, owner)
        current = dict(callbacks.read_config())
        expected = args.get("expected_config_digest", "")
        if expected and expected != _digest(current):
            raise ValueError("Settings changed; re-read settings and plan again")
        prepared = prepare_config_update(current, changes)
        if prepared.error:
            raise ValueError(prepared.error)
        if callbacks.apply_config_guarded is not None:
            result = callbacks.apply_config_guarded(changes, config_digest(current))
            if inspect.isawaitable(result):
                result = await result
        elif callbacks.apply_config is not None:
            result = callbacks.apply_config(changes)
            if inspect.isawaitable(result):
                result = await result
        elif callbacks.write_config is not None:
            result = callbacks.write_config(dict(prepared.state))
            if inspect.isawaitable(result):
                result = await result
        else:
            raise RuntimeError("settings write callback unavailable")
        if isinstance(result, Mapping) and result.get("ok") is False:
            raise ValueError(str(result.get("error") or "配置更新失败"))
        return {"ok": True, "changed": sorted(prepared.changed_keys), "settings": _public_config(prepared.state),
                "result": _safe(result) if result is not None else None}

    def settings_guard(args: dict[str, Any], owner: str) -> str:
        _authorize(callbacks, "settings.patch", args, owner)
        return _digest(callbacks.read_config())

    def settings_preview(args: dict[str, Any], owner: str) -> dict[str, Any]:
        del owner
        changes = _validate_changes(args.get("changes"))
        prepared = prepare_config_update(dict(callbacks.read_config()), changes)
        if prepared.error:
            raise ValueError(prepared.error)
        return {"ok": True, "changed": sorted(prepared.changed_keys),
                "values": _public_config({key: prepared.state[key] for key in prepared.changed_keys if key in prepared.state})}

    async def plugins(args: dict[str, Any], owner: str) -> dict[str, Any]:
        del args, owner
        if callbacks.list_plugins is None:
            raise RuntimeError("plugin listing unavailable")
        value = callbacks.list_plugins()
        value = await value if inspect.isawaitable(value) else value
        return {"ok": True, "plugins": _safe(value)}

    async def plugin_settings(args: dict[str, Any], owner: str) -> dict[str, Any]:
        del owner
        if callbacks.plugin_detail is None:
            raise RuntimeError("plugin settings unavailable")
        plugin_id = args["plugin_id"]
        value = callbacks.plugin_detail(plugin_id)
        value = await value if inspect.isawaitable(value) else value
        return {"ok": True, "plugin": _safe(value)}

    async def activate(args: dict[str, Any], owner: str) -> dict[str, Any]:
        if callbacks.activate_plugin is None:
            raise RuntimeError("plugin activation unavailable")
        _authorize(callbacks, "plugins.activate", args, owner)
        value = callbacks.activate_plugin(args["plugin_id"])
        value = await value if inspect.isawaitable(value) else value
        return {"ok": True, "plugin": _safe(value)}

    plugin_id = {"type": "string", "minLength": 1, "maxLength": 96, "pattern": r"[a-z0-9]+(?:-[a-z0-9]+)*"}
    plugin_read_schema = {"type": "object", "properties": {"plugin_id": plugin_id},
                          "required": ["plugin_id"], "additionalProperties": False}
    tools = [
        AgentTool("read_settings", "Read non-secret application settings and provider catalogue", {"type": "object", "properties": {}, "additionalProperties": False}, read),
        AgentTool("patch_settings", "Patch validated application settings", {"type": "object", "properties": {
            "changes": _settings_schema()["properties"]["changes"],
            "expected_config_digest": {"type": "string", "minLength": 0, "maxLength": 80}},
            "required": ["changes"], "additionalProperties": False}, patch, mutation=True,
            guard=settings_guard, preview=settings_preview),
    ]
    if callbacks.list_plugins is not None:
        tools.append(AgentTool("list_plugins", "List installed plugins", {"type": "object", "properties": {}, "additionalProperties": False}, plugins))
    if callbacks.plugin_detail is not None:
        tools.append(AgentTool("read_plugin_settings", "Read an installed plugin's public settings", plugin_read_schema, plugin_settings))
    if callbacks.activate_plugin is not None:
        tools.append(AgentTool("activate_plugin", "Activate an existing installed plugin", plugin_read_schema, activate, mutation=True))
    return tuple(tools)


def build_settings_actions(callbacks: SettingsToolCallbacks) -> tuple[ApplicationAction, ...]:
    """Return metadata-rich ApplicationAction contracts for the root registry."""
    tools = {tool.name: tool for tool in build_settings_tools(callbacks)}
    return tuple(ApplicationAction(tool.name, tool.label, tool.schema, tool.handler,
                                    mutation=tool.mutation, domain="settings" if "plugin" not in tool.name else "plugins",
                                    # Metadata is static while patch fields are dynamic; classify
                                    # the settings patch conservatively because it can change AI
                                    # providers and agent budgets.
                                    effect=("external" if tool.name in {"activate_plugin", "patch_settings"}
                                            else ("write" if tool.mutation else "read")),
                                    guard=tool.guard, preview=tool.preview,
                                    authorize=(lambda args, owner, name=tool.name: _authorize(callbacks, name, args, owner)) if tool.mutation else None)
                 for tool in tools.values())


__all__ = ["SETTINGS_FIELDS", "SettingsToolCallbacks", "build_settings_tools", "build_settings_actions", "config_digest"]
