"""Round check records and manual roll requests; reset preserves manual rolls."""

from __future__ import annotations

from typing import Any

from src.engine.contracts import CheckResult
from src.engine.module_state import (
    ModuleStateError, ModuleStateSpec, get_module_state, register_module_state,
)

MODULE_NAME = "checks"
SCHEMA_VERSION = 1


def fresh() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "last_check": None,
        "last_checks": [],
        "round_checks_prepared": False,
        "manual_roll_requests": [],
    }


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    if not isinstance(raw.get("last_check"), dict):
        raw["last_check"] = None
    for key in ("last_checks", "manual_roll_requests"):
        if not isinstance(raw.get(key), list):
            raw[key] = []
    raw["round_checks_prepared"] = bool(raw.get("round_checks_prepared", False))
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
        raise ModuleStateError(f"unsupported checks module schema: {slot.get('schema_version')!r}")


def last_check(instance: Any) -> CheckResult | None:
    return get_module_state(instance, MODULE_NAME)["last_check"]


def replace_last_check(instance: Any, value: CheckResult | None) -> None:
    get_module_state(instance, MODULE_NAME)["last_check"] = value


def last_checks(instance: Any) -> list[CheckResult]:
    return get_module_state(instance, MODULE_NAME)["last_checks"]


def replace_last_checks(instance: Any, value: list[CheckResult]) -> None:
    get_module_state(instance, MODULE_NAME)["last_checks"] = value


def round_checks_prepared(instance: Any) -> bool:
    return get_module_state(instance, MODULE_NAME)["round_checks_prepared"]


def replace_round_checks_prepared(instance: Any, value: bool) -> None:
    get_module_state(instance, MODULE_NAME)["round_checks_prepared"] = value


def manual_roll_requests(instance: Any) -> list[dict[str, Any]]:
    return get_module_state(instance, MODULE_NAME)["manual_roll_requests"]


def replace_manual_roll_requests(instance: Any, value: list[dict[str, Any]]) -> None:
    get_module_state(instance, MODULE_NAME)["manual_roll_requests"] = value


def record(instance: Any, check: CheckResult) -> None:
    require_writable(instance)
    slot = get_module_state(instance, MODULE_NAME)
    slot["last_checks"].append(check)
    slot["last_check"] = check


def sync_last(instance: Any, check: CheckResult) -> None:
    require_writable(instance)
    replace_last_check(instance, dict(check))


def mark_prepared(instance: Any) -> None:
    require_writable(instance)
    slot = get_module_state(instance, MODULE_NAME)
    if slot["last_checks"]:
        slot["last_check"] = slot["last_checks"][-1]
    slot["round_checks_prepared"] = True


def clear_round(instance: Any, *, prepared: bool = False) -> None:
    require_writable(instance)
    slot = get_module_state(instance, MODULE_NAME)
    slot["last_check"] = None
    slot["last_checks"].clear()
    slot["round_checks_prepared"] = prepared


def invalidate_prepared(instance: Any) -> None:
    require_writable(instance)
    replace_round_checks_prepared(instance, False)


def add_manual_roll_request(instance: Any, req: dict[str, Any]) -> None:
    require_writable(instance)
    manual_roll_requests(instance).append(req)


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)
