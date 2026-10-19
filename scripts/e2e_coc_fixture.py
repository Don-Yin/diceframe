"""Real percentile result fixtures for the temporary browser-test table."""
from pathlib import Path
from copy import deepcopy

from src.engine.checks import resolve_check_request
from src.engine.game_instance import GameInstance, GameState
from src.engine.modules import checks, check_presentation
from src.rules.rule_system import RuleSystem


E2E_COC_GAME_KEYS = {
    (fixture, viewport): ("web", f"e2e-{fixture}-{viewport}", "web_bot")
    for viewport in ("desktop", "mobile")
    for fixture in ("coc", "dice-tray", "dice-tray-feedback", "check-mode", "push", "preferences-push")
}


def write_coc_fixture(data_dir: Path, write_save) -> None:
    for viewport in ("desktop", "mobile"):
        _write_coc_fixture(data_dir, write_save, viewport)


def _write_coc_fixture(data_dir: Path, write_save, viewport: str) -> None:
    rule = RuleSystem.load(Path(__file__).resolve().parents[1] / "templates/rules/freeform_coc.json")
    inst = GameInstance(game_key=E2E_COC_GAME_KEYS["coc", viewport], state=GameState.ACTIVE_ACTION,
                        rule_id="freeform_coc", world_id="default_fantasy", gm_uid="e2e-gm", language="zh-CN")
    inst.round_number = 2
    check_presentation.replace_dice_reveal_mode(inst, "click")
    for uid, name in (("e2e-gm", "Keeper"), ("e2e-player", "Investigator")):
        inst.put_player(uid, {"user_id": uid, "character_name": name,
                             "character_sheet": {"attributes": {"int": 60}, "skills": [{"name": "侦查", "value": 60}],
                                                 "hp": 12, "max_hp": 12, "luck": 50}})
    results = []
    for mode, chosen in (("advantage", 30), ("disadvantage", 100)):
        results.append(resolve_check_request(inst, {
            "user_id": "e2e-player", "text": "搜索书房", "dice_value": chosen, "dice_rolls": [100, 30],
            "check_request": {"check_id": f"coc-{mode}", "dice_system": "d100", "skill": "侦查", "advantage_mode": mode},
        }, rule))
    checks.replace_last_checks(inst, results)
    checks.replace_last_check(inst, results[-1])
    inst.log = [{"round": 1, "actions": [{"user_id": uid, "text": "搜索书房"} for uid in inst.players],
                 "gm_response": "调查员在书房寻找线索。", "check_results": results, "state_changes": [], "swipes": []}]
    write_save(data_dir, inst)
    # Each reveal suite gets its own mutable reveal records; an earlier suite
    # must not reveal the result that a later one expects to be sealed.
    for fixture in ("dice-tray", "dice-tray-feedback"):
        presentation = deepcopy(inst)
        presentation.game_key = E2E_COC_GAME_KEYS[fixture, viewport]
        write_save(data_dir, presentation)
    modes = GameInstance(game_key=E2E_COC_GAME_KEYS["check-mode", viewport], state=GameState.ACTIVE_ACTION,
                         rule_id="freeform_coc", world_id="default_fantasy", gm_uid="e2e-gm", language="zh-CN")
    modes.players = inst.players
    modes.round_number = 2
    write_save(data_dir, modes)
    from src.engine import check_decisions

    pushes = GameInstance(game_key=E2E_COC_GAME_KEYS["push", viewport], state=GameState.ACTIVE_JUDGMENT,
                          rule_id="freeform_coc", world_id="default_fantasy", gm_uid="e2e-gm", language="zh-CN")
    pushes.players = deepcopy(inst.players)
    pushes.round_number = 2
    check_presentation.replace_dice_reveal_mode(pushes, "auto")
    checks.replace_last_checks(pushes, [resolve_check_request(pushes, {'user_id': uid, 'text': '搜索书房', 'dice_value': 80, 'dice_rolls': [80], 'check_request': {'check_id': f'push-{uid}', 'dice_system': 'd100', 'skill': '侦查', 'kind': 'check'}}, rule) for uid in pushes.players])
    for check in checks.last_checks(pushes):
        check["luck_decision"] = "pending"
    checks.replace_last_check(pushes, checks.last_checks(pushes)[-1])
    check_decisions.prepare(pushes, rule)
    pushes.complete_round_check_preparation()
    write_save(data_dir, pushes)
    # Disabling Push resolves pending decisions permanently. Preference tests
    # must not consume the decisions exercised by the player/Keeper journey.
    preferences = deepcopy(pushes)
    preferences.game_key = E2E_COC_GAME_KEYS["preferences-push", viewport]
    write_save(data_dir, preferences)
