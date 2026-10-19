"""Schema 44→45: separate kernel configuration from optional preferences."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

_DEFAULTS = {
    "difficulty": "标准", "solo_mode": False, "seed_code": "", "entry_point": "web",
    "narrative_perspective": "auto", "gm_style_override": None,
    "dice_reveal_mode": "click", "luck_timeout_seconds": 60, "economy_reward_policy": {},
}
_GROUPS = {
    "game_config": ("difficulty", "solo_mode", "seed_code", "entry_point"),
    "narration_preferences": ("narrative_perspective", "gm_style_override"),
    "check_presentation": ("dice_reveal_mode", "luck_timeout_seconds"),
}


def split_table_preferences(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = deepcopy(payload)
    modules = candidate.setdefault("modules", {})
    if not isinstance(modules, dict):
        raise ValueError("schema 44 table preferences require a module object")
    legacy = modules.get("table_settings")
    if legacy is None:
        legacy = {"schema_version": 1}
    if not isinstance(legacy, dict) or legacy.get("schema_version") != 1:
        raise ValueError("cannot split unsupported table_settings schema")
    if any(name in modules for name in _GROUPS):
        raise ValueError("cannot split mixed legacy and new table preference slots")
    policy = legacy.get("economy_reward_policy", {})
    policy = policy if isinstance(policy, dict) else {}
    economy = modules.get("economy")
    if economy is not None and (not isinstance(economy, dict) or economy.get("schema_version") != 1):
        if policy:
            raise ValueError("cannot move reward policy into unsupported economy schema")
    elif isinstance(economy, dict) and "reward_policy" in economy and economy["reward_policy"] != policy:
        raise ValueError("conflicting legacy and economy reward policies")

    for name, fields in _GROUPS.items():
        modules[name] = {"schema_version": 1, **{key: deepcopy(legacy.get(key, _DEFAULTS[key])) for key in fields}}
    if economy is None:
        # Storage initialization fills the unchanged ledger defaults later.
        economy = modules["economy"] = {"schema_version": 1, "state": {}}
    if isinstance(economy, dict) and economy.get("schema_version") == 1:
        economy["reward_policy"] = deepcopy(policy)
    remainder = {key: value for key, value in legacy.items() if key != "schema_version" and key not in _DEFAULTS}
    if remainder:
        modules["table_settings"] = {"schema_version": 1, **remainder}
    else:
        modules.pop("table_settings", None)
    candidate["instance_schema_version"] = 45
    return candidate
