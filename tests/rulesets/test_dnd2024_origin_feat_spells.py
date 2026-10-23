"""Origin-feat (Magic Initiate) spells, newly automated cantrips, and Shield."""

from __future__ import annotations

from copy import deepcopy

from src.engine.modules import ruleset_runtime
from src.rulesets.dnd2024.resting import Dnd2024RestEngine
from src.rulesets.dnd2024.runtime import Dnd2024Runtime

from dnd2024_monk_common import SequenceRng, monk_draft, monk_instance, start_combat


def sage_monk_sheet(
    runtime: Dnd2024Runtime, *, ability: str = "wis",
    cantrips: tuple[str, ...] = ("fire_bolt", "chill_touch"), spell: str = "shield",
) -> dict:
    """A Monk (no class spellcasting) whose Sage background grants Magic Initiate."""

    draft = monk_draft(runtime)
    draft.update(
        background_ref="background:sage",
        background_equipment_package_ref="equipment_package:sage_b",
    )
    choices = runtime.builder_choices(None, draft)
    refs = choices["background_ability_refs"]
    draft["background_ability_bonuses"] = {
        refs[0].split(":", 1)[1]: 2, refs[1].split(":", 1)[1]: 1,
    }
    draft["feat_choice_answers"] = {
        feat["feat_ref"]: {
            spec["id"]: [option["value"] for option in spec["options"]][: int(spec["count"])]
            for spec in feat["specs"]
        }
        for feat in choices["feat_choices"]
    }
    draft["feat_choice_answers"]["feat:magic_initiate_wizard"] = {
        "spellcasting_ability": [ability],
        "cantrips": list(cantrips),
        "level_1_spell": [spell],
    }
    assert runtime.validate_character(None, draft) == []
    return runtime.finalize_character(None, draft)


def setup(**kwargs):
    runtime = Dnd2024Runtime()
    sheet = sage_monk_sheet(runtime, **kwargs)
    engine, instance = monk_instance(runtime, sheet)
    start_combat(engine, instance, hp=100)
    return runtime, engine, instance


def intent(instance, kind: str, **extra) -> dict:
    version = ruleset_runtime.state(instance)["version"]
    return {
        "intent_id": f"{kind}:{version}", "type": kind, "expected_version": version,
        "submitted_by": "gm", "actor_id": "player:gm", **extra,
    }


def apply(engine, instance, request, rolls):
    resolved = engine.resolve_intent(instance, request, SequenceRng(list(rolls)))
    assert resolved["ok"], resolved
    assert engine.apply_batch(instance, resolved["event_batch"])["applied"]
    return resolved["event_batch"]["events"]


def player(instance) -> dict:
    return instance.get_character_sheet("gm")["ruleset_character"]


def spell_action(engine, instance) -> dict | None:
    return next(
        (row for row in engine.available_intents(instance, "gm") if row["type"] == "cast_spell"),
        None,
    )


def enemy_turn(engine, instance) -> None:
    apply(engine, instance, intent(instance, "end_turn"), [])
    assert ruleset_runtime.state(instance)["combat"]["initiative"][
        ruleset_runtime.state(instance)["combat"]["turn_index"]
    ] == "enemy:goblin-1"


def goblin_attack(engine, instance, roll: int) -> list[dict]:
    request = {
        **intent(instance, "attack", target_id="player:gm", attack_id="scimitar"),
        "actor_id": "enemy:goblin-1",
    }
    return apply(engine, instance, request, [roll, 4])


def test_magic_initiate_spells_reach_combat_with_feat_ability() -> None:
    _runtime, engine, instance = setup()
    action = spell_action(engine, instance)
    assert action is not None
    refs = {row["spell_ref"] for row in action["spells"]}
    assert {"spell:fire_bolt", "spell:chill_touch"} <= refs
    # Shield is only castable as a reaction, never from the turn menu.
    assert "spell:shield" not in refs
    actor = next(
        row for row in engine.gameplay_view(instance)["combat"]["actors"]
        if row["actor_id"] == "player:gm"
    )
    reasons = {row["spell_ref"]: row["blocked_reason"] for row in actor["spells"]}
    assert reasons["spell:shield"] == "requires_being_hit"

    wis = player(instance)["abilities"]["wis"]
    expected_bonus = 2 + (wis - 10) // 2
    events = apply(engine, instance, intent(
        instance, "cast_spell", spell_ref="spell:fire_bolt",
        target_id="enemy:goblin-1", slot_level=0,
    ), [15, 7])
    check = next(row for row in events if row["type"] == "check.resolved")
    assert check["modifier"] == expected_bonus
    damage = next(row for row in events if row["type"] == "resource.changed")
    assert damage["damage_type"] == "fire" and damage["amount"] == 7


