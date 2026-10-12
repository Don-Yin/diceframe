"""多人同时提交行动的 Golden Path。"""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_concurrent_actions_keep_actor_and_round_isolated(
    game_env,
    create_two_player_game,
):
    game_key, gm_uid, player_uid = await create_two_player_game()
    api = game_env["api"]
    instance = game_env["registry"].get(api._parse_key(game_key))
    initial_log_count = len(instance.log)
    game_env["llm"].responses.append("两人的行动同时生效。")

    results = await asyncio.gather(
        api.submit_action(game_key, gm_uid, "甲守住北门", selected_attribute="str"),
        api.submit_action(game_key, player_uid, "乙检查南窗", selected_attribute="dex"),
    )

    assert sum(result["payload"].get("advanced") is True for result in results) == 1
    assert instance.round_number == 2
    assert len(instance.log) == initial_log_count + 1
    actions = instance.log[-1]["actions"]
    assert {(action["user_id"], action["text"]) for action in actions} == {
        (gm_uid, "甲守住北门"),
        (player_uid, "乙检查南窗"),
    }
    assert instance.action_queue == []
    assert instance.ready_players == set()
