"""Narrator proposals cannot bypass rule-owned recovery authorization."""

from copy import deepcopy
from pathlib import Path
import re

import pytest

from src.commands.madness_tracker import MadnessTracker
from src.commands.player_state_applier import PlayerStateApplier
from src.commands.tag_parser import parse_tag_state
from src.engine.game_instance import GameInstance
from src.rules.rule_system import RuleSystem


POLICY = {"version": 1, "policy": "coc_light", "luck_recovery": "check"}
_MISSING = object()


def rule(recovery=POLICY, *, declared=True):
    stats = [{"key": key, "max": 99} for key in ("sanity", "luck")] if declared else []
    template = {"rule_id": "recovery_tag_test", "special_stats": stats}
    if recovery is not _MISSING:
        template["resource_recovery"] = deepcopy(recovery)
    return RuleSystem(template)


def game(*, resources=True):
    instance = GameInstance(game_key=("web", "recovery-tags", "gm"))
    sheet = {"hp": 10, "max_hp": 10}
    if resources:
        sheet.update(sanity=40, max_sanity=99, luck=50, max_luck=99)
        sheet["resources"] = {
            "sanity": {"current": 40, "max": 99, "min": 0},
            "luck": {"current": 50, "max": 99, "min": 0},
        }
    instance.players["alice"] = {"character_name": "Alice", "character_sheet": sheet}
    return instance


def apply(instance, update, selected_rule):
    PlayerStateApplier(MadnessTracker()).apply_players(instance, {"alice": update}, rule=selected_rule)


@pytest.mark.parametrize("tag,field,before", [("SAN", "sanity", 40), ("LUCK", "luck", 50)])
@pytest.mark.parametrize("policy_id", ["coc_light", "coc7e_style"])
def test_positive_legacy_tags_are_unapproved_recovery_proposals(tag, field, before, policy_id):
    instance = game()
    parsed = parse_tag_state(f"A moment of respite.\n---\n{tag}:alice:+5")
    apply(instance, parsed["state_update"]["players"]["alice"], rule({**POLICY, "policy": policy_id}))
    sheet = instance.get_character_sheet("alice")
    assert sheet[field] == before
    assert sheet["resources"][field]["current"] == before


def test_raw_resource_updates_cannot_bypass_the_legacy_tag_boundary():
    instance = game()
    apply(instance, {"stat_changes": {"sanity": 12, "luck": 12}}, rule())
    sheet = instance.get_character_sheet("alice")
    assert (sheet["sanity"], sheet["luck"]) == (40, 50)
    assert (sheet["resources"]["sanity"]["current"], sheet["resources"]["luck"]["current"]) == (40, 50)


def test_negative_legacy_and_raw_changes_still_apply_to_declared_resources():
    instance = game()
    apply(instance, {"san_change": -2, "luck_change": -3}, rule())
    apply(instance, {"stat_changes": {"sanity": -1, "luck": -1}}, rule())
    sheet = instance.get_character_sheet("alice")
    assert (sheet["sanity"], sheet["luck"]) == (37, 46)
    assert (sheet["resources"]["sanity"]["current"], sheet["resources"]["luck"]["current"]) == (37, 46)


def test_raw_san_loss_keeps_the_same_insanity_transition_as_san_tags():
    instance = game()
    apply(instance, {"stat_changes": {"sanity": -99}}, rule())
    sheet = instance.get_character_sheet('alice')
    assert sheet['sanity'] == 0 and sheet['deceased'] is True
    assert sheet['death_cause'] == '永久疯狂'


def test_negative_stat_cannot_restore_san_from_a_stale_resource_projection():
    instance = game()
    instance.get_character_sheet('alice').update(sanity=0, deceased=True, death_cause='永久疯狂')
    apply(instance, {'stat_changes': {'sanity': -1}}, rule())
    sheet = instance.get_character_sheet('alice')
    assert sheet['sanity'] == 0 and sheet['resources']['sanity']['current'] == 0
    assert sheet['deceased'] is True


def test_existing_canonical_resources_do_not_fall_back_to_legacy_default_values():
    instance = game()
    sheet = instance.get_character_sheet("alice")
    sheet.pop("sanity")
    sheet.pop("luck")
    apply(instance, {"san_change": -2, "luck_change": -3}, rule())
    sheet = instance.get_character_sheet("alice")
    assert (sheet["sanity"], sheet["luck"]) == (38, 47)
    assert "madness" not in sheet


def test_custom_rules_without_policy_keep_existing_tag_compatibility():
    instance = game()
    apply(instance, {"san_change": 2, "luck_change": 3}, rule(_MISSING))
    assert instance.get_character_sheet("alice")["sanity"] == 42
    assert instance.get_character_sheet("alice")["luck"] == 53


@pytest.mark.parametrize("recovery", [
    None,
    {},
    {"version": 2, "policy": "coc_light", "luck_recovery": "check"},
    {"version": 1, "policy": "unknown", "luck_recovery": "check"},
    {"version": 1, "policy": "coc_light", "luck_recovery": "always"},
])
def test_invalid_or_future_policy_is_rejected_before_any_player_mutation(recovery):
    instance = game()
    before = deepcopy(instance.players)
    with pytest.raises(ValueError):
        apply(instance, {"hp_change": -2, "san_change": 10, "luck_change": 10}, rule(recovery))
    assert instance.players == before


@pytest.mark.parametrize("declared,resources", [(False, True), (True, False), (False, False)])
def test_configured_recovery_never_invents_undeclared_or_missing_resources(declared, resources):
    instance = game(resources=resources)
    before = deepcopy(instance.get_character_sheet("alice"))
    apply(instance, {"san_change": -2, "luck_change": -2}, rule(declared=declared))
    sheet = instance.get_character_sheet("alice")
    for key in ("sanity", "luck"):
        if key in before:
            assert sheet[key] == before[key]
        else:
            assert key not in sheet
            assert key not in sheet.get("resources", {})


def test_sanity_loss_check_cannot_create_a_resource_that_the_character_lacks():
    instance = game(resources=False)
    apply(instance, {"san_check_loss": "1d6"}, rule())
    sheet = instance.get_character_sheet("alice")
    assert "sanity" not in sheet
    assert "sanity" not in sheet.get("resources", {})


def test_positive_sanity_tags_cannot_restore_a_permanently_insane_character():
    instance = game()
    sheet = instance.get_character_sheet("alice")
    sheet.update(sanity=0, deceased=True, death_cause="永久疯狂")
    sheet["resources"]["sanity"]["current"] = 0
    apply(instance, {"san_change": 20, "stat_changes": {"sanity": 20}}, rule())
    sheet = instance.get_character_sheet("alice")
    assert sheet["sanity"] == 0
    assert sheet["resources"]["sanity"]["current"] == 0
    assert sheet["deceased"] is True
    assert sheet["death_cause"] == "永久疯狂"


@pytest.mark.parametrize("locale", [None, "en", "ja"])
def test_builtin_coc_recovery_policy_and_prompts_are_consistent_across_locales(locale):
    path = (Path("templates/rules/locales") / locale / "freeform_coc.json"
            if locale else Path("templates/rules/freeform_coc.json"))
    selected_rule = RuleSystem.load(path)
    assert selected_rule.template["resource_recovery"] == POLICY
    prompt = selected_rule.template["gm_prompt_appendix"]
    assert not re.search(r"SAN:[^:\s]+:\+", prompt)
    assert "SAN_CHECK:" in prompt
