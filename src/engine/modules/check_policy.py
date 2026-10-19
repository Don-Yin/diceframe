"""Optional pushed-roll policy. Missing old-save slots retain enabled behavior."""
from __future__ import annotations

from typing import Any

from src.engine import module_hooks
from src.engine.module_state import ModuleStateError, ModuleStateSpec, get_module_state, register_module_state

NAME = 'check_policy'


def fresh() -> dict:
    return {'schema_version': 1, 'push_enabled': True}


def ensure(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get('schema_version') == 1 and 'push_enabled' not in raw:
        raw['push_enabled'] = True
    return raw


def require_writable(instance: Any) -> None:
    slot = instance.modules.get(NAME)
    if slot is not None and (not isinstance(slot, dict) or slot.get('schema_version') != 1
                             or type(slot.get('push_enabled', True)) is not bool):
        raise ModuleStateError('unsupported or invalid check_policy module')


def push_enabled(instance: Any) -> bool:
    require_writable(instance)
    return get_module_state(instance, NAME)['push_enabled']


def replace_push_enabled(instance: Any, value: bool) -> None:
    require_writable(instance)
    if type(value) is not bool:
        raise ValueError('push_enabled must be a boolean')
    get_module_state(instance, NAME)['push_enabled'] = value


def carry(candidate: Any, source: Any) -> None:
    replace_push_enabled(candidate, push_enabled(source))


def preflight(instance: Any, kind: str) -> None:
    if kind == module_hooks.PUSH_ENABLED:
        require_writable(instance)


def read(instance: Any, kind: str) -> bool | None:
    return push_enabled(instance) if kind == module_hooks.PUSH_ENABLED else None


def record(instance: Any, kind: str, value: Any) -> None:
    if kind == module_hooks.PUSH_ENABLED:
        replace_push_enabled(instance, value)


register_module_state(ModuleStateSpec(NAME, 1, fresh, ensure))
module_hooks.register(module_hooks.INSTANCE_NEW_RUN_PREFLIGHT, NAME, require_writable)
module_hooks.register(module_hooks.INSTANCE_NEW_RUN, NAME, carry)
module_hooks.register(module_hooks.STATE_WRITE_PREFLIGHT, NAME, preflight)
module_hooks.register(module_hooks.STATE_READ, NAME, read)
module_hooks.register(module_hooks.STATE_RECORD, NAME, record)
