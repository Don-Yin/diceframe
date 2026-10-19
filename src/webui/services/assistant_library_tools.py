"""Small, owner-scoped library capabilities for DF Agent.

Every callback is an existing service/API operation.  This module does not
open files, databases, or network connections and does not expose delete or
purge operations.
"""
from __future__ import annotations

import inspect
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from src.application_actions import ApplicationAction
from src.webui.services.assistant_agent import AgentTool


@dataclass(frozen=True)
class LibraryToolCallbacks:
    list_worlds: Callable[[], Any] | None = None
    clone_world: Callable[[str, str], Any] | None = None
    list_lorebooks: Callable[[], Any] | None = None
    read_lorebook: Callable[[str], Any] | None = None
    list_lorebook_bindings: Callable[[str], Any] | None = None
    create_lorebook: Callable[[dict[str, Any]], Any] | None = None
    update_lorebook: Callable[[str, dict[str, Any]], Any] | None = None
    export_lorebook: Callable[[str], Any] | None = None
    preview_lorebook_import: Callable[[dict[str, Any]], Any] | None = None
    commit_lorebook_plan: Callable[[dict[str, Any]], Any] | None = None
    list_adventures: Callable[[], Any] | None = None
    copy_adventure: Callable[[str, dict[str, Any]], Any] | None = None
    adventure_detail: Callable[[str], Any] | None = None
    guard: Callable[[str, dict[str, Any]], Any] | None = None
    authorize: Callable[[str, dict[str, Any], str], Any] | None = None


async def _call(callback: Callable, *args: Any) -> Any:
    result = callback(*args)
    return await result if inspect.isawaitable(result) else result


def _authorize(callbacks: LibraryToolCallbacks, operation: str, args: dict[str, Any], owner: str) -> None:
    if callbacks.authorize is None:
        return
    result = callbacks.authorize(operation, args, owner)
    if inspect.isawaitable(result):
        raise TypeError("library authorize callback must be synchronous")
    if result is False:
        raise PermissionError("Library operation is not authorized")


def _require_ok(result: Any) -> Any:
    if isinstance(result, Mapping) and result.get("ok") is False:
        raise ValueError(str(result.get("error") or "Library operation failed"))
    return result


def _snapshot_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _guard(callbacks: LibraryToolCallbacks, operation: str, args: dict[str, Any], owner: str) -> str | None:
    del owner
    if callbacks.guard is None:
        return None
    value = callbacks.guard(operation, args)
    if inspect.isawaitable(value):
        raise TypeError("library guard callback must be synchronous")
    return str(value or "")


def _book_guard(callbacks: LibraryToolCallbacks, args: dict[str, Any], owner: str) -> str | None:
    guarded = _guard(callbacks, "lorebook.update", args, owner)
    if guarded is not None:
        return guarded
    if callbacks.read_lorebook is None:
        return None
    value = callbacks.read_lorebook(str(args["book_id"]))
    if inspect.isawaitable(value):
        raise TypeError("read_lorebook guard callback must be synchronous")
    return _snapshot_digest(value)


