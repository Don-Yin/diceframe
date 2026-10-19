"""Explicit, bounded CoC recovery strategies; no clock or balance ownership."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

PROFILES = frozenset({"coc_light", "coc7e_style"})
RESOURCES = frozenset({"sanity", "luck"})
KINDS = frozenset({"overnight", "therapy", "luck", "reward"})
DAY_MINUTES = 1440
MONTH_MINUTES = 30 * DAY_MINUTES


def policy(rule: Any) -> dict[str, Any] | None:
    """A missing declaration disables recovery; malformed declarations refuse."""
    template = getattr(rule, "template", {})
    if not isinstance(template, dict) or "resource_recovery" not in template:
        return None
    raw = template["resource_recovery"]
    if (not isinstance(raw, dict) or set(raw) != {"version", "policy", "luck_recovery"}
            or type(raw.get("version")) is not int or raw["version"] != 1
            or not isinstance(raw.get("policy"), str) or raw["policy"] not in PROFILES
            or not isinstance(raw.get("luck_recovery"), str) or raw["luck_recovery"] not in {"check", "off"}):
        raise ValueError("resource_recovery requires a supported complete version 1 policy")
    return deepcopy(raw)


def managed_resources(rule: Any) -> frozenset[str]:
    if policy(rule) is None:
        return frozenset()
    stats = getattr(rule, "template", {}).get("special_stats", [])
    if not isinstance(stats, list) or any(not isinstance(item, dict) for item in stats):
        raise ValueError("resource_recovery requires valid special_stats declarations")
    if any(not isinstance(item.get("key"), str) for item in stats):
        raise ValueError("special_stats require canonical resource keys")
    names = [item["key"] for item in stats if item["key"] in RESOURCES]
    if len(names) != len(set(names)):
        raise ValueError("duplicate recovery resource declaration")
    return frozenset(names)


def requirements(rule: Any, kind: str) -> dict[str, Any]:
    selected = policy(rule)
    if selected is None:
        raise ValueError("this rule does not declare resource recovery")
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("unsupported recovery source kind")
    strict = selected["policy"] == "coc7e_style"
    if kind == "overnight":
        if strict:
            raise ValueError("CoC 7e style does not recover SAN from overnight rest")
        return {"resource_key": "sanity", "duration": 480, "period": DAY_MINUTES, "skills": ()}
    if kind == "therapy":
        return {"resource_key": "sanity", "duration": MONTH_MINUTES if strict else 0,
                "period": MONTH_MINUTES if strict else DAY_MINUTES,
                "skills": ("psychoanalysis",) if strict else ("psychoanalysis", "psychology")}
    if kind == "luck":
        if selected["luck_recovery"] != "check":
            raise ValueError("Luck recovery is disabled by this rule")
        return {"resource_key": "luck", "duration": 0, "period": 0, "skills": ()}
    return {"resource_key": "", "duration": 0, "period": 0, "skills": ()}


def reward_delta(value: Any) -> int | str:
    if type(value) is int and -99 <= value <= 99:
        return value
    if isinstance(value, str) and value in {"1d3", "1d6", "1d10"}:
        return value
    raise ValueError("reward delta must be an integer -99..99 or 1d3, 1d6, 1d10")


def skill_value(rule: Any, healer: dict[str, Any], skill_id: str) -> int:
    """Resolve canonical rows, with explicit template aliases for legacy sheets."""
    template = getattr(rule, "template", {})
    definitions = template.get("skills") or {}
    definition = definitions.get(skill_id) if isinstance(definitions, dict) else None
    aliases: set[str] = {skill_id}
    if isinstance(definition, dict) and isinstance(definition.get("name"), str):
        aliases.add(definition["name"])
    canonical = template.get("canonical_skill_names") or {}
    if isinstance(canonical, dict) and isinstance(canonical.get(skill_id), str):
        aliases.add(canonical[skill_id])
    improvement = template.get("skill_improvement") or {}
    identity_aliases = improvement.get("identity_aliases") if isinstance(improvement, dict) else None
    if isinstance(identity_aliases, dict):
        declared_aliases = identity_aliases.get(skill_id, [])
        if not isinstance(declared_aliases, list):
            raise ValueError("treatment skill aliases must be an explicit list")
        aliases.update(item for item in declared_aliases if isinstance(item, str))
    skills = healer.get("skills", [])
    if not isinstance(skills, list):
        raise ValueError("healer has no valid skill rows")
    matches = [row for row in skills if isinstance(row, dict) and (
        row.get("id") == skill_id or (not row.get("id") and isinstance(row.get("name"), str)
                                     and row["name"] in aliases))]
    if len(matches) != 1 or type(matches[0].get("value")) is not int or not 0 <= matches[0]["value"] <= 100:
        raise ValueError("healing skill must identify one server-owned skill value")
    return matches[0]["value"]


def resolve_delta(rule: Any, source: dict[str, Any], character: dict[str, Any],
                  healer: dict[str, Any] | None, rng: Any) -> dict[str, Any]:
    """Roll this recovery's own purpose-bound check, never a narrator check."""
    kind = source["kind"]
    selected = policy(rule)
    requirements(rule, kind)
    rolls: dict[str, int] = {}
    delta = 0
    success = True
    fumble = False
    if kind == "overnight":
        rolls["recovery"] = rng.randint(1, 6)
        delta = rolls["recovery"]
    elif kind == "therapy":
        threshold = skill_value(rule, healer or {}, source["skill_id"])
        rolls["threshold"] = threshold
        rolls["check"] = rng.randint(1, 100)
        fumble = rolls["check"] == 100 or (threshold < 50 and rolls["check"] >= 96)
        success = rolls["check"] <= threshold and not fumble
        if success:
            rolls["recovery"] = rng.randint(1, 3)
            delta = rolls["recovery"]
        elif fumble and selected and selected["policy"] == "coc7e_style":
            rolls["loss"] = rng.randint(1, 6)
            delta = -rolls["loss"]
    elif kind == "luck":
        rolls["threshold"] = int(character["luck"])
        rolls["check"] = rng.randint(1, 100)
        success = rolls["check"] > rolls["threshold"]
        if success:
            rolls["recovery"] = rng.randint(1, 10)
            delta = rolls["recovery"]
    else:
        configured = reward_delta(source["resource_delta"])
        if isinstance(configured, str):
            rolls["recovery"] = rng.randint(1, int(configured[2:]))
            delta = rolls["recovery"]
        else:
            delta = configured
    return {"resource_delta": delta, "rolls": rolls, "success": success, "fumble": fumble}
