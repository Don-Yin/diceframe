"""Opaque combat storage; services and snapshot owners interpret inner schemas."""

from __future__ import annotations

from typing import Any

from src.engine.module_state import ModuleStateSpec, get_module_state, register_module_state

MODULE_NAME = "combat_extension"
SCHEMA_VERSION = 1


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "current": {}, "round_snapshots": {}}


def ensure(raw: Any) -> dict[str, Any]:
    """Repair only supported-slot containers, retaining live dict identities.

    Legacy snapshot key/record normalization belongs solely to v19 -> v20.
    Unknown outer schemas and all inner contents remain opaque here.
    """

    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    for key in ("current", "round_snapshots"):
        if not isinstance(raw.get(key), dict):
            raw[key] = {}
    return raw


def current(instance: Any) -> dict[str, Any]:
    """Return the live current payload, rejecting unsupported slot schemas."""

    return get_module_state(instance, MODULE_NAME)["current"]


def replace_current(instance: Any, value: Any) -> None:
    """Keep assigned dicts (even empty ones) by identity; repair other inputs."""

    get_module_state(instance, MODULE_NAME)["current"] = value if isinstance(value, dict) else {}


def round_snapshots(instance: Any) -> dict[str, Any]:
    """Return the live map without interpreting snapshot envelopes."""

    return get_module_state(instance, MODULE_NAME)["round_snapshots"]


def replace_round_snapshots(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["round_snapshots"] = value if isinstance(value, dict) else {}


def reset(instance: Any) -> None:
    """Match lifecycle reset: replace current, clear the existing snapshot map.

    Validate the slot first so unknown schemas cannot be partially reset.
    Preserve outer extras, sibling modules, and references to old current data.
    """

    slot = get_module_state(instance, MODULE_NAME)
    slot["current"] = {}
    slot["round_snapshots"].clear()


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)
