"""Kernel game configuration; persisted owner for difficulty, solo_mode, seed_code, entry_point."""
from __future__ import annotations

from typing import Any
from src.engine.module_state import ModuleStateError, ModuleStateSpec, get_module_state, register_module_state

MODULE_NAME = "game_config"
SCHEMA_VERSION = 1


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, **{'difficulty': '标准', 'solo_mode': False, 'seed_code': '', 'entry_point': 'web'}}


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    defaults = fresh()
    if not isinstance(raw.get('difficulty'), str):
        raw['difficulty'] = defaults['difficulty']
    if not isinstance(raw.get('solo_mode'), bool):
        raw['solo_mode'] = defaults['solo_mode']
    if not isinstance(raw.get('seed_code'), str):
        raw['seed_code'] = defaults['seed_code']
    if not isinstance(raw.get('entry_point'), str):
        raw['entry_point'] = defaults['entry_point']
    return raw


def require_writable(instance: Any) -> None:
    modules = getattr(instance, "modules", None)
    if not isinstance(modules, dict):
        raise ModuleStateError("instance has no module state container")
    slot = modules.get(MODULE_NAME)
    if isinstance(slot, dict) and slot.get("schema_version") != SCHEMA_VERSION:
        raise ModuleStateError(f"unsupported {MODULE_NAME} module schema: {slot.get('schema_version')!r}")


def difficulty(instance: Any) -> str:
    return get_module_state(instance, MODULE_NAME)["difficulty"]


def replace_difficulty(instance: Any, value: str) -> None:
    get_module_state(instance, MODULE_NAME)["difficulty"] = value


def solo_mode(instance: Any) -> bool:
    return get_module_state(instance, MODULE_NAME)["solo_mode"]


def replace_solo_mode(instance: Any, value: bool) -> None:
    get_module_state(instance, MODULE_NAME)["solo_mode"] = value


def seed_code(instance: Any) -> str:
    return get_module_state(instance, MODULE_NAME)["seed_code"]


def replace_seed_code(instance: Any, value: str) -> None:
    get_module_state(instance, MODULE_NAME)["seed_code"] = value


def entry_point(instance: Any) -> str:
    return get_module_state(instance, MODULE_NAME)["entry_point"]


def replace_entry_point(instance: Any, value: str) -> None:
    get_module_state(instance, MODULE_NAME)["entry_point"] = value


def copy_for_carried_game(candidate: Any, source: Any) -> None:
    """Copy table policy while giving the separate Web game a fresh seed."""
    require_writable(source)
    require_writable(candidate)
    replace_difficulty(candidate, difficulty(source))
    replace_solo_mode(candidate, solo_mode(source))


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)
