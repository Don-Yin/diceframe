"""D&D attack-mode authority shared by pre-roll projection and resolution."""
from __future__ import annotations
from src.engine.modules import ruleset_runtime

from typing import Any

from src.engine.modules.check_modes import scoped


def context_id(engine: Any, instance: Any) -> str:
    combat = ruleset_runtime.state(instance).get("combat", {})
    order = combat.get("initiative", [])
    index = combat.get("turn_index", -1)
    current = order[index] if type(index) is int and 0 <= index < len(order) else ""
    return f"combat:{int(ruleset_runtime.state(instance).get('version', 0))}:{current}"


def attack_sources(actor: dict, target: dict, range_disadvantage: bool) -> list[dict]:
    sources = []
    for code in ("next_attack_advantage", "faerie_fire"):
        if code in target["conditions"]:
            sources.append({"code": code, "mode": "advantage"})
    if range_disadvantage:
        sources.append({"code": "long_range", "mode": "disadvantage"})
    if "dodging" in target["conditions"]:
        sources.append({"code": "dodging", "mode": "disadvantage"})
    if "next_attack_disadvantage" in actor["conditions"]:
        sources.append({"code": "next_attack_disadvantage", "mode": "disadvantage"})
    return sources


def mode_from_sources(sources: list[dict]) -> str:
    modes = {row["mode"] for row in sources}
    return next(iter(modes)) if len(modes) == 1 else ""


def attack_mode(engine: Any, instance: Any, actor: dict, target: dict,
                range_disadvantage: bool, *, use_grant: bool = True) -> dict:
    sources = attack_sources(actor, target, range_disadvantage)
    if use_grant and actor["kind"] == "player":
        grant = scoped(instance, actor["actor_id"].removeprefix("player:"), context_id(engine, instance)).get("grant")
        if grant:
            sources.append({"code": "gm_grant", "mode": grant["mode"], "reason": grant["reason"]})
    return {"mode": mode_from_sources(sources), "sources": sources}


def policy(engine: Any, instance: Any, uid: str) -> dict:
    combat = ruleset_runtime.state(instance).get("combat", {})
    scope = context_id(engine, instance)
    result = {"kind": "d20_keep_high_low", "scope": "combat_attack", "context_id": scope,
              "blocked_reason": "", "previews": []}
    if combat.get("status") != "active":
        result["blocked_reason"] = "combat_required"
        return result
    actor_id = f"player:{uid}"
    order = combat.get("initiative", [])
    index = combat.get("turn_index", -1)
    if type(index) is not int or not 0 <= index < len(order) or order[index] != actor_id:
        result["blocked_reason"] = "not_this_seat"
        return result
    actor = engine._actor_view(instance, combat, actor_id)
    for available in engine.available_intents(instance, uid):
        if available["type"] == "cast_spell":
            for spell in available.get("spells", []):
                if spell.get("mode") != "spell_attack":
                    continue
                for target in available.get("targets", []):
                    intent = {"intent_id": "check-mode-spell-preview", "submitted_by": instance.gm_uid,
                              "type": "cast_spell", "actor_id": actor_id, "target_ids": [target["actor_id"]],
                              "spell_ref": spell["spell_ref"], "slot_level": spell["available_slot_levels"][0],
                              "expected_version": int(ruleset_runtime.state(instance)["version"])}
                    if engine.validate_intent(instance, intent).get("ok"):
                        result["previews"].append({"spell_ref": spell["spell_ref"], "target_id": target["actor_id"],
                            "label": f"{spell['name']} → {target.get('name') or target['actor_id']}",
                            **attack_mode(engine, instance, actor, engine._actor_view(instance, combat, target["actor_id"]), False)})
        if available["type"] != "attack":
            continue
        for weapon in available.get("weapons", []):
            for target in available.get("targets", []):
                intent = {"intent_id": "check-mode-preview", "submitted_by": instance.gm_uid,
                          "type": "attack", "actor_id": actor_id, "target_id": target["actor_id"],
                          "weapon_ref": weapon["weapon_ref"], "expected_version": int(ruleset_runtime.state(instance)["version"])}
                if not engine.validate_intent(instance, intent).get("ok"):
                    continue
                profile = engine._declared_attack(actor, intent)
                distance = engine._distance(combat, actor_id, target["actor_id"])
                normal = int(profile.get("thrown_range") or profile["range"])
                maximum = int(profile.get("long_range") or profile.get("thrown_range") or profile["range"])
                result["previews"].append({"weapon_ref": weapon["weapon_ref"], "target_id": target["actor_id"],
                    "label": f"{weapon.get('name') or weapon['weapon_ref']} → {target.get('name') or target['actor_id']}",
                    **attack_mode(engine, instance, actor, engine._actor_view(instance, combat, target["actor_id"]),
                                  normal < distance <= maximum)})
    return result
