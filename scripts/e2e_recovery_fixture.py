"""Isolated opt-in CoC tables for the authoritative recovery browser journey."""
import json
from pathlib import Path

from src.engine.game_instance import GameInstance, GameState


E2E_RECOVERY_GAME_KEYS = tuple(
    ("web", f"e2e-{journey}-{viewport}", "web_bot")
    for journey in ("resource-recovery", "rest-notices")
    for viewport in ("desktop", "mobile")
)


def write_recovery_fixtures(data_dir: Path, write_save) -> None:
    rule_id = "e2e_resource_recovery"
    target = data_dir / "templates" / "rules" / f"{rule_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "extends": "freeform_coc", "rule_id": rule_id,
        "rule_name": "E2E Recovery CoC", "resource_recovery": {
            "version": 1, "policy": "coc_light", "luck_recovery": "check",
        },
    }, ensure_ascii=False), encoding="utf-8")
    for game_key in E2E_RECOVERY_GAME_KEYS:
        instance = GameInstance(
            game_key=game_key, rule_id=rule_id, world_id="default_fantasy",
            state=GameState.ACTIVE_ACTION, gm_uid="e2e-gm", language="zh-CN",
        )
        instance.round_number = 2
        instance.set_scene("安全的旅馆")
        for uid, name in (("e2e-gm", "Keeper"), ("e2e-player", "Investigator")):
            instance.put_player(uid, {"user_id": uid, "character_name": name, "character_sheet": {
                "character_name": name, "attributes": {"int": 60, "pow": 60},
                "hp": 12, "max_hp": 12, "sanity": 40, "max_sanity": 90,
                "luck": 50, "max_luck": 99,
                "resources": {"sanity": {"current": 40, "max": 90}, "luck": {"current": 50, "max": 99}},
                "skills": [{"id": "psychoanalysis", "name": "精神分析", "value": 80}],
            }})
        instance.log = [{"round": 1, "actions": [], "gm_response": "调查员回到旅馆，准备安全休息。"}]
        write_save(data_dir, instance)
