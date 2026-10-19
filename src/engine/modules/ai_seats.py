"""Persisted AI seat policy. Only references and style IDs belong in saves."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.ai_providers import is_valid_provider_id
from src.engine import module_hooks
from src.engine.module_state import ModuleStateSpec, get_module_state, register_module_state, set_module_state

MODULE_NAME = "ai_seats"
SCHEMA_VERSION = 1
STYLES = ("character", "concise", "cautious", "bold", "supportive")
FIELDS = frozenset({"provider_ref", "model", "style"})


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "revision": 0,
            "defaults_revision": 0, "seat_revisions": {},
            "defaults": {"provider_ref": None, "model": None, "style": "character"},
            "seats": {}, "outcomes": {}}


def ensure(raw: Any) -> dict[str, Any]:
    # Unknown or corrupt existing policy is never silently replaced by defaults.
    return raw if isinstance(raw, dict) else fresh()


def validate_settings(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.keys() - FIELDS:
        raise ValueError("unsupported AI seat settings fields")
    result = {key: raw.get(key) for key in FIELDS}
    for key in ("provider_ref", "model"):
        value = result[key]
        if value is not None:
            if not isinstance(value, str) or not value.strip() or len(value) > 160:
                raise ValueError(f"invalid {key}")
            result[key] = value.strip()
    if result["provider_ref"] is not None and not is_valid_provider_id(result["provider_ref"]):
        raise ValueError("invalid provider_ref")
    if result["style"] is not None and result["style"] not in STYLES:
        raise ValueError("invalid AI seat style")
    return result


def settings_state(instance: Any) -> dict[str, Any]:
    slot = get_module_state(instance, MODULE_NAME)
    if (type(slot.get("revision")) is not int or slot["revision"] < 0
            or not isinstance(slot.get("seats"), dict)
            or type(slot.get("defaults_revision")) is not int
            or not isinstance(slot.get("seat_revisions"), dict)
            or not isinstance(slot.get("outcomes"), dict)):
        raise ValueError("invalid AI settings state")
    validate_settings(slot.get("defaults"))
    return slot


def effective_settings(instance: Any, uid: str) -> dict[str, Any]:
    slot = settings_state(instance)
    defaults = validate_settings(slot["defaults"])
    seat = validate_settings(slot["seats"].get(uid, {}))
    effective = {key: seat[key] if seat[key] is not None else defaults[key] for key in FIELDS}
    effective["style"] = effective["style"] or "character"
    return effective


def update_settings(instance: Any, raw: Any, *, uid: str | None = None,
                    expected_revision: int) -> int:
    """Replace one policy under the caller's authority gate; nulls inherit."""
    value = validate_settings(raw)
    slot = settings_state(instance)
    if type(expected_revision) is not int or expected_revision != slot["revision"]:
        raise ValueError("AI settings revision changed")
    if uid is not None and uid not in instance.players:
        raise ValueError("unknown seat")
    if uid is None:
        slot["defaults"] = value
    elif all(item is None for item in value.values()):
        slot["seats"].pop(uid, None)
    else:
        slot["seats"][uid] = value
    slot["revision"] += 1
    if uid is None:
        slot["defaults_revision"] = slot["revision"]
    else:
        slot["seat_revisions"][uid] = slot["revision"]
    return slot["revision"]


def configuration_token(instance: Any, uid: str) -> tuple[int, int] | None:
    try:
        slot = settings_state(instance)
        revision = slot["seat_revisions"].get(uid, 0)
        if type(revision) is not int or revision < 0:
            raise ValueError("invalid seat revision")
        return slot["defaults_revision"], revision
    except ValueError:
        return None


def record_outcome(instance: Any, uid: str, outcome: dict[str, Any]) -> None:
    slot = settings_state(instance)
    # Whitelist safe metadata: never persist response text, URLs or exceptions.
    slot["outcomes"][uid] = deepcopy({key: outcome.get(key) for key in
        ("status", "reason", "run_id", "round", "control_revision", "config_revision")})
    if type(outcome.get("combat_round")) is int and outcome["combat_round"] >= 0:
        slot["outcomes"][uid]["combat_round"] = outcome["combat_round"]


def restore_settings(instance: Any, before: dict[str, Any]) -> None:
    set_module_state(instance, MODULE_NAME, deepcopy(before))


def remove_seat(instance: Any, uid: str) -> None:
    try:
        slot = settings_state(instance)
    except ValueError:
        return  # Preserve unsupported saves; their policy remains unusable.
    slot["seats"].pop(uid, None)
    slot["outcomes"].pop(uid, None)
    slot["revision"] += 1
    slot["seat_revisions"][uid] = slot["revision"]  # fence a later reuse of the UID


def reset_seats(instance: Any) -> None:
    try:
        slot = settings_state(instance)
    except ValueError:
        return
    slot["seats"].clear()
    slot["outcomes"].clear()
    slot["seat_revisions"].clear()
    slot["revision"] += 1
    slot["defaults_revision"] = slot["revision"]


register_module_state(ModuleStateSpec(MODULE_NAME, SCHEMA_VERSION, fresh, ensure))

module_hooks.register(module_hooks.SEAT_FORGOTTEN, MODULE_NAME, remove_seat)
module_hooks.register(module_hooks.INSTANCE_RESET, MODULE_NAME, reset_seats)
