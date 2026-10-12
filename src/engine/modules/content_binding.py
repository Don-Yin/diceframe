"""Canonical content references bound to one game run.

The binding slot is deliberately opaque to the generic game aggregate: World
and Book remain content-layer identities while the game only keeps the
source-aware refs selected for this run.  The Lorebook database remains the
authority for the actual Book binding rows, and ``GameInstance.adventure_binding``
is the single authority for Adventure identity (this slot never mirrors it).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.content_modules.refs import ContentRefError, parse_content_ref
from src.engine.module_state import (
    ModuleStateError, ModuleStateSpec, get_module_state, register_module_state,
)

MODULE_NAME = "content_binding"
SCHEMA_VERSION = 1


def fresh() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "world_ref": {},
        "book_refs": [],
    }


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    raw.setdefault("world_ref", {})
    raw.setdefault("book_refs", [])
    # Adventure identity lives in GameInstance.adventure_binding; drop the
    # duplicate key that unreleased builds of this slot wrote.
    raw.pop("adventure_refs", None)
    return raw


def require_writable(instance: Any) -> None:
    """Read-only transaction preflight; never repair or materialize a slot."""
    modules = getattr(instance, "modules", None)
    if not isinstance(modules, dict):
        raise ModuleStateError("instance has no module state container")
    slot = modules.get(MODULE_NAME)
    if not isinstance(slot, dict):
        return  # Missing/corrupt slots have the documented fresh default.
    if slot.get("schema_version") != SCHEMA_VERSION:
        raise ModuleStateError(f"unsupported content_binding module schema: {slot.get('schema_version')!r}")


def _state(instance: Any) -> dict[str, Any]:
    return get_module_state(instance, MODULE_NAME)


def world_ref(instance: Any) -> dict[str, Any]:
    return deepcopy(_state(instance).get("world_ref") or {})


def set_world_ref(instance: Any, ref: dict[str, Any]) -> None:
    require_writable(instance)
    parsed = parse_content_ref(ref, default_source="world:unknown")
    if parsed.kind != "world":
        raise ContentRefError("content binding world_ref must have kind 'world'")
    _state(instance)["world_ref"] = parsed.to_portable_dict()


def book_refs(instance: Any) -> list[dict[str, Any]]:
    return deepcopy(list(_state(instance).get("book_refs") or []))


def add_book_ref(instance: Any, ref: dict[str, Any]) -> None:
    require_writable(instance)
    parsed = parse_content_ref(ref, default_source="world:unknown")
    if parsed.kind != "lorebook":
        raise ContentRefError("content binding book_refs must have kind 'lorebook'")
    value = parsed.to_portable_dict()
    state = _state(instance)
    refs = state.setdefault("book_refs", [])
    if value not in refs:
        refs.append(value)


SPEC = ModuleStateSpec(
    name=MODULE_NAME,
    schema_version=SCHEMA_VERSION,
    fresh=fresh,
    ensure=ensure,
)
register_module_state(SPEC)


__all__ = [
    "MODULE_NAME",
    "SCHEMA_VERSION",
    "add_book_ref",
    "book_refs",
    "ensure",
    "fresh",
    "require_writable",
    "set_world_ref",
    "world_ref",
]
