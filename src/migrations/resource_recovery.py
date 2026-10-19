"""Fail-closed save/import boundary for one-use recovery qualifications.

Missing slots belong to old readers and stay missing until normal instance
defaults run. Existing qualifications are validated before those defaults can
erase a malformed envelope. Import never transfers a Keeper's pending grant.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from src.engine.module_state import ModuleStateError
from src.engine.modules import resource_recovery


def _validate_slot(slot: Any) -> None:
    resource_recovery.require_writable(SimpleNamespace(modules={resource_recovery.MODULE_NAME: slot}))


def validate_recovery_state(payload: dict[str, Any]) -> None:
    """Validate live authority and historical rewind snapshots without repair."""
    modules = payload.get("modules")
    # Before schema 47 no recovery ledger existed. Preserve the established
    # migration repair of malformed legacy containers; a current writer must
    # never lose a possibly populated authority ledger through that repair.
    if ("modules" in payload and not isinstance(modules, dict)
            and int(payload.get("instance_schema_version", 1) or 1) >= 47):
        raise ModuleStateError("invalid persisted module container")
    if isinstance(modules, dict) and resource_recovery.MODULE_NAME in modules:
        slot = modules[resource_recovery.MODULE_NAME]
        _validate_slot(slot)
        for source in slot["sources"].values():
            if source["status"] in {"pending", "approved"} and source["run_id"] != payload.get("run_id"):
                raise ModuleStateError("pending resource recovery qualification belongs to another run")
    log = payload.get("log")
    if isinstance(log, list):
        for entry in log:
            if isinstance(entry, dict) and "pre_resource_recovery" in entry:
                _validate_slot(entry["pre_resource_recovery"])


def rebind_recovery_state(payload: dict[str, Any], *, run_id: str) -> None:
    """Keep settled provenance/consumption, refusing transferable pending grants."""
    validate_recovery_state(payload)
    modules = payload.get("modules")
    slot = modules.get(resource_recovery.MODULE_NAME) if isinstance(modules, dict) else None
    if slot is None or run_id == payload.get("run_id"):
        return
    if any(source["status"] in {"pending", "approved"} for source in slot["sources"].values()):
        raise ValueError("resolve or reject pending resource recovery before importing into another run")
    # Settled/rejected sources, command identities, receipts and consumed scopes
    # retain their original run. No new eligibility or RNG seed is minted.
    # Historical qualifications cannot become executable in a different run.
    # Keep the current audit ledger while removing only its old rollback entry
    # points; ordinary player/world history and receipt provenance are intact.
    slot.pop("_before_round", None)
    for entry in payload.get("log") or []:
        if isinstance(entry, dict):
            entry.pop("pre_resource_recovery", None)
