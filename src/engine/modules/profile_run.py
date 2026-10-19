"""Concrete profile binding and state; no rule or narrative authority duplication."""

from src.engine.module_state import (
    ModuleStateSpec,
    register_module_state,
    set_module_state,
)


def fresh():
    return {"schema_version": 1, "profile_id": "", "profile_version": 0}


def ensure(raw):
    return raw if isinstance(raw, dict) else fresh()


def unconfigured(slot):
    return slot is None or (
        isinstance(slot, dict)
        and type(slot.get("schema_version")) is int
        and slot.get("schema_version") == 1
        and slot.get("profile_id") == ""
        and type(slot.get("profile_version")) is int
        and slot.get("profile_version") == 0
    )


def install(instance, state):
    """Replace this module's supported slot through its owner boundary."""
    return set_module_state(instance, "profile_run", state)


register_module_state(ModuleStateSpec("profile_run", 1, fresh, ensure))
