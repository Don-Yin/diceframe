
from legacy_save_fixtures import legacy_table_payload
from src.engine.modules import checks, ruleset_runtime
"""Player requests never become mechanical grants; persisted GM decisions do."""
from copy import deepcopy
from pathlib import Path

import pytest

from src.engine.checks import build_check_request
from src.engine.game_instance import GameInstance
from src.engine.game_state import GameState
from src.engine.participant_view import Viewer
from src.rules.rule_system import RuleSystem
from src.rulesets import build_default_ruleset_registry

ROOT = Path(__file__).resolve().parents[1]


def game():
    inst = GameInstance(game_key=("web", "modes", "bot"))
    inst.state = GameState.ACTIVE_ACTION
    inst.gm_uid = "gm"
    inst.players = {uid: {"character_name": uid, "character_sheet": {
        "attributes": {"str": 12}, "skills": [], "deceased": False,
    }} for uid in ("a", "b")}
    return inst


def test_player_text_and_payload_cannot_grant_mode():
    from src.commands.dice_resolver import DiceResolver

    rule = RuleSystem.load(ROOT / "templates/rules/dnd5e.json")
    inst = game()
    action = {"user_id": "a", "text": "以优势攻击守卫", "advantage_mode": "advantage"}
    request = build_check_request(inst, action, rule)
    assert request is not None
    assert request["advantage_mode"] == ""
    assert DiceResolver._legacy_request(inst, action, rule)["advantage_mode"] == ""


def service(inst, save=None):
    from src.webui.services.check_modes import CheckModeDependencies, CheckModeService

    async def persist(_):
        return None

    rule = RuleSystem.load(ROOT / "templates/rules/dnd5e.json")
    return CheckModeService(CheckModeDependencies(
        get_instance=lambda _: inst, save_instance=save or persist,
        load_rule=lambda _: rule, rulesets=build_default_ruleset_registry(),
    ))


def body(view, **fields):
    return {"expected_revision": view["revision"], "context_id": view["seats"][0]["context_id"],
            "run_id": view["run_id"], **fields}


@pytest.mark.asyncio
async def test_request_grant_cancel_clear_and_round_expiry():
    from src.engine.modules.check_modes import apply_grant

    inst = game()
    app = service(inst)
    player = Viewer("seat", "a")
    view = app.read("g", player)
    assert len(view["seats"]) == 1
    requested = await app.update("g", player, "a", "request", body(view, mode="advantage", reason="high ground"))
    assert requested["ok"]
    request = {"actor_uid": "a", "advantage_mode": "", "advantage_note": None}
    apply_grant(inst, request, f"round:{inst.round_number}")
    assert request["advantage_mode"] == ""
    granted = await app.update("g", Viewer("gm", "gm"), "a", "grant", body(requested, mode="advantage", reason="GM approves"))
    assert granted["ok"]
    apply_grant(inst, request, f"round:{inst.round_number}")
    assert request["advantage_mode"] == "advantage"
    opposing = {"actor_uid": "a", "advantage_mode": "disadvantage"}
    apply_grant(inst, opposing, f"round:{inst.round_number}")
    assert opposing["advantage_mode"] == ""
    assert "GM approves" in opposing["advantage_note"]
    restored = GameInstance.from_dict(inst.to_dict())
    assert restored.modules["check_modes"] == inst.modules["check_modes"]
    inst.round_number += 1
    fresh_request = {"actor_uid": "a", "advantage_mode": ""}
    apply_grant(inst, fresh_request, f"round:{inst.round_number}")
    assert fresh_request["advantage_mode"] == ""
    assert app.read("g", player)["seats"][0]["grant"] is None


