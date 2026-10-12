"""Lorebook runtime timers (sticky / cooldown / delay) as a module state slot."""

from __future__ import annotations

from typing import Any

from src.engine.module_state import ModuleStateSpec, get_module_state, register_module_state
from src.lorebook.activation import migrate_timed_state

MODULE_NAME = "lorebook_runtime"
SCHEMA_VERSION = 1


def normalize_timers(raw: Any) -> dict[str, dict[str, int]]:
    """Canonical timers; corrupt records are dropped without losing valid ones."""

    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, int]] = {}
    for entry_id, value in raw.items():
        try:
            result.update(migrate_timed_state({entry_id: value}))
        except (TypeError, ValueError, OverflowError):
            continue
    return result


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "timers": {}}


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        # Unknown schema: preserve verbatim. Access rejects it without writes.
        return raw
    raw["timers"] = normalize_timers(raw.get("timers"))
    return raw


def timers(instance: Any) -> dict[str, dict[str, int]]:
    """Live timer dict (same object; callers mutate in place)."""

    return get_module_state(instance, MODULE_NAME)["timers"]


def replace_timers(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["timers"] = normalize_timers(value)


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)
