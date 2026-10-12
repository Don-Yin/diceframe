from __future__ import annotations

from src.engine.game_instance import GameInstance
from src.rulesets.dnd2024 import advancement_access
from src.engine.modules import ruleset_runtime


def _instance() -> GameInstance:
    instance = GameInstance(
        game_key=("web", "advancement", "web_bot"),
        world_id="test-world",
        rule_id="dnd2024_srd",
    )
    for user_id, name in (("hero", "Hero"), ("ally", "Ally")):
        instance.players[user_id] = {
            "character_name": name,
            "character_sheet": {
                "character_name": name,
                "ruleset_character": {
                    "build": {"level": 1, "class_levels": [{"level": 1}]},
                },
            },
        }
    ruleset_runtime.replace_binding(instance, {"id": "core:dnd2024"})
    return instance


def test_old_save_defaults_to_ai_milestone() -> None:
    status = advancement_access.view(_instance())

    assert status["mode"] == "milestone"
    assert status["authority"] == "ai_gm"
    assert all(not row["entitled"] for row in status["players"])


def test_read_only_projection_does_not_normalize_old_save() -> None:
    instance = _instance()
    ruleset_runtime.replace_state(instance, {"unrelated": {"kept": True}})

    status = advancement_access.project(instance)

    assert status["mode"] == "milestone"
    assert status["authority"] == "ai_gm"
    assert ruleset_runtime.state(instance) == {"unrelated": {"kept": True}}


def test_milestone_grants_only_one_next_level_entitlement() -> None:
    instance = _instance()

    assert advancement_access.grant(instance, "hero", source="gm") is True
    assert advancement_access.grant(instance, "hero", source="gm") is False
    advancement_access.require_entitlement(instance, "hero", 2)
    advancement_access.consume(instance, "hero", 2)

    assert advancement_access.view(instance)["players"][0]["entitled"] is False


def test_xp_crossing_threshold_grants_entitlement_once() -> None:
    instance = _instance()
    advancement_access.configure(instance, "xp", "gm")

    below = advancement_access.award_xp(instance, "hero", 299, source="gm")
    crossed = advancement_access.award_xp(instance, "hero", 1, source="gm")
    repeated = advancement_access.award_xp(instance, "hero", 50, source="gm")

    assert below == {"total": 299, "granted": False}
    assert crossed == {"total": 300, "granted": True}
    assert repeated == {"total": 350, "granted": False}
    advancement_access.require_entitlement(instance, "hero", 2)


def test_xp_reconciles_next_entitlement_after_level_up() -> None:
    instance = _instance()
    advancement_access.configure(instance, "xp", "gm")
    advancement_access.award_xp(instance, "hero", 900, source="gm")
    advancement_access.consume(instance, "hero", 2)
    instance.players["hero"]["character_sheet"]["ruleset_character"]["build"]["level"] = 2
    instance.players["hero"]["character_sheet"]["ruleset_character"]["build"]["class_levels"][0]["level"] = 2

    assert advancement_access.reconcile_after_level_up(instance, "hero") is True
    advancement_access.require_entitlement(instance, "hero", 3)


def test_ai_rewards_obey_selected_authority_and_mode() -> None:
    instance = _instance()
    advancement_access.configure(instance, "milestone", "gm")
    assert advancement_access.apply_ai_rewards(
        instance, {"milestone_grants": ["all"]},
    ) == []

    advancement_access.configure(instance, "milestone", "ai_gm")
    messages = advancement_access.apply_ai_rewards(
        instance, {"milestone_grants": ["all"]},
    )

    assert len(messages) == 2
    assert all(row["entitled"] for row in advancement_access.view(instance)["players"])
