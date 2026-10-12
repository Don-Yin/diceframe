"""seat_activity: v40 -> v41 seeding and which plays mark a seat."""

from __future__ import annotations

from copy import deepcopy

import pytest

from src.engine.game_instance import GameInstance
from src.engine.modules import seat_activity
from src.engine.player_control import set_control
from src.migrations.instance import (
    CURRENT_INSTANCE_SCHEMA_VERSION,
    _migrate_v40_to_v41,
    migrate_game_state_payload,
)

KEY = ["web", "seat-activity", "bot"]
HUMAN = {"mode": "human", "revision": 1}
AWAY = {"mode": "ai", "revision": 2, "temporary": True, "resume_mode": "human"}
AI_FOR_GOOD = {"mode": "ai", "revision": 1}


def v40_payload(*, started_at="", log=None, **extra):
    return {
        "game_key": KEY, "state": "active_action", "instance_schema_version": 40,
        "players": {
            "human": {"character_name": "H", "character_sheet": {}, "control": dict(HUMAN)},
            "legacy": {"character_name": "L", "character_sheet": {}},  # no control: human
            "away": {"character_name": "W", "character_sheet": {}, "control": dict(AWAY)},
            "npc_ai": {"character_name": "A", "character_sheet": {}, "control": dict(AI_FOR_GOOD)},
            "ai_logged": {"character_name": "B", "character_sheet": {}, "control": dict(AI_FOR_GOOD)},
        },
        "modules": {"session_stats": {"schema_version": 1, "started_at": started_at}},
        "log": log if log is not None else [],
        **extra,
    }


STARTED_LOG = [{"round": 1, "actions": [
    {"user_id": "ai_logged", "text": "acted while it was still human"},
    {"user_id": "system", "text": "Game Start"},
]}]


def _acted(payload) -> list[str]:
    return payload["modules"]["seat_activity"]["acted_seats"]


def test_started_run_seeds_its_players_and_logged_actors():
    original = v40_payload(started_at="2026-01-01T00:00:00+00:00", log=STARTED_LOG)
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert original == before
    assert migrated["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert sorted(_acted(migrated)) == ["ai_logged", "away", "human", "legacy"]
    assert migrate_game_state_payload(migrated) == migrated
    step = _migrate_v40_to_v41(deepcopy(original))
    assert _migrate_v40_to_v41(deepcopy(step)) == step


@pytest.mark.parametrize("started_at, log", [("2026-01-01T00:00:00+00:00", []), ("", STARTED_LOG)])
def test_either_signal_means_the_run_is_in_play(started_at, log):
    migrated = migrate_game_state_payload(v40_payload(started_at=started_at, log=log))
    assert {"human", "legacy", "away"} <= set(_acted(migrated))
    assert "npc_ai" not in _acted(migrated)


def test_fresh_lobby_stays_empty():
    migrated = migrate_game_state_payload(v40_payload())
    assert _acted(migrated) == []


@pytest.mark.parametrize("slot", [
    {"schema_version": 1, "acted_seats": ["someone"]},
    {"schema_version": 99, "opaque": True},
])
def test_existing_or_future_slot_is_left_untouched(slot):
    payload = v40_payload(started_at="2026-01-01T00:00:00+00:00", log=STARTED_LOG)
    payload["modules"]["seat_activity"] = deepcopy(slot)
    migrated = migrate_game_state_payload(payload)
    assert migrated["modules"]["seat_activity"] == slot


def test_old_saves_travel_the_whole_ladder():
    payload = {"game_key": KEY, "state": "waiting", "instance_schema_version": 24,
               "players": {"p1": {"character_name": "P", "character_sheet": {}}},
               "log": STARTED_LOG}
    migrated = migrate_game_state_payload(payload)
    assert _acted(migrated) == ["p1"]


def test_loaded_campaign_is_locked_right_after_the_upgrade():
    restored = GameInstance.from_dict(
        v40_payload(started_at="2026-01-01T00:00:00+00:00", log=STARTED_LOG),
    )
    assert seat_activity.has_acted(restored, "human")
    assert not seat_activity.has_acted(restored, "npc_ai")


# ---- which plays mark the seat -------------------------------------------------


def _running(uid="p1") -> GameInstance:
    instance = GameInstance.from_dict(v40_payload())
    instance.players[uid] = {"character_name": "P", "character_sheet": {}}
    return instance


@pytest.mark.asyncio
async def test_ai_hosting_an_away_player_marks_the_seat():
    instance = _running()
    set_control(instance, "p1", "ai", temporary=True, resume_mode="human")
    assert await instance.add_action("p1", "AI 替暂离的玩家行动") is True
    assert seat_activity.has_acted(instance, "p1")


@pytest.mark.asyncio
async def test_ai_seat_for_good_or_awaiting_a_claim_stays_adoptable():
    instance = _running()
    set_control(instance, "p1", "ai")
    assert await instance.add_action("p1", "AI 自己的席位") is True
    instance.players["p2"] = {"character_name": "Q", "character_sheet": {}}
    set_control(instance, "p2", "ai", temporary=True, resume_mode="unclaimed")
    assert await instance.add_action("p2", "AI 代管待认领席位") is True
    assert not seat_activity.has_acted(instance, "p1")
    assert not seat_activity.has_acted(instance, "p2")
