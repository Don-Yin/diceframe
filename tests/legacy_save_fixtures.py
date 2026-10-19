"""Construct historical test fixtures; this is not a supported save downgrade API."""
from copy import deepcopy


def legacy_table_payload(payload: dict) -> dict:
    """Rewrite only the known v45 preference layout to its pre-v45 test shape.

    Tests exercising older migrations must supply older storage, rather than
    merely relabel a newly serialized save with a historical version number.
    """
    result = deepcopy(payload)
    modules = result.get("modules", {})
    names = ("game_config", "narration_preferences", "check_presentation")
    if not any(name in modules for name in names):
        return result
    legacy = modules.setdefault("table_settings", {"schema_version": 1})
    assert legacy.get("schema_version") == 1
    for name in names:
        slot = modules.pop(name, None)
        if slot is not None:
            assert slot.get("schema_version") == 1, "future slots cannot form a historical fixture"
            legacy.update({key: value for key, value in slot.items() if key != "schema_version"})
    economy = modules.get("economy")
    if isinstance(economy, dict) and "reward_policy" in economy:
        assert economy.get("schema_version") == 1
        legacy["economy_reward_policy"] = economy.pop("reward_policy")
    result["instance_schema_version"] = 44
    return result
