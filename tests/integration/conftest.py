"""Integration 测试共享 harness：真实 WebAPI -> GameHandler -> GameRegistry 链路。

只有 LLM 是脚本化替身（昂贵外部资源），其余全部真实执行：真实存档目录、
真实 lorebook SQLite、真实回合管线与标签解析。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.integration

from src.lorebook.matcher import KeywordMatcher
from src.lorebook.store import LorebookStore
from src.engine.game_instance import GameRegistry
from src.commands.game_handler import GameHandler
from src.llm.client import LLMResponse
from src.webui.api import WebAPI


class ScriptedLLM:
    """按顺序吐出预置回复的假 LLM，保证 integration 流程可重复。"""

    default = "scripted"

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def call(self, system_prompt: str, user_message: str, **kwargs) -> LLMResponse:
        self.calls.append({"system_prompt": system_prompt, "user_message": user_message})
        if "请用 JSON 分析当前局势" in user_message:
            content = '{"situation":"integration","risks":[]}'
        else:
            content = self.responses.pop(0) if self.responses else "剧情继续。"
        narration = content.split("---", 1)[0].strip() if "---" in content else content
        return LLMResponse(
            content=content,
            narration=narration,
            state_update=None,
            memory_delta=None,
            info_asymmetry=None,
            plot_update=None,
            total_tokens=10,
            is_narration_only=True,
            provider_used="scripted",
        )


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_templates(base: Path) -> tuple[Path, Path, Path]:
    worlds_dir = base / "worlds"
    prompts_dir = base / "prompts"
    rules_dir = base / "rules"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "gm_system_zh.md").write_text("你是 integration 测试 GM。", encoding="utf-8")

    _write_json(rules_dir / "itest_rule.json", {
        "rule_id": "itest_rule",
        "rule_name": "Integration d20 规则",
        "dice_system": "d20",
        "combat_model": "hp_based",
        "mechanics": "freeform_d20_core",
        "attributes": [
            {"key": "str", "name": "力量", "min": 3, "max": 18},
            {"key": "dex", "name": "敏捷", "min": 3, "max": 18},
            {"key": "con", "name": "体质", "min": 3, "max": 18},
        ],
        "attribute_points": 36,
        "attr_hint": "三项属性合计建议 36 点。",
        "hp_formula": "20 + con",
        "classes": [{"name": "冒险者"}],
        "skill_mode": "numeric",
        "skill_hint": "技能建议 20-80。",
        "max_skills": 4,
        "skill_point_total": 160,
        "skill_pools": {"冒险者": ["侦查", "战斗"]},
        "skill_base_values": {"侦查": 25, "战斗": 20},
        "currency": "金币",
        "currency_system": {"base_unit": "gold", "units": [{"id": "gold", "name": "金币", "rate": 1}]},
        "resource_schema": [{"key": "hp", "label": "生命", "min": 0}],
        "identity_schema": [
            {"key": "origin", "label": "出身", "type": "text", "legacy_field": "race"},
            {"key": "archetype", "label": "职业", "type": "text", "legacy_field": "class"},
        ],
        "progression_schema": {"type": "xp_level"},
        "ui_schema": {"primary_resources": ["hp"], "currency_label": "金币"},
        "item_categories": {"key_item": ["钥匙"], "equipment": ["剑"]},
    })
    _write_json(worlds_dir / "itest_world.json", {
        "world_id": "itest_world",
        "world_name": "Integration 世界",
        "description": "用于真实链路集成测试。",
        "world_setting": "一座测试遗迹。",
        "starter_scene": "大厅",
        "default_rule": "itest_rule",
        "starter_lorebook": [],
    })
    _write_json(rules_dir / "itest_coc.json", {
        "rule_id": "itest_coc",
        "rule_name": "Integration d100 规则",
        "dice_system": "d100",
        "combat_model": "hp_based",
        "attributes": [
            {"key": "str", "name": "力量", "min": 15, "max": 90},
            {"key": "dex", "name": "敏捷", "min": 15, "max": 90},
            {"key": "con", "name": "体质", "min": 15, "max": 90},
        ],
        "attribute_points": 150,
        "attr_hint": "d100 属性建议 15-90。",
        "hp_formula": "con // 5",
        "classes": [{"name": "调查员"}],
        "skill_mode": "numeric",
        "skill_hint": "技能建议 20-80。",
        "max_skills": 4,
        "skill_point_total": 160,
        "skill_pools": {"调查员": ["侦查", "聆听"]},
        "skill_base_values": {"侦查": 25, "聆听": 20},
        "currency": "美元",
        "currency_system": {"base_unit": "gold", "units": [{"id": "gold", "name": "美元", "rate": 1}]},
        "resource_schema": [{"key": "hp", "label": "生命", "min": 0}],
        "identity_schema": [
            {"key": "origin", "label": "出身", "type": "text", "legacy_field": "race"},
            {"key": "archetype", "label": "职业", "type": "text", "legacy_field": "class"},
        ],
        "progression_schema": {"type": "xp_level"},
        "ui_schema": {"primary_resources": ["hp"], "currency_label": "美元"},
        "item_categories": {"key_item": ["钥匙"], "equipment": ["手枪"]},
    })
    _write_json(worlds_dir / "itest_world_coc.json", {
        "world_id": "itest_world_coc",
        "world_name": "Integration d100 世界",
        "description": "用于 ruleset 隔离集成测试。",
        "world_setting": "一间深夜图书馆。",
        "starter_scene": "门厅",
        "default_rule": "itest_coc",
        "starter_lorebook": [],
    })
    return worlds_dir, prompts_dir, rules_dir


@pytest.fixture()
def game_env(tmp_path):
    worlds_dir, prompts_dir, rules_dir = _write_templates(tmp_path)
    data_dir = tmp_path / "data"
    registry = GameRegistry(data_dir / "saves")
    lorebook = LorebookStore(data_dir / "lorebook.db")
    lorebook.open()
    llm = ScriptedLLM([])
    handler = GameHandler(
        registry=registry,
        llm_client=llm,
        lorebook_matcher=KeywordMatcher(),
        lorebook_store=lorebook,
        memory_store=None,
        prompts_dir=prompts_dir,
        rules_dir=rules_dir,
        worlds_dir=worlds_dir,
    )
    api = WebAPI(
        registry=registry,
        lorebook=lorebook,
        memory=None,
        rules_dir=rules_dir,
        handler=handler,
        llm_client=llm,
        worlds_dir=worlds_dir,
    )
    env = {
        "api": api,
        "registry": registry,
        "llm": llm,
        "lorebook": lorebook,
        "saves_dir": data_dir / "saves",
        "prompts_dir": prompts_dir,
        "rules_dir": rules_dir,
        "worlds_dir": worlds_dir,
    }
    try:
        yield env
    finally:
        lorebook.close()


@pytest.fixture()
def create_two_player_game(game_env):
    async def _create() -> tuple[str, str, str]:
        """创建双人真实对局，返回 (game_key, gm_uid, player_uid)。"""
        api = game_env["api"]
        created = await api.create_game(
            "itest_world",
            "集成对局",
            solo=False,
            gm_uid="gm_user",
            players=[
                {
                    "character_name": "甲",
                    "race": "人类",
                    "class": "冒险者",
                    "attributes": {"str": 12, "dex": 12, "con": 12},
                    "gold": 30,
                },
                {
                    "character_name": "乙",
                    "race": "人类",
                    "class": "冒险者",
                    "attributes": {"str": 10, "dex": 14, "con": 10},
                    "gold": 30,
                },
            ],
        )
        assert created["ok"] is True
        gm_uid = created["players"][0]["user_id"]
        player_uid = created["players"][1]["user_id"]
        return created["game_key"], gm_uid, player_uid

    return _create