def test_chill_touch_blocks_healing_until_end_of_casters_next_turn() -> None:
    _runtime, engine, instance = setup()
    events = apply(engine, instance, intent(
        instance, "cast_spell", spell_ref="spell:chill_touch",
        target_id="enemy:goblin-1", slot_level=0,
    ), [15, 5])
    assert any(
        row["type"] == "condition.applied" and row["condition"] == "cannot_regain_hp"
        for row in events
    )
    combat = ruleset_runtime.state(instance)["combat"]
    assert "cannot_regain_hp" in combat["enemies"]["goblin-1"]["conditions"]
    enemy_turn(engine, instance)
    combat = ruleset_runtime.state(instance)["combat"]
    assert "cannot_regain_hp" in combat["enemies"]["goblin-1"]["conditions"]
    apply(engine, instance, intent(instance, "end_turn", actor_id="enemy:goblin-1"), [])
    apply(engine, instance, intent(instance, "end_turn", actor_id="player:gm"), [])
    combat = ruleset_runtime.state(instance)["combat"]
    assert "cannot_regain_hp" not in combat["enemies"]["goblin-1"]["conditions"]


def test_shield_reaction_is_offered_on_enemy_turn_and_negates_the_hit() -> None:
    runtime, engine, instance = setup()
    enemy_turn(engine, instance)
    hp_before = player(instance)["resources"]["hp"]
    ac = player(instance)["derived"]["armor_class"]
    # Goblin +4: a natural roll that just hits, so +5 AC turns it into a miss.
    events = goblin_attack(engine, instance, ac - 4)
    pending = next(row for row in events if row["type"] == "dnd2024.decision.pending")
    assert pending["kind"] == "hit_reaction_spell"
    assert pending["assigned_to"] == "gm"
    assert player(instance)["resources"]["hp"] == hp_before

    # The defender sees the decision even though it is the goblin's turn.
    decision_action = next(
        row for row in engine.available_intents(instance, "gm")
        if row["type"] == "decision.resolve"
    )
    decision = decision_action["decisions"][0]
    assert decision["spells"][0]["spell_ref"] == "spell:shield"
    assert decision["spells"][0]["available_slot_levels"] == [0]
    # Nothing else may resolve while the defender decides.
    blocked = engine.resolve_intent(instance, {
        **intent(instance, "end_turn"), "actor_id": "enemy:goblin-1",
    }, SequenceRng([]))
    assert blocked["ok"] is False

    events = apply(engine, instance, {
        **intent(instance, "decision.resolve"), "decision_id": decision["decision_id"],
        "option": "cast", "spell_ref": "spell:shield", "slot_level": 0,
    }, [])
    types = [row["type"] for row in events]
    assert "dnd2024.reaction.spent" in types
    assert "dnd2024.feat_spell.free_cast_spent" in types
    assert "resource.changed" not in types
    assert player(instance)["resources"]["hp"] == hp_before
    assert player(instance)["spellcasting"]["magic_initiate"][0]["free_cast_used"] is True
    view_ac = next(
        row for row in engine.gameplay_view(instance)["combat"]["actors"]
        if row["actor_id"] == "player:gm"
    )
    assert "shield" in view_ac["conditions"]

    # Free cast spent, no slots, reaction spent: a later hit offers nothing.
    combat = ruleset_runtime.state(instance)["combat"]
    assert combat["reactions"]["player:gm"] == 0
    defender = engine._actor_view(instance, combat, "player:gm")
    combat["reactions"]["player:gm"] = 1
    defender["conditions"].pop("shield")
    assert engine._reaction_spell_choices(combat, defender) == []
    combat["reactions"]["player:gm"] = 0

    rested = Dnd2024RestEngine(runtime.load_bundle("en")).complete_long_rest(
        deepcopy(player(instance)),
    )
    assert {"type": "restore_feat_spell", "feat_ref": "feat:magic_initiate_wizard"} in rested["events"]
    assert "free_cast_used" not in rested["character"]["spellcasting"]["magic_initiate"][0]


def test_declining_shield_applies_the_held_damage() -> None:
    _runtime, engine, instance = setup()
    enemy_turn(engine, instance)
    hp_before = player(instance)["resources"]["hp"]
    events = goblin_attack(engine, instance, 18)
    pending = next(row for row in events if row["type"] == "dnd2024.decision.pending")
    held = pending["damage_event"]["amount"]
    apply(engine, instance, {
        **intent(instance, "decision.resolve"), "decision_id": pending["decision_id"],
        "option": "decline",
    }, [])
    assert player(instance)["resources"]["hp"] == hp_before - held
    assert "free_cast_used" not in player(instance)["spellcasting"]["magic_initiate"][0]


