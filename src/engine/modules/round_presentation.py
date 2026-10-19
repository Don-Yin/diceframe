"""Round presentation state and the persistent quick-action display preference.

The core flow reaches this module only through ``module_hooks`` (round
processing begin, instance reset, module state record / read), so removing it drops
these presentation extras and nothing else.
"""

from __future__ import annotations

from typing import Any

from src.engine import module_hooks
from src.engine.contracts import TokenBudgetBump
from src.engine.module_state import ModuleStateError, ModuleStateSpec, get_module_state, register_module_state

MODULE_NAME = "round_presentation"
SCHEMA_VERSION = 1


def fresh() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "gm_directives": [],
        "quick_actions": [],
        "quick_actions_enabled": True,
        "last_state_update": None,
        "last_token_budget_bump": None,
        "pending_combat_results": [],
    }


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    raw.setdefault("quick_actions_enabled", True)
    for key in ("gm_directives", "quick_actions", "pending_combat_results"):
        if not isinstance(raw.get(key), list):
            raw[key] = []
    for key in ("last_state_update", "last_token_budget_bump"):
        if not isinstance(raw.get(key), dict):
            raw[key] = None
    return raw


def gm_directives(instance: Any) -> list[dict]:
    return get_module_state(instance, MODULE_NAME)["gm_directives"]


def replace_gm_directives(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["gm_directives"] = value if isinstance(value, list) else []


def quick_actions(instance: Any) -> list[str]:
    return get_module_state(instance, MODULE_NAME)["quick_actions"]


def replace_quick_actions(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["quick_actions"] = value if isinstance(value, list) else []


def last_state_update(instance: Any) -> dict | None:
    return get_module_state(instance, MODULE_NAME)["last_state_update"]


def replace_last_state_update(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["last_state_update"] = value if isinstance(value, dict) else None


def last_token_budget_bump(instance: Any) -> TokenBudgetBump | None:
    return get_module_state(instance, MODULE_NAME)["last_token_budget_bump"]


def replace_last_token_budget_bump(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["last_token_budget_bump"] = value if isinstance(value, dict) else None


def pending_combat_results(instance: Any) -> list[dict]:
    return get_module_state(instance, MODULE_NAME)["pending_combat_results"]


def replace_pending_combat_results(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["pending_combat_results"] = value if isinstance(value, list) else []


_LIST_REPORTS = {
    module_hooks.QUICK_ACTIONS: "quick_actions",
    module_hooks.GM_DIRECTIVES: "gm_directives",
    module_hooks.COMBAT_RESULTS: "pending_combat_results",
}
_DICT_REPORTS = {
    module_hooks.STATE_UPDATE: "last_state_update",
    module_hooks.TOKEN_BUDGET_BUMP: "last_token_budget_bump",
}


def begin_round(instance: Any) -> None:
    replace_last_token_budget_bump(instance, None)
    pending_combat_results(instance).clear()


def reset(instance: Any) -> None:
    for key in _LIST_REPORTS.values():
        get_module_state(instance, MODULE_NAME)[key].clear()
    for key in _DICT_REPORTS.values():
        get_module_state(instance, MODULE_NAME)[key] = None


def record_state(instance: Any, kind: str, value: Any) -> None:
    if kind == module_hooks.QUICK_ACTIONS_ENABLED:
        require_preferences_writable(instance)
        if type(value) is not bool:
            raise ValueError('quick_actions_enabled must be a boolean')
        get_module_state(instance, MODULE_NAME)['quick_actions_enabled'] = value
    elif kind in _LIST_REPORTS:
        get_module_state(instance, MODULE_NAME)[_LIST_REPORTS[kind]] = value if isinstance(value, list) else []
    elif kind in _DICT_REPORTS:
        get_module_state(instance, MODULE_NAME)[_DICT_REPORTS[kind]] = value if isinstance(value, dict) else None


def read_state(instance: Any, kind: str) -> Any:
    if kind == module_hooks.QUICK_ACTIONS_ENABLED:
        require_preferences_writable(instance)
        return get_module_state(instance, MODULE_NAME).get('quick_actions_enabled', True)
    key = _LIST_REPORTS.get(kind) or _DICT_REPORTS.get(kind)
    return None if key is None else get_module_state(instance, MODULE_NAME)[key]


def require_preferences_writable(instance: Any) -> None:
    slot = instance.modules.get(MODULE_NAME)
    if slot is not None and (not isinstance(slot, dict) or slot.get('schema_version') != SCHEMA_VERSION
                             or type(slot.get('quick_actions_enabled', True)) is not bool):
        raise ModuleStateError('unsupported or invalid round_presentation preferences')


def preflight_preferences(instance: Any, kind: str) -> None:
    if kind == module_hooks.QUICK_ACTIONS_ENABLED:
        require_preferences_writable(instance)


def carry_preferences(candidate: Any, source: Any) -> None:
    record_state(candidate, module_hooks.QUICK_ACTIONS_ENABLED, read_state(source, module_hooks.QUICK_ACTIONS_ENABLED))


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)
module_hooks.register(module_hooks.ROUND_PROCESSING_BEGIN, MODULE_NAME, begin_round)
module_hooks.register(module_hooks.INSTANCE_RESET, MODULE_NAME, reset)
module_hooks.register(module_hooks.STATE_RECORD, MODULE_NAME, record_state)
module_hooks.register(module_hooks.STATE_READ, MODULE_NAME, read_state)
module_hooks.register(module_hooks.STATE_WRITE_PREFLIGHT, MODULE_NAME, preflight_preferences)
module_hooks.register(module_hooks.INSTANCE_NEW_RUN_PREFLIGHT, MODULE_NAME, require_preferences_writable)
module_hooks.register(module_hooks.INSTANCE_NEW_RUN, MODULE_NAME, carry_preferences)
