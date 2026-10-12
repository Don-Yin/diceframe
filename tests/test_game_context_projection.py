"""Behavior contracts for generic and legacy game-context projections."""

from src.engine.game_context_projector import GameContextProjector
from src.engine.game_instance import GameInstance
from src.rulesets.legacy_adapter import LegacyRulesetAdapter


def _instance_with_legacy_character() -> GameInstance:
    instance = GameInstance(game_key=("web", "projection", "bot"))
    instance.players["player"] = {
        "character_name": "艾琳",
        "character_sheet": {
            "attributes": {"str": 14},
            "equipment": [{"name": "旅行斗篷", "type": "clothing"}],
            "skills": ["观察"],
        },
    }
    return instance


def test_generic_projection_does_not_invent_legacy_mechanics() -> None:
    sheet = GameContextProjector.project(_instance_with_legacy_character())[
        "players"
    ]["player"]["character_sheet"]

    assert sheet["attributes"] == {"str": 14}
    assert sheet["skills"] == ["观察"]
    assert "_modifiers" not in sheet
    assert "_armor" not in sheet


def test_legacy_runtime_explicitly_preserves_legacy_prompt_projection() -> None:
    sheet = LegacyRulesetAdapter().build_llm_view(_instance_with_legacy_character())[
        "players"
    ]["player"]["character_sheet"]

    assert sheet["_modifiers"] == {"str": 2}
    assert sheet["_armor"] == 1
    assert sheet["skills"] == [{"name": "观察", "value": 20}]
