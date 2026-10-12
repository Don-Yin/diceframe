"""Per-run Adventure state: v2 graph progress and the free/adventure play mode.

Adventure identity is not stored here: ``GameInstance.adventure_binding`` stays
the single authority for which Adventure a game is bound to, and the
``content_binding`` slot never mirrors it.  This slot only keeps what the run
has done with that binding:

- ``progress``: active/completed nodes, objectives, milestones and history of
  an Adventure v2 graph.  It is written in the same authoritative transaction
  as world truth, so round snapshots and rollbacks carry it alongside
  ``world_state``.
- ``play_mode``: ``"free"`` or ``"adventure"`` chosen at creation.  An empty or
  unknown value is derived from the binding when a save is decoded, exactly as
  the codec did when the field lived at the top level.

Run transitions: the in-place reset clears ``progress`` together with world
truth and keeps ``play_mode``; a new run (reset/restart/seed) keeps the play
mode and re-initializes v2 progress through the Adventure runtime.
"""

from __future__ import annotations

from typing import Any

from src.engine.module_state import (
    ModuleStateError, ModuleStateSpec, get_module_state, register_module_state,
)

MODULE_NAME = "adventure_runtime"
SCHEMA_VERSION = 1
PLAY_MODES = frozenset({"free", "adventure"})


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "progress": {}, "play_mode": ""}


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    if not isinstance(raw.get("progress"), dict):
        raw["progress"] = {}
    if not isinstance(raw.get("play_mode"), str):
        raw["play_mode"] = ""
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
        raise ModuleStateError(f"unsupported adventure_runtime module schema: {slot.get('schema_version')!r}")


def derive_play_mode(value: Any, adventure_binding: Any) -> str:
    """The decode rule: keep a known mode verbatim, otherwise derive it."""
    text = str(value or "")
    if text.casefold() in PLAY_MODES:
        return text
    if isinstance(adventure_binding, dict) and adventure_binding.get("adventure_id"):
        return "adventure"
    return "free"


def progress(instance: Any) -> dict[str, Any]:
    return get_module_state(instance, MODULE_NAME)["progress"]


def replace_progress(instance: Any, value: Any) -> None:
    require_writable(instance)
    get_module_state(instance, MODULE_NAME)["progress"] = value if isinstance(value, dict) else {}


def play_mode(instance: Any) -> str:
    return get_module_state(instance, MODULE_NAME)["play_mode"]


def replace_play_mode(instance: Any, value: Any) -> None:
    require_writable(instance)
    get_module_state(instance, MODULE_NAME)["play_mode"] = value if isinstance(value, str) else ""


def normalize_decoded_play_mode(instance: Any) -> None:
    """Re-apply the decode-time derivation; unknown slot schemas stay opaque."""
    slot = getattr(instance, "modules", {}).get(MODULE_NAME)
    if not isinstance(slot, dict) or slot.get("schema_version") != SCHEMA_VERSION:
        return
    slot["play_mode"] = derive_play_mode(slot.get("play_mode"), getattr(instance, "adventure_binding", None))


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)
