"""WebUI 测试共享 harness：真实 WebAPI + GameHandler + 临时目录，仅 LLM 为替身。

自原 tests/test_webui_create_flow.py 拆分而来，供拆分后的各领域测试文件复用。
"""

from __future__ import annotations

import json

import pytest

from src.commands.game_handler import GameHandler
from src.engine.game_instance import GameRegistry
from src.llm.client import LLMResponse
from src.lorebook.matcher import KeywordMatcher
from src.lorebook.store import LorebookStore
from src.webui.api import WebAPI


class FakeLLMClient:
    default = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def call(self, system_prompt: str, user_message: str, **kwargs) -> LLMResponse:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_message": user_message,
            "kwargs": kwargs,
        })
        if "TRPG规则设计师" in system_prompt:
            return LLMResponse(
                content=json.dumps({
                    "rule_name": "凡人修仙轻量规则",
                    "rule_name_en": "Mortal Cultivation Lite",
                    "description": "低资质散修成长的轻量规则。",
                    "dice_system": "d20",
                    "combat_model": "hp_based",
                    "mechanics": "xianxia_lite",
                    "ruleset_level": "assisted",
                    "attributes": [
                        {"key": "body", "name": "体魄", "min": 3, "max": 18},
                        {"key": "sense", "name": "神识", "min": 3, "max": 18},
                        {"key": "will", "name": "心性", "min": 3, "max": 18},
                    ],
                    "special_stats": [{"key": "qi", "name": "灵力", "max": 100}],
                    "attribute_points": 36,
                    "attr_hint": "凡人修仙属性偏低开局，资源比天赋更重要。",
                    "hp_formula": "5 + body * 3",
                    "max_skills": 4,
                    "skill_point_total": 180,
                    "max_skill_value": 80,
                    "skill_mode": "narrative",
                    "skill_hint": "技能填写功法、法术、炼丹、制符等。",
                    "currency": "灵石",
                    "classes": [{"name": "散修", "description": "无宗门依靠的低阶修士", "starter_equipment": ["粗劣飞剑"]}],
                    "skill_pools": {"散修": ["基础吐纳", "御器", "符箓", "遁术"]},
                    "item_categories": {"equipment": ["飞剑"], "consumable": ["丹药"], "misc": ["玉简"]},
                    "gm_prompt_appendix": "保持凡人修仙味：谨慎、资源稀缺、机缘有代价。",
                    "difficulty_instructions": {"轻松": "机缘稍多", "标准": "资源紧张", "硬核": "强敌环伺"},
                }, ensure_ascii=False),
                narration="",
                state_update=None,
                memory_delta=None,
                info_asymmetry=None,
                plot_update=None,
                total_tokens=20,
                is_narration_only=True,
                provider_used="fake",
            )
        return LLMResponse(
            content="艾琳站在试炼大厅中央，新的冒险开始了。",
            narration="艾琳站在试炼大厅中央，新的冒险开始了。",
            state_update=None,
            memory_delta=None,
            info_asymmetry=None,
            plot_update=None,
            total_tokens=12,
            is_narration_only=True,
            provider_used="fake",
        )


def write_world(
    worlds_dir,
    world_id: str,
    *,
    starter_lorebook: list[dict] | None = None,
    default_rule: str = "freeform_fantasy",
) -> None:
    worlds_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "world_id": world_id,
        "world_name": world_id,
        "description": f"{world_id} description",
        "world_setting": f"{world_id} setting",
        "starter_scene": "试炼大厅",
        "default_rule": default_rule,
        "starter_lorebook": starter_lorebook or [],
    }
    (worlds_dir / f"{world_id}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@pytest.fixture()
def web_api(tmp_path):
    data_dir = tmp_path / "data"
    worlds_dir = tmp_path / "worlds"
    prompts_dir = tmp_path / "prompts"
    rules_dir = tmp_path / "rules"
    prompts_dir.mkdir()
    rules_dir.mkdir()
    (prompts_dir / "gm_system_zh.md").write_text("你是测试 GM。", encoding="utf-8")
    (rules_dir / "freeform_fantasy.json").write_text(
        json.dumps({
            "rule_id": "freeform_fantasy",
            "rule_name": "自由幻想",
            "dice_system": "d20",
            "combat_model": "hp_based",
            "attributes": [{"key": "str", "name": "力量", "min": 3, "max": 18}],
            "attribute_points": 60,
            "attr_hint": "属性测试提示",
            "hp_formula": "20 + str",
            "max_skills": 3,
            "skill_mode": "narrative",
            "skill_hint": "技能测试提示",
            "skill_pools": {"游侠": ["侦查", "射击"]},
            "skills": [],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    write_world(
        worlds_dir,
        "template_world",
        starter_lorebook=[{
            "id": "template_npc",
            "world_id": "template_world",
            "name": "模板导师",
            "type": "npc",
            "keywords": ["导师"],
            "content": "模板自带角色",
            "tier": "core",
        }],
    )

    registry = GameRegistry(data_dir / "saves")
    lorebook = LorebookStore(data_dir / "lorebook.db")
    lorebook.open()
    fake_llm = FakeLLMClient()
    handler = GameHandler(
        registry=registry,
        llm_client=fake_llm,
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
        llm_client=fake_llm,
        worlds_dir=worlds_dir,
    )
    try:
        yield api, lorebook, registry, fake_llm, worlds_dir
    finally:
        lorebook.close()
