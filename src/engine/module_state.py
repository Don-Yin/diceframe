"""Per-module persisted state slots on GameInstance.

Concrete modules own their slots; this registry must not import GameInstance
or any concrete module. Unknown schemas are preserved but cannot be used by
this runtime.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

MODULES_KEY = "modules"


class ModuleStateError(ValueError):
    """A module slot cannot be accepted by this runtime."""


@dataclass(frozen=True)
class ModuleStateSpec:
    """Creation and idempotent repair for one module's persisted slot.

    ``ensure`` repairs missing/corrupt slots, preserving unknown schema versions
    verbatim rather than guessing how to interpret them.
    """

    name: str
    schema_version: int
    fresh: Callable[[], dict[str, Any]]
    ensure: Callable[[Any], dict[str, Any]]


_SPECS: dict[str, ModuleStateSpec] = {}


def register_module_state(spec: ModuleStateSpec) -> None:
    if not spec.name or not spec.name.isidentifier():
        raise ValueError(f"invalid module state name: {spec.name!r}")
    _SPECS[spec.name] = spec


def registered_module_states() -> tuple[ModuleStateSpec, ...]:
    return tuple(_SPECS[name] for name in sorted(_SPECS))


def module_state_spec(name: str) -> ModuleStateSpec:
    try:
        return _SPECS[name]
    except KeyError as exc:
        raise ModuleStateError(f"unknown module state: {name!r}") from exc


def ensure_module_states(modules: Any) -> dict[str, dict[str, Any]]:
    """Materialize registered slots and preserve unregistered dict slots."""

    result: dict[str, dict[str, Any]] = {}
    if isinstance(modules, Mapping):
        for key, value in modules.items():
            if isinstance(value, dict):
                result[str(key)] = value
    for spec in registered_module_states():
        result[spec.name] = spec.ensure(result.get(spec.name))
    return result


def get_module_state(instance: Any, name: str) -> dict[str, Any]:
    """Return the live slot; reject unknown schemas without changing them."""

    modules = getattr(instance, MODULES_KEY, None)
    if not isinstance(modules, dict):
        raise ModuleStateError("instance has no module state container")
    spec = module_state_spec(name)
    slot = modules.get(name)
    if not isinstance(slot, dict):
        slot = spec.ensure(slot)
        modules[name] = slot
    if slot.get("schema_version") != spec.schema_version:
        raise ModuleStateError(f"unsupported {name} module schema: {slot.get('schema_version')!r}")
    return slot


def set_module_state(instance: Any, name: str, value: Mapping[str, Any]) -> dict[str, Any]:
    """Replace a supported slot. Only the owning module may call this."""

    get_module_state(instance, name)
    spec = module_state_spec(name)
    slot = spec.ensure(dict(value))
    if slot.get("schema_version") != spec.schema_version:
        raise ModuleStateError(f"unsupported {name} module schema: {slot.get('schema_version')!r}")
    modules = getattr(instance, MODULES_KEY)
    modules[name] = slot
    return slot