@pytest.mark.asyncio
async def test_actor_permission_stale_context_and_save_rollback():
    inst = game()
    app = service(inst)
    view = app.read("g", Viewer("seat", "a"))
    data = body(view, mode="advantage", reason="reason")
    for viewer, uid, operation in ((Viewer("seat", "a"), "b", "request"),
                                   (Viewer("seat", "a"), "a", "grant"),
                                   (Viewer("outsider", "a"), "a", "request")):
        assert not (await app.update("g", viewer, uid, operation, data))["ok"]
    assert not app.read("g", Viewer("outsider"))["ok"]
    assert (await app.update("g", Viewer("seat", "a"), "a", "request", data))["ok"]
    assert not (await app.update("g", Viewer("seat", "a"), "a", "request", data))["ok"]
    current = app.read("g", Viewer("seat", "a"))
    inst.round_number += 1
    assert not (await app.update("g", Viewer("gm"), "a", "grant", body(current, mode="advantage", reason="yes")))["ok"]
    before = deepcopy(inst.to_dict())

    async def fail(_):
        raise OSError("disk")

    broken = service(inst, fail)
    current = broken.read("g", Viewer("seat", "a"))
    with pytest.raises(OSError):
        await broken.update("g", Viewer("gm"), "a", "grant", body(current, mode="advantage", reason="yes"))
    assert inst.to_dict() == before


@pytest.mark.asyncio
async def test_unknown_schema_and_prepared_checks_fail_closed():
    inst = game()
    app = service(inst)
    view = app.read("g", Viewer("seat", "a"))
    checks.replace_round_checks_prepared(inst, True)
    assert not (await app.update("g", Viewer("gm"), "a", "grant", body(view, mode="advantage", reason="yes")))["ok"]
    inst.modules["check_modes"] = {"schema_version": 99, "future": "keep"}
    assert not app.read("g", Viewer("gm"))["ok"]
    assert inst.to_dict()["modules"]["check_modes"]["future"] == "keep"


@pytest.mark.asyncio
async def test_rejection_clear_removal_and_restart():
    inst = game()
    app = service(inst)
    viewer = Viewer("gm")
    view = app.read("g", viewer)
    view = await app.update("g", viewer, "a", "grant", body(view, mode="disadvantage", reason="fog"))
    assert view["ok"]
    view = await app.update("g", viewer, "a", "clear", body(view))
    assert view["ok"] and view["seats"][0]["grant"] is None
    view = await app.update("g", Viewer("seat", "a"), "a", "request", body(view, mode="advantage", reason="help"))
    view = await app.update("g", viewer, "a", "reject", body(view, reason="not applicable"))
    assert view["seats"][0]["request"]["status"] == "rejected"
    await inst.remove_player("a")
    assert "a" not in inst.modules["check_modes"]["seats"]
    await inst.reset()
    assert not inst.modules["check_modes"]["seats"]


def test_professional_preview_matches_roll_sources_and_expires_after_intent():
    from src.engine.modules.check_modes import change
    from tests.test_ai_player_combat import _setup, _start, _set_turn, SequenceRng

    runtime, engine, inst = _setup()
    _start(engine, inst, rolls=[18, 10, 1], enemy_hp=200)
    _set_turn(engine, inst, "player:ai1")
    ruleset_runtime.state(inst)["combat"]["enemies"]["goblin-1"]["conditions"]["dodging"] = {}
    policy = runtime.check_mode_policy(inst, None, "ai1")
    assert policy["previews"]
    preview = policy["previews"][0]
    assert preview["mode"] == "disadvantage"
    assert any(source["code"] == "dodging" for source in preview["sources"])
    change(inst, "ai1", "grant", policy["context_id"], mode="advantage", reason="GM high ground")
    policy = runtime.check_mode_policy(inst, None, "ai1")
    preview = next(p for p in policy["previews"] if p["weapon_ref"] == preview["weapon_ref"])
    assert preview["mode"] == ""
    intent = {"intent_id": "approved-attack", "submitted_by": "gm", "actor_id": "player:ai1",
              "type": "attack", "expected_version": ruleset_runtime.state(inst)["version"],
              "target_id": preview["target_id"], "weapon_ref": preview["weapon_ref"]}
    assert engine.validate_intent(inst, intent)["ok"]
    batch = engine.resolve_intent(inst, intent, SequenceRng([10, 4]))["event_batch"]
    check = next(e for e in batch["events"] if e["type"] == "check.resolved")
    assert check["rolls"] == [10]
    assert check["advantage_mode"] == preview["mode"]
    assert check["advantage_sources"] == preview["sources"]
    engine.apply_batch(inst, batch)
    assert runtime.check_mode_policy(inst, None, "ai1")["context_id"] != policy["context_id"]
    projected = runtime.gameplay_view(inst, "ai1")["recent_combat_events"]
    projected_check = next(e for e in projected if e["type"] == "check.resolved")
    assert projected_check["advantage_sources"] == preview["sources"]
    assert projected_check["rolls"] == [10]


