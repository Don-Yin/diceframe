"""Scoped check-mode requests and grants. Only GM grants affect mechanics."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.engine import module_hooks
from src.engine.module_state import ModuleStateSpec, get_module_state, register_module_state, set_module_state

NAME = "check_modes"
MODES = ("advantage", "disadvantage")


def fresh() -> dict:
    return {"schema_version": 1, "revision": 0, "seats": {}}


def state(instance: Any) -> dict:
    slot = get_module_state(instance, NAME)
    if type(slot.get("revision")) is not int or slot["revision"] < 0 or not isinstance(slot.get("seats"), dict):
        raise ValueError("invalid check mode state")
    return slot


def scoped(instance: Any, uid: str, context_id: str) -> dict:
    value = state(instance)["seats"].get(uid)
    if (not isinstance(value, dict) or value.get("run_id") != instance.run_id
            or value.get("context_id") != context_id):
        return {"request": None, "grant": None}
    for field in ("request", "grant"):
        row = value.get(field)
        if row is not None and (not isinstance(row, dict) or row.get("mode") not in MODES
                                or not isinstance(row.get("reason"), str)
                                or row.get("status") not in (("granted",) if field == "grant" else ("pending", "granted", "rejected"))):
            raise ValueError("invalid check mode entry")
    return deepcopy(value)


def change(instance: Any, uid: str, operation: str, context_id: str, *, mode: Any, reason: Any) -> None:
    slot = state(instance)
    row = scoped(instance, uid, context_id)
    if operation in ("request", "grant"):
        if mode not in MODES or not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise ValueError("mode and reason required")
        row[operation] = {"mode": mode, "reason": reason.strip(), "status": "pending" if operation == "request" else "granted"}
        if operation == "grant" and row.get("request"):
            row["request"]["status"] = "granted"
    elif operation == "clear":
        row["grant"] = None
    elif operation == "reject":
        if not row.get("request") or not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise ValueError("request and reason required")
        row["request"].update(status="rejected", decision_reason=reason.strip())
    else:
        raise ValueError("unknown check mode operation")
    row.update(run_id=instance.run_id, context_id=context_id)
    slot["seats"][uid] = row
    slot["revision"] += 1


def combine_mode(automatic: str, grant: dict | None) -> str:
    manual = grant.get("mode") if grant else ""
    modes = {mode for mode in (automatic, manual) if mode in MODES}
    return next(iter(modes)) if len(modes) == 1 else ""


def apply_grant(instance: Any, request: dict, context_id: str) -> None:
    # A delegated companion check is not a check made by its controlling PC.
    uid = str(request.get("actor_uid") or "")
    if request.get("actor_ref", f"player:{uid}") != f"player:{uid}":
        return
    grant = scoped(instance, uid, context_id).get("grant")
    if grant:
        automatic = str(request.get("advantage_mode") or "")
        modes = set(request.get("check_mode_sources") or [])
        if automatic in MODES:
            modes.add(automatic)
        modes.add(grant["mode"])
        request["advantage_mode"] = next(iter(modes)) if len(modes) == 1 else ""
        previous = str(request.get("advantage_note") or "")
        request["advantage_note"] = "; ".join(filter(None, (previous, f"GM: {grant['reason']}")))
        request["advantage_reason"] = request["advantage_note"]


def restore(instance: Any, before: dict) -> None:
    set_module_state(instance, NAME, deepcopy(before))


def remove_seat(instance: Any, uid: str) -> None:
    try:
        slot = state(instance)
    except ValueError:
        return  # Preserve future data; unsupported grants cannot be consumed.
    if uid in slot["seats"]:
        slot["seats"].pop(uid)
        slot["revision"] += 1


def reset(instance: Any) -> None:
    # Unsupported future slots remain preserved, never silently reinterpreted.
    try:
        slot = state(instance)
    except ValueError:
        return
    slot["seats"] = {}
    slot["revision"] += 1


register_module_state(ModuleStateSpec(NAME, 1, fresh, lambda raw: raw if isinstance(raw, dict) else fresh()))

module_hooks.register(module_hooks.SEAT_FORGOTTEN, NAME, remove_seat)
module_hooks.register(module_hooks.INSTANCE_RESET, NAME, reset)
