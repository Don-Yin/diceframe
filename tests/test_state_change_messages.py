"""回合状态变动播报测试。"""

from __future__ import annotations

from src.commands.game_handler import (
    _build_state_change_messages,
    _snapshot_public_player_state,
)
from src.engine.game_instance import GameInstance


def test_state_change_messages_include_hp_loot_and_quests():
    instance = GameInstance(("web", "group", "bot"))
    instance.players["web_user"] = {
        "character_name": "艾琳",
        "character_sheet": {
            "hp": 46,
            "max_hp": 46,
            "gold": 30,
            "inventory": [],
            "equipment": [],
            "key_items": [],
        },
    }
    before = _snapshot_public_player_state(instance)

    cs = instance.players["web_user"]["character_sheet"]
    cs["hp"] = 44
    cs["inventory"].append({"name": "老格雷的细磨刀石", "qty": 1})

    data = {
        "state_update": {
            "players": {"web_user": {"hp_change": -2}},
            "loot": [{"player": "web_user", "item": "老格雷的细磨刀石"}],
        },
        "plot_update": {
            "quests": [
                {"title": "完成训练场等级评价", "status": "completed"},
                {"title": "选择第一个冒险任务", "status": "active"},
            ],
        },
    }

    messages = _build_state_change_messages(instance, before, data)

    # 契约：HP 变化、获得物品、任务状态都进入播报；具体措辞/格式不锁。
    joined = "\n".join(messages)
    assert "艾琳" in joined
    assert "HP" in joined and "44" in joined
    assert "老格雷的细磨刀石" in joined
    assert "完成训练场等级评价" in joined
    assert "选择第一个冒险任务" in joined
