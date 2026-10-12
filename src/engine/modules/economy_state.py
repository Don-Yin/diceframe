"""Economy ledger storage; settlement mechanics remain in engine.economy."""

from __future__ import annotations

from typing import Any

from src.engine.module_state import ModuleStateSpec, get_module_state, register_module_state

MODULE_NAME = "economy"
SCHEMA_VERSION = 1


def fresh_economy_state(run_id: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "run_id": run_id,
        "next_sequence": 1,
        "proposals": [],
        "transactions": [],
        "idempotency_records": {},
        "effect_groups": [],
        "external_effects_outbox": [],
        "outcomes": [],
    }


def ensure_economy_state(raw: Any, run_id: str | None = None) -> dict[str, Any]:
    """Apply the aggregate's existing setdefault repair without rewriting data.

    Registration has no run identity, so defer that one default until instance
    initialization. Explicit stored identities (including empty/None) survive.
    The inner ledger schema is preserved independently of the slot schema.
    """

    result = raw if isinstance(raw, dict) and raw else {}
    defaults = fresh_economy_state(run_id if run_id is not None else "")
    if run_id is None:
        defaults.pop("run_id")
    for key, value in defaults.items():
        result.setdefault(key, value)
    return result


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "state": fresh_economy_state("")}


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {"schema_version": SCHEMA_VERSION}
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    raw["state"] = ensure_economy_state(raw.get("state"))
    return raw


def ensure_run_id(instance: Any) -> None:
    """Finish initialization while keeping unknown slots round-trippable."""

    slot = instance.modules[MODULE_NAME]
    if slot.get("schema_version") == SCHEMA_VERSION:
        slot["state"] = ensure_economy_state(slot.get("state"), instance.run_id)


def state(instance: Any) -> dict[str, Any]:
    """Return the live ledger, rejecting unsupported module schemas."""

    return get_module_state(instance, MODULE_NAME)["state"]


def replace_state(instance: Any, value: Any) -> None:
    """Replace exactly, as field assignment did for run reset and rollback.

    Normalization belongs to initialization, never snapshot restoration.
    """

    get_module_state(instance, MODULE_NAME)["state"] = value


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)