def test_shield_reaction_yields_hit_spell_decision_before_damage() -> None:
    _runtime, engine, instance = setup()
    enemy_turn(engine, instance)
    events = goblin_attack(engine, instance, 18)
    pending = next(row for row in events if row["type"] == "dnd2024.decision.pending")
    state_pending = ruleset_runtime.state(instance)["combat"]["pending_decisions"][0]
    state_pending["next_decision"] = {
        "decision_id": "melee-hit:smite",
        "kind": "melee_hit_spell",
        "actor_id": "player:gm",
        "target_id": "enemy:goblin-1",
        "assigned_to": "gm",
        "options": ["decline"],
        "damage_event": deepcopy(state_pending["damage_event"]),
        "critical": False,
    }
    follow_up = apply(engine, instance, {
        **intent(instance, "decision.resolve"),
        "decision_id": state_pending["decision_id"], "option": "decline",
    }, [])
    assert not any(row["type"] == "resource.changed" for row in follow_up)
    chained = next(row for row in follow_up if row["type"] == "dnd2024.decision.pending")
    assert chained["kind"] == "melee_hit_spell"
    assert ruleset_runtime.state(instance)["combat"]["pending_decisions"][0]["kind"] == "melee_hit_spell"


def test_critical_hit_still_offers_shield_but_cannot_become_a_miss() -> None:
    _runtime, engine, instance = setup()
    enemy_turn(engine, instance)
    hp_before = player(instance)["resources"]["hp"]
    events = goblin_attack(engine, instance, 20)
    pending = next(row for row in events if row["type"] == "dnd2024.decision.pending")
    assert pending["kind"] == "hit_reaction_spell"
    follow_up = apply(engine, instance, {
        **intent(instance, "decision.resolve"),
        "decision_id": pending["decision_id"], "option": "cast",
        "spell_ref": "spell:shield", "slot_level": 0,
    }, [])
    assert any(row["type"] == "resource.changed" for row in follow_up)
    assert player(instance)["resources"]["hp"] < hp_before


def test_ai_hosted_defender_casts_shield_only_when_it_turns_the_hit() -> None:
    _runtime, engine, instance = setup()
    enemy_turn(engine, instance)
    combat = ruleset_runtime.state(instance)["combat"]
    decision = {
        "decision_id": "d", "kind": "hit_reaction_spell", "actor_id": "player:gm",
        "attack_total": 30, "armor_class": 12,
        "spells": [{"spell_ref": "spell:shield", "available_slot_levels": [0], "armor_class_bonus": 5}],
    }
    from src.engine import player_control

    player_control.set_control(instance, "gm", "ai")
    auto = engine._automatic_hit_reaction(instance, combat, decision, 1)
    assert auto["option"] == "decline"
    decision["attack_total"] = 14
    auto = engine._automatic_hit_reaction(instance, combat, decision, 1)
    assert auto["option"] == "cast" and auto["slot_level"] == 0


def test_feat_concentration_spell_works_without_class_spellcasting() -> None:
    runtime = Dnd2024Runtime()
    draft = monk_draft(runtime)  # Acolyte -> Magic Initiate (Cleric)
    draft["feat_choice_answers"]["feat:magic_initiate_cleric"] = {
        "spellcasting_ability": ["wis"],
        "cantrips": ["sacred_flame", "spare_the_dying"],
        "level_1_spell": ["bless"],
    }
    assert runtime.validate_character(None, draft) == []
    sheet = runtime.finalize_character(None, draft)
    engine, instance = monk_instance(runtime, sheet)
    start_combat(engine, instance, hp=100)
    apply(engine, instance, intent(
        instance, "cast_spell", spell_ref="spell:bless",
        target_ids=["player:gm"], slot_level=0,
    ), [])
    spellcasting = player(instance)["spellcasting"]
    assert "class" not in spellcasting
    assert spellcasting["concentration"]["spell_ref"] == "spell:bless"
    assert spellcasting["magic_initiate"][0]["free_cast_used"] is True
    rested = Dnd2024RestEngine(runtime.load_bundle("en")).complete_long_rest(
        deepcopy(player(instance)),
    )
    assert rested["character"]["spellcasting"]["concentration"] is None


def test_spare_the_dying_stabilizes_a_downed_ally() -> None:
    runtime = Dnd2024Runtime()
    draft = monk_draft(runtime)
    draft["feat_choice_answers"]["feat:magic_initiate_cleric"] = {
        "spellcasting_ability": ["wis"],
        "cantrips": ["sacred_flame", "spare_the_dying"],
        "level_1_spell": ["bless"],
    }
    sheet = runtime.finalize_character(None, draft)
    engine, instance = monk_instance(runtime, sheet)
    start_combat(engine, instance, hp=100)
    healthy = engine.resolve_intent(instance, intent(
        instance, "cast_spell", spell_ref="spell:spare_the_dying",
        target_id="player:gm", slot_level=0,
    ), SequenceRng([]))
    assert healthy["ok"] is False
    assert "dying ally" in healthy["error"]