def _obj(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def build_library_tools(callbacks: LibraryToolCallbacks) -> tuple[AgentTool, ...]:
    tools: list[AgentTool] = []
    empty = _obj({})

    if callbacks.list_worlds is not None:
        async def list_worlds(args, owner):
            del args, owner
            return {"ok": True, "worlds": await _call(callbacks.list_worlds)}
        tools.append(AgentTool("list_worlds", "List available world templates", empty, list_worlds))
    if callbacks.clone_world is not None:
        async def clone_world(args, owner):
            _authorize(callbacks, "worlds.clone", args, owner)
            return _require_ok(await _call(callbacks.clone_world, args["template_id"], args.get("name", "")))
        schema = _obj({"template_id": {"type": "string", "minLength": 1, "maxLength": 160},
                       "name": {"type": "string", "maxLength": 160}}, ("template_id",))
        tools.append(AgentTool("clone_world_from_template", "Clone an existing world template", schema, clone_world, mutation=True,
                               guard=(lambda args, owner: _guard(callbacks, "worlds.clone", args, owner)) if callbacks.guard else None))

    if callbacks.list_lorebooks is not None:
        async def list_books(args, owner):
            del args, owner
            return {"ok": True, "books": await _call(callbacks.list_lorebooks)}
        tools.append(AgentTool("list_lorebooks", "List lorebook metadata and bindings", empty, list_books))
    if callbacks.list_lorebook_bindings is not None:
        async def list_bindings(args, owner):
            del owner
            return _require_ok(await _call(callbacks.list_lorebook_bindings, args["book_id"]))
        schema = _obj({"book_id": {"type": "string", "minLength": 1, "maxLength": 160}}, ("book_id",))
        tools.append(AgentTool("list_lorebook_bindings", "Read bindings for an existing lorebook", schema, list_bindings))
    if callbacks.create_lorebook is not None:
        async def create_book(args, owner):
            _authorize(callbacks, "lorebook.create", args, owner)
            return _require_ok(await _call(callbacks.create_lorebook, dict(args)))
        schema = _obj({"id": {"type": "string", "minLength": 1, "maxLength": 160},
                       "name": {"type": "string", "minLength": 1, "maxLength": 240}}, ("id", "name"))
        tools.append(AgentTool("create_lorebook", "Create an empty lorebook metadata record", schema, create_book, mutation=True,
                               guard=(lambda args, owner: _guard(callbacks, "lorebook.create", args, owner)) if callbacks.guard else None))
    if callbacks.update_lorebook is not None:
        async def update_book(args, owner):
            _authorize(callbacks, "lorebook.update", args, owner)
            changes = dict(args["changes"])
            return _require_ok(await _call(callbacks.update_lorebook, args["book_id"], changes))
        changes = {key: {"type": "string", "maxLength": 12000} for key in ("name", "description", "language")}
        changes.update({"enabled": {"type": "boolean"}, "recursive_scanning": {"type": "boolean"},
                        "scan_depth": {"type": "integer", "minimum": 0, "maximum": 32},
                        "token_budget": {"type": "integer", "minimum": 0, "maximum": 100000},
                        "settings_json": {"type": "object", "additionalProperties": True}})
        schema = _obj({"book_id": {"type": "string", "minLength": 1, "maxLength": 160},
                       "changes": _obj(changes)}, ("book_id", "changes"))
        tools.append(AgentTool("update_lorebook_metadata", "Update validated lorebook metadata", schema, update_book, mutation=True,
                               guard=(lambda args, owner: _book_guard(callbacks, args, owner)) if (callbacks.guard or callbacks.read_lorebook) else None))
    if callbacks.export_lorebook is not None:
        async def export_book(args, owner):
            del owner
            return _require_ok(await _call(callbacks.export_lorebook, args["book_id"]))
        schema = _obj({"book_id": {"type": "string", "minLength": 1, "maxLength": 160}}, ("book_id",))
        tools.append(AgentTool("export_lorebook", "Export canonical lorebook data", schema, export_book))
    if callbacks.preview_lorebook_import is not None:
        async def preview_import(args, owner):
            del owner
            return _require_ok(await _call(callbacks.preview_lorebook_import, args["payload"]))
        schema = _obj({"payload": {"type": "object", "additionalProperties": True}}, ("payload",))
        tools.append(AgentTool("preview_lorebook_import", "Preview a native lorebook import", schema, preview_import))
    if callbacks.commit_lorebook_plan is not None:
        async def commit_import(args, owner):
            _authorize(callbacks, "lorebook.import", args, owner)
            body = {"payload": args["payload"], "plan_digest": args["plan_digest"],
                    "decision": args["decision"]}
            if "binding" in args:
                body["binding"] = args["binding"]
            return _require_ok(await _call(callbacks.commit_lorebook_plan, body))
        schema = _obj({"payload": {"type": "object", "additionalProperties": True},
                       "plan_digest": {"type": "string", "minLength": 1, "maxLength": 100},
                       "decision": {"type": "string", "enum": ["create", "update", "duplicate", "skip"]},
                       "binding": {"type": "object", "additionalProperties": True}},
                      ("payload", "plan_digest", "decision"))
        def import_guard(args, owner):
            del owner
            if callbacks.preview_lorebook_import is None:
                return None
            preview = _require_ok(callbacks.preview_lorebook_import(args["payload"]))
            digest = (preview.get('plan') or {}).get('plan_digest') if isinstance(preview, Mapping) else None
            if not digest:
                raise ValueError("Import preview did not produce a server plan digest")
            if digest != args['plan_digest']:
                raise ValueError('Import plan is stale; preview it again')
            return str(digest)
        tools.append(AgentTool("commit_lorebook_import", "Commit only a server-previewed lorebook plan", schema, commit_import, mutation=True,
                               guard=import_guard if callbacks.preview_lorebook_import else None))

    if callbacks.list_adventures is not None:
        async def list_adventures(args, owner):
            del args, owner
            return {"ok": True, "adventures": await _call(callbacks.list_adventures)}
        tools.append(AgentTool("list_adventures", "List installed adventures", empty, list_adventures))
    if callbacks.copy_adventure is not None:
        async def copy_adventure(args, owner):
            _authorize(callbacks, "adventures.copy", args, owner)
            changes = dict(args["copy"])
            return _require_ok(await _call(callbacks.copy_adventure, args["adventure_id"], changes))
        schema = _obj({"adventure_id": {"type": "string", "minLength": 1, "maxLength": 200},
                       "copy": _obj({"directory_id": {"type": "string", "minLength": 1, "maxLength": 96},
                                      "adventure_id": {"type": "string", "maxLength": 200},
                                      "name": {"type": "string", "maxLength": 240},
                                      "summary": {"type": "string", "maxLength": 4000},
                                      "version": {"type": "string", "maxLength": 32}})},
                      ("adventure_id", "copy"))
        tools.append(AgentTool("copy_adventure", "Copy an existing adventure through owner validation", schema, copy_adventure, mutation=True,
                               guard=(lambda args, owner: _guard(callbacks, "adventures.copy", args, owner)) if callbacks.guard else None))
    if callbacks.adventure_detail is not None:
        async def adventure_detail(args, owner):
            del owner
            return _require_ok(await _call(callbacks.adventure_detail, args["adventure_id"]))
        schema = _obj({"adventure_id": {"type": "string", "minLength": 1, "maxLength": 200}}, ("adventure_id",))
        tools.append(AgentTool("read_adventure_detail", "Read validated adventure metadata and graph preview", schema, adventure_detail))
    return tuple(tools)


def build_library_actions(callbacks: LibraryToolCallbacks) -> tuple[ApplicationAction, ...]:
    actions = []
    for tool in build_library_tools(callbacks):
        domain = ("worlds" if "world" in tool.name else
                  "adventures" if "adventure" in tool.name else "lorebook")
        if tool.name == "commit_lorebook_import":
            effect = "disclosure"
        elif tool.mutation:
            effect = "write" if tool.guard is not None else "external"
        else:
            effect = "read"
        actions.append(ApplicationAction(tool.name, tool.label, tool.schema, tool.handler,
                                         mutation=tool.mutation, domain=domain, effect=effect,
                                         guard=tool.guard, preview=tool.preview,
                                         authorize=(lambda args, owner, name=tool.name: _authorize(callbacks, name, args, owner)) if tool.mutation else None))
    return tuple(actions)


__all__ = ["LibraryToolCallbacks", "build_library_tools", "build_library_actions"]
