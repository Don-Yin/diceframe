"""Optional table preferences; persisted owner for narrative_perspective, gm_style_override."""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from src.engine import module_hooks
from src.engine.module_state import ModuleStateError, ModuleStateSpec, get_module_state, register_module_state

MODULE_NAME = "narration_preferences"
SCHEMA_VERSION = 1


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, **{'narrative_perspective': 'auto', 'gm_style_override': None}}


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    defaults = fresh()
    if not isinstance(raw.get('narrative_perspective'), str):
        raw['narrative_perspective'] = defaults['narrative_perspective']
    if not isinstance(raw.get("gm_style_override"), dict):
        raw["gm_style_override"] = None
    return raw


def require_writable(instance: Any) -> None:
    modules = getattr(instance, "modules", None)
    if not isinstance(modules, dict):
        raise ModuleStateError("instance has no module state container")
    slot = modules.get(MODULE_NAME)
    if isinstance(slot, dict) and slot.get("schema_version") != SCHEMA_VERSION:
        raise ModuleStateError(f"unsupported {MODULE_NAME} module schema: {slot.get('schema_version')!r}")


def narrative_perspective(instance: Any) -> str:
    return get_module_state(instance, MODULE_NAME)["narrative_perspective"]


def replace_narrative_perspective(instance: Any, value: str) -> None:
    get_module_state(instance, MODULE_NAME)["narrative_perspective"] = value


def gm_style_override(instance: Any) -> dict[str, str] | None:
    return get_module_state(instance, MODULE_NAME)["gm_style_override"]


def replace_gm_style_override(instance: Any, value: dict[str, str] | None) -> None:
    get_module_state(instance, MODULE_NAME)["gm_style_override"] = value


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)


_KINDS = {
    module_hooks.NARRATIVE_PERSPECTIVE: 'narrative_perspective',
    module_hooks.GM_STYLE_OVERRIDE: 'gm_style_override',
}


def _preflight(instance: Any, state_kind: str) -> None:
    if state_kind == module_hooks.NARRATION_PREFERENCES or state_kind in _KINDS:
        require_writable(instance)


def _read(instance: Any, state_kind: str) -> dict | None:
    return get_module_state(instance, MODULE_NAME) if state_kind == module_hooks.NARRATION_PREFERENCES else None


def _record(instance: Any, state_kind: str, value: Any) -> None:
    field = _KINDS.get(state_kind)
    if field is not None:
        require_writable(instance)
        get_module_state(instance, MODULE_NAME)[field] = value


def _carry(candidate: Any, source: Any) -> None:
    source_slot = get_module_state(source, MODULE_NAME)
    candidate_slot = get_module_state(candidate, MODULE_NAME)
    for field in _KINDS.values():
        candidate_slot[field] = deepcopy(source_slot[field])


module_hooks.register(module_hooks.STATE_WRITE_PREFLIGHT, MODULE_NAME, _preflight)
module_hooks.register(module_hooks.STATE_READ, MODULE_NAME, _read)
module_hooks.register(module_hooks.STATE_RECORD, MODULE_NAME, _record)
module_hooks.register(module_hooks.INSTANCE_NEW_RUN_PREFLIGHT, MODULE_NAME, require_writable)
module_hooks.register(module_hooks.INSTANCE_NEW_RUN, MODULE_NAME, _carry)
