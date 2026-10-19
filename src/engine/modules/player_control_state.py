"""Room-level player-control settings as a module state slot."""

from __future__ import annotations

from typing import Any

from src.engine import module_hooks
from src.engine.module_state import ModuleStateSpec, get_module_state, register_module_state
from src.engine.player_control import DEFAULT_AWAY_CONTROL_POLICY, normalize_away_control_policy

MODULE_NAME = "player_control"
SCHEMA_VERSION = 1


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "away_control_policy": DEFAULT_AWAY_CONTROL_POLICY}


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    raw["away_control_policy"] = normalize_away_control_policy(raw.get("away_control_policy"))
    return raw


def away_control_policy(instance: Any) -> str:
    return str(get_module_state(instance, MODULE_NAME)["away_control_policy"])


def set_away_control_policy_value(instance: Any, policy: str) -> None:
    get_module_state(instance, MODULE_NAME)["away_control_policy"] = policy


def record_state(instance: Any, kind: str, value: Any) -> None:
    if kind == module_hooks.AWAY_CONTROL_POLICY:
        set_away_control_policy_value(instance, normalize_away_control_policy(value))


def read_state(instance: Any, kind: str) -> Any:
    return away_control_policy(instance) if kind == module_hooks.AWAY_CONTROL_POLICY else None


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)
module_hooks.register(module_hooks.STATE_RECORD, MODULE_NAME, record_state)
module_hooks.register(module_hooks.STATE_READ, MODULE_NAME, read_state)
