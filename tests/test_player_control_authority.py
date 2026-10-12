"""Player control authority (AI teammate plan, PR2).

PR1 made *who plays a seat* an explicit persisted record.  This file locks down
the part that makes that record authoritative for behaviour:

* a human-initiated action is refused on an ``ai`` or ``unclaimed`` seat, and an
  unknown seat is still rejected by the roster check, not by the control gate;
* the multiplayer ready barrier counts human-controlled seats only, so AI-hosted
  and unclaimed seats never block a round, while a second human still does and an
  away human still does not;
* ``multiplayer_status`` keeps every pre-existing key and reports the non-human
  seats explicitly instead of hiding them in ``waiting_players``;
* claiming a seat (``ai`` / ``unclaimed`` -> ``human``) is lossless: the
  character record, its sheet and the authoritative world facts do not move;
* the claim and safe-boundary entry points fail closed on stale revisions, on an
  already-human seat, and while a round is in flight.

The tests drive the real ``turns.submit_action`` service for the submission gate
so the ordering (roster check -> control gate) is verified end to end.
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any

import pytest

from src.engine.game_instance import GameInstance, GameState
from src.engine.player_control import (
    SUBMISSION_BLOCK_CODES,
    PlayerControlError,
    claim_seat,
    control_change_block,
    control_mode,
    get_control,
    set_control,
    submission_block,
)
from src.engine.world_legality import actor_location_fact_key
from src.engine.world_state import apply_world_ops, fact_value
from src.rulesets.registry import RulesetRuntimeRegistry
from src.webui.services.turns import TurnDependencies, submit_action

from webapi_harness import web_api  # noqa: F401  （pytest fixture）


def make_instance(*, uids: tuple[str, ...] = ("h1", "h2")) -> GameInstance:
    instance = GameInstance(game_key=("web", "player-control", "bot"), rule_id="test")
    instance.state = GameState.ACTIVE_ACTION
    instance.round_number = 1
    for uid in uids:
        # 走真实席位写入路径：控制记录由聚合保证存在，不靠测试手工补。
        instance.put_player(uid, {
            "user_id": uid,
            "character_name": f"角色{uid}",
            "character_sheet": {"hp": 10, "max_hp": 10},
        })
    return instance


# ---- 提交权限 ---------------------------------------------------------------


def test_submission_block_codes_are_closed() -> None:
    assert SUBMISSION_BLOCK_CODES == ("PLAYER_AI_CONTROLLED", "PLAYER_UNCLAIMED")


def test_submission_block_follows_the_seat_controller() -> None:
    instance = make_instance(uids=("h1", "a1", "u1"))
    set_control(instance, "a1", "ai")
    set_control(instance, "u1", "unclaimed")

    assert submission_block(instance, "h1") == ""
    assert submission_block(instance, "a1") == "PLAYER_AI_CONTROLLED"
    assert submission_block(instance, "u1") == "PLAYER_UNCLAIMED"

    # 未知席位交给调用点已有的名册检查，不在这里发明第二种"不是玩家"错误。
    assert submission_block(instance, "ghost") == ""

    # 读路径是纯读取：判定不改变任何控制记录。
    assert control_mode(instance, "a1") == "ai"
    assert control_mode(instance, "u1") == "unclaimed"


def test_submission_block_treats_corrupt_control_as_human() -> None:
    instance = make_instance(uids=("p1",))
    instance.players["p1"]["control"] = {"mode": "script", "revision": -3}

    # 损坏记录降级为 human（契约前行为），不会凭空变成一个 AI 席位。
    assert submission_block(instance, "p1") == ""


# ---- ready barrier ----------------------------------------------------------


def test_active_human_players_excludes_ai_unclaimed_and_away() -> None:
    instance = make_instance(uids=("h1", "h2", "a1", "u1"))
    set_control(instance, "a1", "ai")
    set_control(instance, "u1", "unclaimed")

    assert instance.active_human_players == {"h1", "h2"}
    # active_alive_players 语义不变：它在场的非真人也算。
    assert instance.active_alive_players == {"h1", "h2", "a1", "u1"}

    instance.away_players.add("h2")
    assert instance.active_human_players == {"h1"}


def test_ai_and_unclaimed_seats_never_block_the_ready_barrier() -> None:
    instance = make_instance(uids=("h1", "h2", "a1", "a2", "u1"))
    set_control(instance, "a1", "ai")
    set_control(instance, "a2", "ai")
    set_control(instance, "u1", "unclaimed")

    # 一个真人都没交：不推进。
    assert instance.all_alive_ready() is False

    instance.ready_players.add("h1")
    # AI 托管与未认领不参与等待，但第二个真人仍然阻塞。
    assert instance.all_alive_ready() is False

    instance.ready_players.add("h2")
    assert instance.all_alive_ready() is True


def test_one_human_table_passes_as_soon_as_that_human_submits() -> None:
    """1 真人 + 3 AI + 1 未认领：唯一的真人一交行动，barrier 立刻满足。"""

    instance = make_instance(uids=("h1", "a1", "a2", "a3", "u1"))
    for uid in ("a1", "a2", "a3"):
        set_control(instance, uid, "ai")
    set_control(instance, "u1", "unclaimed")

    assert instance.active_human_players == {"h1"}
    assert instance.all_alive_ready() is False

    instance.ready_players.add("h1")
    assert instance.all_alive_ready() is True


def test_all_human_table_still_waits_for_every_human() -> None:
    instance = make_instance(uids=("h1", "h2", "h3"))

    assert instance.all_alive_ready() is False
    for uid in ("h1", "h2"):
        instance.ready_players.add(uid)
        assert instance.all_alive_ready() is False

    instance.ready_players.add("h3")
    assert instance.all_alive_ready() is True


def test_away_human_still_does_not_block() -> None:
    instance = make_instance(uids=("h1", "h2"))
    instance.ready_players.add("h1")

    assert instance.all_alive_ready() is False

    instance.away_players.add("h2")
    assert instance.all_alive_ready() is True

    instance.away_players.discard("h2")
    assert instance.all_alive_ready() is False


def test_ai_only_table_never_auto_advances() -> None:
    instance = make_instance(uids=("a1", "u1"))
    set_control(instance, "a1", "ai")
    set_control(instance, "u1", "unclaimed")

    # 没有真人需要等待不等于"已经齐了"：空集合仍是 False（原有语义）。
    assert instance.active_human_players == set()
    assert instance.all_alive_ready() is False


# ---- multiplayer_status -----------------------------------------------------


def test_multiplayer_status_scopes_the_barrier_to_humans() -> None:
    instance = make_instance(uids=("h1", "h2", "h3", "a1", "u1"))
    instance.round_number = 7
    set_control(instance, "a1", "ai")
    set_control(instance, "u1", "unclaimed")
    instance.away_players.add("h2")
    instance.ready_players.add("h1")

    status = instance.multiplayer_status()

    assert [item["user_id"] for item in status["waiting_players"]] == ["h3"]
    assert [item["user_id"] for item in status["ready_players"]] == ["h1"]
    assert [item["user_id"] for item in status["away_players"]] == ["h2"]
    assert status["ai_players"] == [
        {"user_id": "a1", "character_name": "角色a1"},
    ]
    assert status["unclaimed_players"] == [
        {"user_id": "u1", "character_name": "角色u1"},
    ]
    assert status["ai_count"] == 1
    assert status["unclaimed_count"] == 1
    assert status["ready_count"] == 1
    assert status["alive_count"] == 5
    assert status["active_count"] == 4
    assert status["away_count"] == 1

    # 既有键一个都不许消失/改名。
    for key in (
        "state", "round_number", "solo_mode", "player_count", "max_players",
        "ready_count", "alive_count", "active_count", "away_count",
        "ready_players", "waiting_players", "away_players",
        "can_accept_actions", "can_advance", "action_count", "submitted_actions",
        "pending_action_count", "gm_uid", "player_access_open",
    ):
        assert key in status
    assert status["state"] == "active_action"
    assert status["round_number"] == 7
    assert status["solo_mode"] is False
    assert status["can_accept_actions"] is True


def test_multiplayer_status_reports_no_ai_seats_on_a_human_table() -> None:
    instance = make_instance(uids=("h1",))

    status = instance.multiplayer_status()

    assert status["ai_players"] == []
    assert status["unclaimed_players"] == []
    assert status["ai_count"] == 0
    assert status["unclaimed_count"] == 0


# ---- 认领（无损） -----------------------------------------------------------


@pytest.mark.parametrize("previous", ["unclaimed", "ai"])
def test_claim_seat_is_lossless(previous: str) -> None:
    instance = make_instance(uids=("u1", "h2"))
    sheet = {
        "hp": 7, "max_hp": 12, "gold": 33,
        "equipment": [{"name": "长剑", "type": "weapon", "slot": "main_hand"}],
        "inventory": [{"name": "治疗药水"}],
        "rule_binding": {"rule_id": "core:test", "version": "1"},
        "ruleset_character": {"class": "战士", "level": 3},
    }
    instance.players["u1"]["character_sheet"] = copy.deepcopy(sheet)
    apply_world_ops(instance, [
        {"op": "set_fact", "key": actor_location_fact_key("u1"), "value": "location:cellar"},
    ])
    before_player = copy.deepcopy(instance.players["u1"])
    before_world = copy.deepcopy(instance.world_state)
    before_sheet = copy.deepcopy(instance.get_character_sheet("u1"))

    set_control(instance, "u1", previous)
    before_revision = get_control(instance, "u1")["revision"]

    record = claim_seat(instance, "u1")

    assert record["mode"] == "human"
    assert record["revision"] == before_revision + 1
    assert record["temporary"] is False
    assert record["resume_mode"] is None
    assert control_mode(instance, "u1") == "human"

    # 只有 control 变了：角色本体、角色卡与世界真相一字未动。
    after_player = copy.deepcopy(instance.players["u1"])
    assert after_player.pop("control") == {
        **before_player.pop("control"), "mode": "human", "revision": before_revision + 1,
    }
    assert after_player == before_player
    assert instance.get_character_sheet("u1") == before_sheet
    assert instance.get_character_sheet("u1")["hp"] == 7
    assert instance.get_character_sheet("u1")["equipment"][0]["name"] == "长剑"
    assert instance.get_character_sheet("u1")["ruleset_character"]["level"] == 3
    assert instance.world_state == before_world
    assert fact_value(instance.world_state, actor_location_fact_key("u1")) == "location:cellar"

    # 其它席位也不受影响。
    assert control_mode(instance, "h2") == "human"


def test_claim_seat_accepts_the_current_revision() -> None:
    instance = make_instance(uids=("u1",))
    set_control(instance, "u1", "unclaimed")

    record = claim_seat(instance, "u1", expected_revision=get_control(instance, "u1")["revision"])

    assert record["mode"] == "human"


def test_claim_seat_fails_closed_on_not_claimable_seats() -> None:
    instance = make_instance(uids=("h1",))

    with pytest.raises(PlayerControlError) as excinfo:
        claim_seat(instance, "h1")

    assert "CONTROL_NOT_CLAIMABLE" in str(excinfo.value)
    assert get_control(instance, "h1") == {
        "mode": "human", "revision": 0, "temporary": False, "resume_mode": None,
    }


def test_claim_seat_fails_closed_on_a_stale_revision() -> None:
    instance = make_instance(uids=("u1",))
    set_control(instance, "u1", "unclaimed")
    stale = get_control(instance, "u1")["revision"]
    set_control(instance, "u1", "ai")  # 另一个调用点抢先改了控制记录

    with pytest.raises(PlayerControlError) as excinfo:
        claim_seat(instance, "u1", expected_revision=stale)

    assert "CONTROL_STALE" in str(excinfo.value)
    # fail closed：记录保持抢占后的状态，没有被覆盖成 human。
    assert control_mode(instance, "u1") == "ai"


def test_claim_seat_rejects_an_unknown_seat() -> None:
    instance = make_instance(uids=("h1",))

    with pytest.raises(PlayerControlError):
        claim_seat(instance, "ghost")

    assert "ghost" not in instance.players


# ---- 变更安全边界 -----------------------------------------------------------


def test_control_change_block_allows_the_action_boundary() -> None:
    instance = make_instance(uids=("h1",))

    assert instance.state == GameState.ACTIVE_ACTION
    assert instance._process_lock.locked() is False
    assert control_change_block(instance) == ""


@pytest.mark.parametrize("state", [
    GameState.ACTIVE_JUDGMENT,
    GameState.WAITING,
    GameState.PAUSED,
    GameState.ENDED,
])
def test_control_change_block_refuses_other_states(state: GameState) -> None:
    instance = make_instance(uids=("h1",))
    instance.state = state

    assert control_change_block(instance) == "CONTROL_CHANGE_BUSY"


def test_control_change_block_refuses_while_a_round_is_in_flight() -> None:
    instance = make_instance(uids=("h1",))

    async def scenario() -> None:
        async with instance._process_lock:
            assert control_change_block(instance) == "CONTROL_CHANGE_BUSY"

    asyncio.run(scenario())
    assert control_change_block(instance) == ""


def test_control_change_block_tolerates_instances_without_state() -> None:
    # 没有 GameState 的对象一律视为"不在安全边界"，不猜测。
    assert control_change_block(object()) == "CONTROL_CHANGE_BUSY"


# ---- 真实服务路径 -----------------------------------------------------------


def _unused_dependency(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("提交闸门之后的依赖不应被调用")


async def _unused_async_dependency(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("提交闸门之后的依赖不应被调用")


def make_dependencies(
    instance: GameInstance,
    *,
    process_round: Any = None,
) -> TurnDependencies:
    async def save_instance(_instance: GameInstance) -> None:
        return None

    return TurnDependencies(
        get_instance=lambda _key: instance,
        parse_game_key=lambda _key: ("web", "player-control", "bot"),
        ruleset_registry=RulesetRuntimeRegistry(),
        load_rule_for_game=lambda _instance: None,
        prepare_round_checks_ai=None,
        prepare_round_checks=None,
        resolve_pending_dice=_unused_async_dependency,
        roll_for_game=_unused_dependency,
        save_instance=save_instance,
        process_round=process_round,
        resolve_luck_decision=_unused_async_dependency,
        decline_pending_luck=_unused_async_dependency,
    )


async def _fake_process_round(_instance: GameInstance, **_kwargs: Any) -> tuple[str, Any]:
    return "本轮叙事", None


@pytest.mark.asyncio
async def test_submit_action_gate_rejects_ai_and_unclaimed_seats() -> None:
    instance = make_instance(uids=("h1", "h2", "a1", "u1"))
    set_control(instance, "a1", "ai")
    set_control(instance, "u1", "unclaimed")
    dependencies = make_dependencies(instance)

    ai_result = await submit_action(dependencies, "game", "a1", "我冲上去")
    assert ai_result["status"] == 409
    assert ai_result["payload"]["ok"] is False
    assert ai_result["payload"]["error_code"] == "PLAYER_AI_CONTROLLED"
    assert ai_result["payload"]["error"]

    unclaimed_result = await submit_action(dependencies, "game", "u1", "我冲上去")
    assert unclaimed_result["status"] == 409
    assert unclaimed_result["payload"]["error_code"] == "PLAYER_UNCLAIMED"

    # 闸门在规则/战斗检查之前：拒绝路径不写入任何行动。
    assert instance.action_queue == []
    assert instance.ready_players == set()


@pytest.mark.asyncio
async def test_submit_action_roster_check_still_precedes_the_control_gate() -> None:
    instance = make_instance(uids=("h1",))
    dependencies = make_dependencies(instance)

    missing = await submit_action(dependencies, "game", "ghost", "我冲上去")

    # 未知席位仍是 403"未加入本局"，不会被控制闸门改写成 409。
    assert missing["status"] == 403
    assert "error_code" not in missing["payload"]


@pytest.mark.asyncio
async def test_submit_action_allows_a_human_seat() -> None:
    instance = make_instance(uids=("h1", "h2"))
    dependencies = make_dependencies(instance)

    result = await submit_action(dependencies, "game", "h1", "我调查石门")

    assert result["status"] == 200
    payload = result["payload"]
    assert payload["advanced"] is False
    assert [action["user_id"] for action in instance.action_queue] == ["h1"]
    # 只有真人席位进入等待：h2 是真人，仍然阻塞；没有 AI/未认领混进来。
    assert [item["user_id"] for item in payload["multiplayer"]["waiting_players"]] == ["h2"]


@pytest.mark.asyncio
async def test_submit_action_passes_once_ai_and_unclaimed_do_not_block() -> None:
    instance = make_instance(uids=("h1", "a1", "u1"))
    set_control(instance, "a1", "ai")
    set_control(instance, "u1", "unclaimed")
    dependencies = make_dependencies(instance, process_round=_fake_process_round)

    # 表里只有一个真人：他提交后 AI 托管与未认领席位不阻塞，本轮直接推进。
    result = await submit_action(dependencies, "game", "h1", "我调查石门")

    assert result["status"] == 200
    assert result["payload"]["advanced"] is True
    assert instance.state == GameState.ACTIVE_JUDGMENT
    assert "h1" in instance.ready_players


# ---- 真实加入路径 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_rejoining_an_existing_seat_records_the_claim(web_api) -> None:
    """Web 加入已有席位走 claim_seat：ai / unclaimed 转 human，普通重连是 no-op。"""

    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api

    created = await api.create_game(
        "template_world",
        "模板世界",
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )
    inst = registry.get(api._parse_key(created["game_key"]))
    existing_uid = created["players"][0]["user_id"]

    # 新席位由 put_player 直接生成为 human，无需认领转换。
    assert control_mode(inst, existing_uid) == "human"

    set_control(inst, existing_uid, "unclaimed")
    before_revision = get_control(inst, existing_uid)["revision"]
    joined = await api.create_player(
        created["game_key"], {"user_id": existing_uid, "name": "随便填"},
    )

    assert joined["ok"] is True
    assert joined["reused"] is True
    assert control_mode(inst, existing_uid) == "human"
    assert get_control(inst, existing_uid)["revision"] == before_revision + 1
    assert len(inst.players) == 1


@pytest.mark.asyncio
async def test_a_recorded_claim_is_persisted_immediately(web_api) -> None:
    """认领是持久化状态：真人接管 AI 席位后必须立刻落盘。

    否则玩家认领完、任何行动之前服务器重启，席位会变回 AI —— 这正是
    ``temporary`` 托管不得变成永久、以及认领必须"无损且生效"的反面。
    """

    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api

    created = await api.create_game(
        "template_world",
        "模板世界",
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )
    inst = registry.get(api._parse_key(created["game_key"]))
    existing_uid = created["players"][0]["user_id"]
    set_control(inst, existing_uid, "ai")
    await registry.save(inst)

    await api.create_player(
        created["game_key"], {"user_id": existing_uid, "name": "随便填"},
    )

    # 重新从存档加载：认领后的控制权必须还在，而不是退回 AI。
    reloaded = registry.get(api._parse_key(created["game_key"]))
    if reloaded is inst:
        reloaded = GameInstance.from_dict(inst.to_dict())
    assert control_mode(reloaded, existing_uid) == "human"


@pytest.mark.asyncio
async def test_an_ordinary_reconnect_does_not_rewrite_the_save(web_api) -> None:
    """普通重连没有改变任何状态，不应该在热路径上多写一次盘。"""

    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api

    created = await api.create_game(
        "template_world",
        "模板世界",
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )
    inst = registry.get(api._parse_key(created["game_key"]))
    existing_uid = created["players"][0]["user_id"]
    revision = get_control(inst, existing_uid)["revision"]

    await api.create_player(
        created["game_key"], {"user_id": existing_uid, "name": "随便填"},
    )

    assert get_control(inst, existing_uid)["revision"] == revision
    assert control_mode(inst, existing_uid) == "human"
