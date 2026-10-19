"""Narrative summary, remembered facts, confirmed items, legacy game time and the scene.

``scene`` is the free-text label of where the story currently is. The narrator
(``scene_change``), the run opening and ruleset campaign steps write it; it is
a narrative label, not Adventure authority. Its value is kept verbatim, as it
was at the top level. Reset clears it together with the other notes.
"""

from __future__ import annotations

from typing import Any
from src.engine import module_hooks

from src.engine.module_state import (
    ModuleStateError, ModuleStateSpec, get_module_state, register_module_state,
)

MODULE_NAME = "narrative_notes"
SCHEMA_VERSION = 2


def fresh() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "summary": {}, "key_facts": [], "confirmed_items": [],
        "game_time": "", "scene": "",
    }


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    if not isinstance(raw.get("summary"), dict):
        raw["summary"] = {}
    for key in ("key_facts", "confirmed_items"):
        if not isinstance(raw.get(key), list):
            raw[key] = []
    if not isinstance(raw.get("game_time"), str):
        raw["game_time"] = ""
    # Only a missing scene is defaulted: the old top-level field was never
    # type-checked, so any stored value is kept verbatim.
    raw.setdefault("scene", "")
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
        raise ModuleStateError(f"unsupported narrative_notes module schema: {slot.get('schema_version')!r}")


def summary(instance: Any) -> dict:
    return get_module_state(instance, MODULE_NAME)["summary"]


def replace_summary(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["summary"] = value if isinstance(value, dict) else {}


def key_facts(instance: Any) -> list:
    return get_module_state(instance, MODULE_NAME)["key_facts"]


def replace_key_facts(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["key_facts"] = value if isinstance(value, list) else []


def confirmed_items(instance: Any) -> list:
    return get_module_state(instance, MODULE_NAME)["confirmed_items"]


def replace_confirmed_items(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["confirmed_items"] = value if isinstance(value, list) else []


def game_time(instance: Any) -> str:
    return get_module_state(instance, MODULE_NAME)["game_time"]


def replace_game_time(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["game_time"] = value if isinstance(value, str) else ""


def scene(instance: Any) -> Any:
    return get_module_state(instance, MODULE_NAME)["scene"]


def replace_scene(instance: Any, value: Any) -> None:
    require_writable(instance)
    get_module_state(instance, MODULE_NAME)["scene"] = value


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)


_KINDS = {
    module_hooks.NARRATIVE_SCENE: "scene", module_hooks.NARRATIVE_TIME: "game_time",
    module_hooks.NARRATIVE_SUMMARY: "summary", module_hooks.NARRATIVE_KEY_FACTS: "key_facts",
    module_hooks.NARRATIVE_CONFIRMED_ITEMS: "confirmed_items",
}


def _preflight(instance: Any, kind: str) -> None:
    if kind == module_hooks.NARRATIVE_VIEW or kind in _KINDS:
        require_writable(instance)


def _read(instance: Any, kind: str) -> dict | None:
    if kind == module_hooks.NARRATIVE_VIEW:
        return get_module_state(instance, MODULE_NAME)
    return None


def _record(instance: Any, kind: str, value: Any) -> None:
    field = _KINDS.get(kind)
    if field is None:
        return
    require_writable(instance)
    if field == "summary" and not isinstance(value, dict):
        value = {}
    elif field in {"key_facts", "confirmed_items"} and not isinstance(value, list):
        value = []
    elif field == "game_time" and not isinstance(value, str):
        value = ""
    get_module_state(instance, MODULE_NAME)[field] = value


def _reset(instance: Any) -> None:
    require_writable(instance)
    get_module_state(instance, MODULE_NAME).update(fresh())


module_hooks.register(module_hooks.STATE_WRITE_PREFLIGHT, MODULE_NAME, _preflight)
module_hooks.register(module_hooks.STATE_READ, MODULE_NAME, _read)
module_hooks.register(module_hooks.STATE_RECORD, MODULE_NAME, _record)
module_hooks.register(module_hooks.INSTANCE_RESET, MODULE_NAME, _reset)