def test_assistance_and_gm_grant_cannot_uncancel_an_automatic_penalty():
    from src.commands.check_planner import _apply_d20_assistance, _apply_granted_advantage_modes
    from src.engine.modules.check_modes import change

    inst = game()
    inst.action_queue = [{"user_id": "a", "text": "我攀爬"}, {"user_id": "b", "text": "我协助a攀爬"}]
    rule = RuleSystem.load(ROOT / "templates/rules/dnd5e.json")
    planned = [(inst.action_queue[0], {"actor_uid": "a", "advantage_mode": "disadvantage"})]
    change(inst, "a", "grant", "round:0", mode="advantage", reason="help")
    planned = _apply_d20_assistance(inst, rule, planned)
    assert planned[0][1]["advantage_mode"] == ""
    _apply_granted_advantage_modes(inst, rule, planned)
    assert planned[0][1]["advantage_mode"] == ""


def test_spell_attack_uses_same_grant_preview_and_two_dice():
    from src.engine.modules.check_modes import change
    from tests.test_ai_player_combat import _setup, _start, _set_turn, SequenceRng

    runtime, engine, inst = _setup(ai_preset="kindly_bulwark")
    _start(engine, inst, rolls=[18, 10, 1], enemy_hp=200)
    _set_turn(engine, inst, "player:ai1")
    policy = runtime.check_mode_policy(inst, None, "ai1")
    change(inst, "ai1", "grant", policy["context_id"], mode="advantage", reason="GM spell attack")
    ruleset_runtime.state(inst)["combat"]["enemies"]["goblin-1"]["conditions"]["next_attack_advantage"] = {}
    spell = next(p for p in runtime.check_mode_policy(inst, None, "ai1")["previews"] if p.get("spell_ref"))
    assert spell["mode"] == "advantage"
    intent = {"intent_id": "approved-spell", "submitted_by": "gm", "actor_id": "player:ai1",
              "type": "cast_spell", "expected_version": ruleset_runtime.state(inst)["version"],
              "target_ids": [spell["target_id"]], "spell_ref": spell["spell_ref"], "slot_level": 1}
    assert engine.validate_intent(inst, intent)["ok"]
    result = engine.resolve_intent(inst, intent, SequenceRng([4, 17, 4, 4, 4, 4]))
    check = next(e for e in result["event_batch"]["events"] if e["type"] == "check.resolved")
    assert check["rolls"] == [4, 17] and check["natural"] == 17
    assert check["advantage_sources"] == spell["sources"]
    events = result["event_batch"]["events"]
    assert any(e["type"] == "condition.removed" and e.get("condition") == "next_attack_advantage" for e in events)


def test_v36_migration_preserves_completed_checks_and_unknown_mode_schema():
    from src.migrations.instance import migrate_game_state_payload

    payload = game().to_dict()
    payload = legacy_table_payload(payload)
    payload["instance_schema_version"] = 36
    payload["modules"].pop("check_modes")
    completed = {"check_id": "old", "advantage_mode": "advantage", "rolls": [3, 17], "roll": 17}
    payload["modules"]["checks"]["last_checks"] = [completed]
    migrated = migrate_game_state_payload(payload)
    from src.migrations.instance import CURRENT_INSTANCE_SCHEMA_VERSION
    assert migrated["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert migrated["modules"]["checks"]["last_checks"] == [completed]
    assert not migrated["modules"]["check_modes"]["seats"]
    assert migrate_game_state_payload(migrated) == migrated
    payload["modules"]["check_modes"] = {"schema_version": 99, "future": [1, 2]}
    assert migrate_game_state_payload(payload)["modules"]["check_modes"] == payload["modules"]["check_modes"]
