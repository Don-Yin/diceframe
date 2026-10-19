"""Narrative HP changes must agree with the rules used by rest and combat."""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.commands.state_update_applier import StateUpdateApplier
from src.commands.round_effects import apply_revive_commands
from src.rulesets.dnd2024.runtime import Dnd2024Runtime
from src.rulesets.dnd2024.resting.engine import Dnd2024RestEngine
from tests.rulesets.test_dnd2024_combat import _instance, _start, SequenceRng


def applier(runtime):
    rules = Path(__file__).resolve().parents[2] / "templates/rules"
    return StateUpdateApplier(
        rules, None, lambda *_: {"default_rule": "dnd2024_srd"},
        ruleset_registry=SimpleNamespace(resolve=lambda _: runtime),
    )


@pytest.mark.parametrize("dead", [False, True])
def test_narrative_healing_after_combat_updates_authority_or_explains_resurrection(dead):
    engine, instance = _instance()
    runtime = Dnd2024Runtime()
    _start(engine, instance)
    ended = engine.resolve_intent(instance, {"intent_id": "gm-leaves-combat", "type": "combat.end", "expected_version": 1, "submitted_by": "gm"}, SequenceRng([]))
    engine.apply_batch(instance, ended["event_batch"])
    sheet = instance.get_character_sheet("gm")
    sheet["hp"] = 0
    sheet["deceased"] = dead
    sheet["status"] = "dead" if dead else "downed"
    canonical = sheet["ruleset_character"]
    canonical["resources"]["hp"] = 0
    canonical["conditions"] = {"unconscious": {}, "death_saves": {"successes": 0, "failures": 3 if dead else 1}}
    if dead:
        canonical["conditions"]["dead"] = {}
    update = {"players": {"gm": {"hp_change": 5}}}
    applier(runtime).apply_state_update(instance, update)
    healed = instance.get_character_sheet("gm")
    assert healed["hp"] == healed["ruleset_character"]["resources"]["hp"] == (0 if dead else 5)
    if dead:
        assert healed["deceased"] is True
        assert not update["players"]["gm"].get("hp_change")
        apply_revive_commands(instance, {"revive_commands": [{"uid": "gm", "method": "法术"}]}, runtime)
        healed = instance.get_character_sheet("gm")
        assert "dead" not in healed["ruleset_character"]["conditions"]
    else:
        assert "unconscious" not in healed["ruleset_character"]["conditions"]
    rested = Dnd2024RestEngine(runtime.load_bundle("en")).complete_long_rest(healed["ruleset_character"])
    assert rested["character"]["resources"]["hp"] > 0
    from src.engine.game_instance import GameInstance
    restored = GameInstance.from_dict(instance.to_dict())
    assert restored.get_character_sheet("gm")["ruleset_character"]["resources"]["hp"] == healed["hp"]


def test_future_health_slot_rejects_before_any_player_write():
    from src.engine.module_state import ModuleStateError
    _, instance = _instance()
    instance.modules["ruleset_runtime"] = {"schema_version": 99, "opaque": [1]}
    before = deepcopy(instance.to_dict())
    with pytest.raises(ModuleStateError):
        applier(Dnd2024Runtime()).apply_state_update(instance, {"players": {"gm": {"hp_change": 5}}})
    assert instance.to_dict() == before


def test_narrative_hp_tags_cannot_duplicate_active_combat_settlement():
    engine, instance = _instance()
    _start(engine, instance)
    before = instance.get_character_sheet("gm")["ruleset_character"]["resources"]["hp"]
    applier(Dnd2024Runtime()).apply_state_update(instance, {"players": {"gm": {"hp_change": -3}}})
    sheet = instance.get_character_sheet("gm")
    assert sheet["hp"] == sheet["ruleset_character"]["resources"]["hp"] == before


def test_health_settlement_preserves_live_inventory_and_currency():
    _, instance = _instance()
    sheet = instance.get_character_sheet("gm")
    sheet["hp"] = 2
    sheet["ruleset_character"]["resources"]["hp"] = 2
    sheet["inventory"] = [{"name": "Gift", "qty": 1}]
    sheet["gold"] = 321
    sheet["currency"] = {"amount": 321}
    applier(Dnd2024Runtime()).apply_state_update(instance, {"players": {"gm": {"hp_change": 3}}})
    updated = instance.get_character_sheet("gm")
    assert updated["inventory"] == [{"name": "Gift", "qty": 1}]
    assert updated["currency"]["amount"] == updated["gold"] == 321
