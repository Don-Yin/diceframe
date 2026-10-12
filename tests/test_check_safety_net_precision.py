"""Issue #268: the deterministic safety net must not promote bare verbs.

#268 reported that "奥托推动的清林提案" produced a forced Athletics check with
a default DC 15, because the broad planner vocabulary contains the single
character 推.  The deterministic safety net and the planner share one
vocabulary; what the safety net adds is the requirement that the text contains
a *concrete action phrase* (推开 / 撬开 / 搬起 …) describing the acting
character's own current action.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.commands.check_planner import (
    _merge_safety_net_checks,
    _safety_net_action_confirmed,
    _safety_net_action_scope,
)
from src.engine.checks import is_concrete_action_phrase, matched_action_phrases
from src.engine.game_instance import GameInstance
from src.rules.rule_system import RuleSystem

ROOT = Path(__file__).resolve().parents[1]
# #268 复现所用规则集：D&D 2024 SRD（extends intents_base）。
RULE = RuleSystem.load(ROOT / "templates" / "rules" / "dnd2024_srd.json")
NPC_NAMES = {"otto": "奥托", "gren": "格伦", "keeper": "老汤姆"}


def make_instance(
    text: str, *, language: str = "zh-CN", npcs: bool = True,
) -> GameInstance:
    instance = GameInstance(game_key=("web", "room", "bot"), rule_id="dnd2024_srd")
    instance.language = language
    instance.players = {
        "p1": {
            "user_id": "p1",
            "character_name": "阿岚",
            "character_sheet": {
                "attributes": {"str": 14, "dex": 12},
                "skills": [{"name": "运动", "value": 2}, {"name": "潜行", "value": 1}],
            },
        },
        "p2": {
            "user_id": "p2",
            "character_name": "白露",
            "character_sheet": {
                "attributes": {"str": 8, "dex": 16},
                "skills": [{"name": "运动", "value": 0}],
            },
        },
    }
    instance.action_queue = [{"user_id": "p1", "text": text}]
    if npcs:
        for npc_id, name in NPC_NAMES.items():
            instance.npcs[npc_id] = {"name": name}
    return instance


def safety_net_checks(instance: GameInstance, rule: RuleSystem | None = RULE) -> list:
    return _merge_safety_net_checks(instance, rule, [])


# ---- 不触发：抽象表达 / 第三方 / 转述 -----------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        # #268 原始复现：普通移动 + 敲门 + 转述议会消息。
        "我走到柴房门外，轻轻敲门，并告诉格伦：奥托推动的清林提案没有得到支持。",
        "我告诉格伦，奥托推动的清林提案没有得到支持。",
        "我向众人转述议会的决定：推动清林提案。",
        "我向众人说明，拉动经济需要时间。",
        "我举例说明这个法术的原理。",
        "我提醒大家，我们追求的目标是一致的。",
        "我担心冒险会撞上好运。",
        "我解释为什么不能拉动经济。",
        "我描述奥托如何搬起那块石头。",
    ],
)
def test_abstract_or_reported_language_never_forces_a_check(text: str) -> None:
    assert safety_net_checks(make_instance(text)) == []


@pytest.mark.parametrize(
    "text",
    [
        "奥托推开了木门。",
        "格伦已经搬起了那块石头。",
        "老汤姆撬开了箱子。",
        "白露游过了河。",
    ],
)
def test_another_participants_action_never_forces_a_check(text: str) -> None:
    assert safety_net_checks(make_instance(text)) == []


def test_actor_clause_still_triggers_when_another_actor_is_mentioned_later() -> None:
    instance = make_instance("我推开木门，奥托搬起那块石头。")

    planned = safety_net_checks(instance)

    assert len(planned) == 1
    assert planned[0][1]["intent"] == "athletics"


def test_reported_clause_is_not_part_of_the_actor_scope() -> None:
    assert _safety_net_action_scope("我敲门并告诉格伦：奥托推开门") == "我敲门并告诉格伦"
    assert _safety_net_action_scope('我大喊"推开"') == "我大喊"


# ---- 应触发：具体身体动作 ------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("我推开木门。", "athletics"),
        ("我撞开生锈的铁门。", "athletics"),
        ("我撬开箱子。", "athletics"),
        ("我搬起那块石头。", "athletics"),
        ("我攀爬城墙。", "athletics"),
        ("我游过河流。", "athletics"),
        ("我翻越矮墙。", "athletics"),
        ("我潜行绕过守卫。", "stealth"),
        ("我攻击地精。", "combat"),
    ],
)
def test_concrete_physical_actions_still_get_a_safety_net(text: str, intent: str) -> None:
    planned = safety_net_checks(make_instance(text))

    assert len(planned) == 1
    request = planned[0][1]
    assert request["intent"] == intent
    assert request["planner_source"] == "deterministic_safety_net"


def test_safety_net_confirmation_is_the_shared_authority() -> None:
    """安全网判定可以直接按 (instance, uid, text, rule, intent) 复算。"""

    instance = make_instance("我推开木门。")
    assert _safety_net_action_confirmed(instance, "p1", "我推开木门。", RULE, "athletics")
    assert not _safety_net_action_confirmed(
        instance, "p1", "奥托推开木门。", RULE, "athletics",
    )


# ---- 英文 / 日文主路径 ---------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "I pry open the crate.",
        "I swim across the river.",
        "I force open the door.",
        "I squeeze through the gap.",
        "I attack the goblin.",
    ],
)
def test_english_concrete_phrases_still_get_a_safety_net(text: str) -> None:
    planned = safety_net_checks(make_instance(text, language="en"))

    assert len(planned) == 1
    assert planned[0][1]["planner_source"] == "deterministic_safety_net"


@pytest.mark.parametrize(
    "text",
    [
        "I tell Gren that Otto pushed the proposal forward.",
        "I explain that lifting the mood takes time.",
    ],
)
def test_english_single_verb_metaphors_do_not_force_a_check(text: str) -> None:
    assert safety_net_checks(make_instance(text, language="en")) == []


def test_japanese_concrete_phrases_still_get_a_safety_net() -> None:
    planned = safety_net_checks(make_instance("私は壁をよじ登る。", language="ja"))

    assert len(planned) == 1
    assert planned[0][1]["planner_source"] == "deterministic_safety_net"


# ---- 词表判定本身 --------------------------------------------------------------


@pytest.mark.parametrize("alias", ["推开", "撬开", "搬起", "攀爬", "游泳", "pry open"])
def test_concrete_action_phrases_pass_the_filter(alias: str) -> None:
    word_match = " " in alias
    assert is_concrete_action_phrase(alias, word_match=word_match) is True


@pytest.mark.parametrize("alias", ["推", "拉", "举", "撞", "爬", "游", "climb", "push"])
def test_single_verbs_are_not_concrete_phrases(alias: str) -> None:
    word_match = alias.isascii()
    assert is_concrete_action_phrase(alias, word_match=word_match) is False


def test_matched_action_phrases_ignores_bare_verbs_but_keeps_compounds() -> None:
    assert matched_action_phrases(RULE, "athletics", "推动清林提案", "zh-CN") == ()
    assert "推开" in matched_action_phrases(RULE, "athletics", "我推开木门", "zh-CN")


def test_fallback_vocabulary_without_a_rule_behaves_the_same() -> None:
    """没有自带 intents 的规则沿用兜底词表，判定方式必须一致。"""

    instance = make_instance("我推开木门。")

    assert safety_net_checks(instance, None) != []
    assert safety_net_checks(make_instance("推动清林提案"), None) == []
