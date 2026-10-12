"""Product contract: in D&D 2024 combat the party sees enemies' exact HP.

The authoritative ``ruleset_state["combat"]`` projection gives every seated
viewer (not only the GM) each enemy's current and maximum HP, while the actor
roster stays a presentation view: enemy stat-block internals (attacks,
abilities, saving throws) are not part of it, and a visitor without a seat
gets nothing.  The P2P bridge relays ``/available-actions`` to this same HTTP
route as the guest's own identity, so it inherits this projection unchanged.
"""

from __future__ import annotations

import random

import pytest
from aiohttp.test_utils import TestClient, TestServer

from src.engine.game_instance import GameInstance, GameRegistry

from test_dnd2024_encounter_preset_visibility import assert_no_stat_blocks
from test_dnd2024_m5_http import (
    _EnabledRuntime, _app, _character, _enemy, _ready_story_encounter,
)
from src.engine.modules import ruleset_runtime

_PATH = "/api/games/web%7Cenemy-hp%7Cweb_bot/available-actions"
_STAT_BLOCK_FIELDS = {"attacks", "abilities", "saving_throws", "attack_bonus"}


def _active_combat(registry: GameRegistry) -> tuple[GameInstance, str, _EnabledRuntime]:
    runtime = _EnabledRuntime()
    instance = GameInstance(
        game_key=("web", "enemy-hp", "web_bot"), world_id="test-world",
        rule_id="dnd2024_srd", gm_uid="gm", language="en",
    )
    character = _character(runtime, "stalwart_guardian", "Guardian")
    instance.players["gm"] = {"character_name": "Guardian", "character_sheet": character}
    instance.players["p1"] = {
        "character_name": "Scout",
        "character_sheet": _character(runtime, "stalwart_guardian", "Scout"),
    }
    assert instance.bind_ruleset_runtime(character["rule_binding"])
    encounter = _ready_story_encounter(runtime, instance)
    resolved = runtime.resolve_intent(instance, {
        "intent_id": "enemy-hp-start", "type": "combat.start",
        "expected_version": encounter["expected_version"],
        "encounter_preset_id": encounter["encounter_preset_id"],
        "encounter_instance_id": encounter["encounter_instance_id"],
        "submitted_by": "gm", "enemies": [_enemy()],
    }, random.Random(7))
    assert resolved["ok"] is True
    runtime.apply_event_batch(instance, resolved["event_batch"])
    enemies = ruleset_runtime.state(instance)["combat"]["enemies"]
    assert enemies, "story encounter must put at least one enemy into combat"
    enemy_id = next(iter(enemies))
    # A wounded enemy: the authoritative HP must reach players verbatim,
    # not rounded into a band or a description.
    enemies[enemy_id]["hp"] = 3
    registry.register(instance)
    return instance, enemy_id, runtime


@pytest.mark.asyncio
async def test_seated_player_and_gm_see_exact_enemy_hp(tmp_path) -> None:
    registry = GameRegistry(tmp_path / "saves")
    instance, enemy_id, runtime = _active_combat(registry)
    max_hp = int(ruleset_runtime.state(instance)["combat"]["enemies"][enemy_id]["max_hp"])
    assert max_hp > 3

    async with TestClient(TestServer(_app(registry, runtime))) as client:
        seat = await client.get(_PATH, headers={"X-Test-User": "p1"})
        gm = await client.get(_PATH, headers={"X-Test-User": "gm"})
        seat_body, gm_body = await seat.json(), await gm.json()

    assert seat.status == 200 and gm.status == 200
    for body in (seat_body, gm_body):
        actors = {
            actor["actor_id"]: actor for actor in body["gameplay"]["combat"]["actors"]
        }
        enemy = actors[f"enemy:{enemy_id}"]
        assert (enemy["hp"], enemy["max_hp"]) == (3, max_hp)
        # The roster is a presentation view, not the GM stat block.
        assert not _STAT_BLOCK_FIELDS & set(enemy)
    # The whole seated-player payload is free of GM-only stat-block keys.
    assert_no_stat_blocks(seat_body, "seat")
    # Players and the GM read one projection of enemy HP, not two.
    seat_enemy = next(
        actor for actor in seat_body["gameplay"]["combat"]["actors"]
        if actor["actor_id"] == f"enemy:{enemy_id}"
    )
    gm_enemy = next(
        actor for actor in gm_body["gameplay"]["combat"]["actors"]
        if actor["actor_id"] == f"enemy:{enemy_id}"
    )
    assert seat_enemy == gm_enemy


@pytest.mark.asyncio
async def test_outsider_gets_no_combat_projection(tmp_path) -> None:
    registry = GameRegistry(tmp_path / "saves")
    _instance, _enemy_id, runtime = _active_combat(registry)

    async with TestClient(TestServer(_app(registry, runtime))) as client:
        outsider = await client.get(_PATH, headers={"X-Test-User": "intruder"})
        anonymous = await client.get(_PATH)
        outsider_body = await outsider.json()

    assert outsider.status == 403
    assert "gameplay" not in outsider_body
    assert anonymous.status in {401, 403}
