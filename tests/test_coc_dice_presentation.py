"""CoC percentile presentation is projected by the rule, including 00 + 0."""
import pytest

from src.engine.checks import resolve_check_request
from src.rules.rule_system import RuleSystem
from tests.test_advantage_authority import _instance, _rule


@pytest.mark.parametrize("mode,chosen", [("advantage", 30), ("disadvantage", 100)])
def test_coc_result_projects_shared_units_tens_candidates_and_taken_index(mode, chosen):
    inst = _instance(skills=[{"name": "侦查", "value": 60}])
    result = resolve_check_request(inst, {
        "user_id": "a", "text": "搜索书房", "dice_value": chosen, "dice_rolls": [100, 30, 80],
        "check_request": {"check_id": "coc", "dice_system": "d100", "skill": "侦查", "advantage_mode": mode},
    }, _rule("freeform_coc.json"))
    assert result["dice_mechanic"] == "coc_bonus_penalty"
    assert result["percentile_dice"] == {
        "units": 0, "tens": [0, 30, 80], "candidates": [100, 30, 80],
        "taken_index": 1 if mode == "advantage" else 0,
        "bonus_dice": 2 if mode == "advantage" else 0,
        "penalty_dice": 2 if mode == "disadvantage" else 0,
    }


def test_generic_d100_does_not_gain_coc_labels_from_its_dice_name():
    inst = _instance(skills=[{"name": "侦查", "value": 60}])
    rule = RuleSystem({"rule_id": "custom", "dice_system": "d100"})
    result = resolve_check_request(inst, {"user_id": "a", "text": "搜索", "dice_value": 42}, rule)
    assert "percentile_dice" not in result


def test_independent_d100_rolls_cannot_be_presented_as_shared_units():
    inst = _instance(skills=[{"name": "侦查", "value": 60}])
    with pytest.raises(ValueError, match="shared units"):
        resolve_check_request(inst, {
            "user_id": "a", "text": "搜索", "dice_value": 12, "dice_rolls": [12, 85],
            "check_request": {"dice_system": "d100", "skill": "侦查", "advantage_mode": "advantage"},
        }, _rule("freeform_coc.json"))
