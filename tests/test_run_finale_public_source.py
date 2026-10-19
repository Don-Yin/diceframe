from types import SimpleNamespace

import pytest

from src.engine.modules import run_finale, skill_growth


def _instance(log):
    return SimpleNamespace(
        players={"p1": {"character_name": "A"}, "p2": {"character_name": "B"}},
        log=log,
    )


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (
            {"actions": [{"user_id": "p1", "text": "打开门", "secret": True}]},
            [{"user_id": "p1", "text": "打开门"}],
        ),
        (
            {"player_actions": [{"user_id": "p1", "text": "检查门"}]},
            [{"user_id": "p1", "text": "检查门"}],
        ),
        (
            {"player_actions": {"p1": "调查脚印", "p2": "守在门口"}},
            [
                {"user_id": "p1", "text": "调查脚印"},
                {"user_id": "p2", "text": "守在门口"},
            ],
        ),
        (
            {
                "actions": [{"user_id": "p1", "text": "重复"}],
                "player_actions": {"p1": "重复", "p2": "另一位行动"},
            },
            [
                {"user_id": "p1", "text": "重复"},
                {"user_id": "p2", "text": "另一位行动"},
            ],
        ),
    ],
)
def test_public_source_supports_new_and_legacy_action_shapes(entry, expected):
    entry = {"round": 1, "gm_response": "公开叙事", **entry}
    assert run_finale.public_source(_instance([entry]))[0]["actions"] == expected


def test_public_source_filters_private_actions_and_metadata():
    instance = _instance(
        [
            {
                "round": 1,
                "gm_response": "公开",
                "actions": [
                    {"user_id": "p1", "text": "公开行动", "metadata": {"secret": True}},
                    {"user_id": "system", "text": "【GM指令】隐藏计划"},
                    {"user_id": "unknown", "text": "不在本局"},
                ],
                "player_actions": {"p1": "公开行动", "p2": "玩家二行动", "system": "公开系统"},
            }
        ]
    )
    assert run_finale.public_source(instance)[0]["actions"] == [
        {"user_id": "p1", "text": "公开行动"},
        {"user_id": "p2", "text": "玩家二行动"},
    ]


def test_public_source_scrubs_legacy_protocol_blocks_and_gm_directives():
    """Old imports may store a raw model response, including protocol suffixes."""

    leaked = (
        "壁炉里的火光晃动。\n"
        "---\n"
        "【状态变更】\n"
        "HP: -2\n"
        '{"state_update": {"gm_plan": "SECRET"}}'
    )
    instance = _instance(
        [
            {"round": 1, "gm_response": leaked},
            {"round": 2, "gm_response": "【GM指令】玩家还不知道真正的出口\n你们沿着河岸前行。"},
        ]
    )

    source = run_finale.public_source(instance)

    assert [entry["round"] for entry in source] == [1, 2]
    assert source[0]["text"] == "壁炉里的火光晃动。"
    assert source[1]["text"] == "你们沿着河岸前行。"
    rendered = str(source)
    assert "SECRET" not in rendered
    assert "GM指令" not in rendered and "状态变更" not in rendered


@pytest.mark.parametrize(
    "text",
    ["你们走进雾里。", "The gate creaks open.", "“快走！”她低声说。\n雨还在下。"],
)
def test_public_source_preserves_normal_narration(text):
    assert run_finale.public_source(
        _instance([{"round": 1, "gm_response": text}]),
    )[0]["text"] == text


def test_public_source_keeps_round_identity_when_narration_is_fully_scrubbed():
    instance = _instance(
        [
            {
                "round": 3,
                "gm_response": "[System Check - Must Follow]\n角色：Alice\n结果：成功",
                "actions": [{"user_id": "p1", "text": "搜索书架"}],
            },
            # Nothing public remains: no invented empty round in the archive.
            {"round": 4, "gm_response": "---\n【状态变更】\nHP: -2"},
        ]
    )

    assert run_finale.public_source(instance) == [
        {"round": 3, "text": "", "actions": [{"user_id": "p1", "text": "搜索书架"}]},
    ]


def test_skill_growth_policy_status_distinguishes_missing_policy():
    missing = SimpleNamespace(growth_system="skill_improvement", template={})
    complete = SimpleNamespace(
        growth_system="skill_improvement",
        template={
            "skill_improvement": {
                "version": 1,
                "success": "above_skill_or_96",
                "gain": "d10",
                "cap": 99,
            }
        },
    )
    unsupported = SimpleNamespace(growth_system="xp_level", template={})
    assert skill_growth.support_status(missing)[0] == "invalid_policy"
    assert skill_growth.support_status(complete) == ("supported", "")
    assert skill_growth.support_status(unsupported) == ("unsupported", "")
    with pytest.raises(ValueError, match="complete version 1 policy"):
        skill_growth.require_supported_policy(missing)
