"""Optional phase/calendar mechanism; narrative counters keep their meaning."""

from src.engine.module_state import (
    ModuleStateSpec,
    ModuleStateError,
    register_module_state,
    set_module_state,
)


def fresh():
    return {
        "schema_version": 1,
        "mode": "unconfigured",
        "phase": "",
        "cycle": 0,
        "day": 0,
        "acted": {},
    }


def ensure(raw):
    return raw if isinstance(raw, dict) else fresh()


def install(instance, state):
    """Replace this module's supported slot through its owner boundary."""
    return set_module_state(instance, "profile_progression", state)


def accepts_narrative(instance):
    from src.engine.modules import profile_run

    modules = getattr(instance, "modules", None)
    slot = modules.get("profile_progression") if isinstance(modules, dict) else None
    binding = modules.get("profile_run") if isinstance(modules, dict) else None
    return profile_run.unconfigured(binding) and (
        slot is None
        or (
            isinstance(slot, dict)
            and type(slot.get("schema_version")) is int
            and slot.get("schema_version") == 1
            and slot.get("mode") == "unconfigured"
        )
    )


def validate(slot, mode, phases):
    if (
        not isinstance(slot, dict)
        or type(slot.get("schema_version")) is not int
        or slot.get("schema_version") != 1
        or slot.get("mode") != mode
    ):
        raise ModuleStateError("unsupported profile progression")
    if slot.get("phase") not in phases or any(
        type(slot.get(key)) is not int or not 1 <= slot[key] <= 1000000
        for key in ("cycle", "day")
    ):
        raise ModuleStateError("invalid profile stage")
    acted = slot.get("acted")
    if (
        not isinstance(acted, dict)
        or len(acted) > 4
        or any(
            not isinstance(uid, str) or type(value) is not int or not 0 <= value <= 2
            for uid, value in acted.items()
        )
    ):
        raise ModuleStateError("invalid profile action counters")


def initial(mode, phases):
    if mode not in ("phase", "calendar") or not phases:
        raise ModuleStateError("unsupported profile progression configuration")
    return {**fresh(), "mode": mode, "phase": phases[0], "cycle": 1, "day": 1}


def advance(slot, mode, phases):
    validate(slot, mode, phases)
    if mode == "phase":
        index = phases.index(slot["phase"]) + 1
        slot["phase"] = phases[index % len(phases)]
        if index == len(phases):
            slot["cycle"] += 1
    else:
        slot["day"] += 1
    slot["acted"] = {}
    validate(slot, mode, phases)


register_module_state(ModuleStateSpec("profile_progression", 1, fresh, ensure))
