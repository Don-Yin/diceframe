"""Who may change which field of a classic character sheet (anti-cheat).

Mechanics (HP, level, XP, gold, attributes, inventory...) are engine / GM
authority.  A seated player, a bot acting for a player seat and a P2P guest
relayed by the host may only edit the profile, plus spend level-up points.
"""

from __future__ import annotations

from copy import deepcopy

from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.engine.game_instance import GameInstance
from src.engine.game_state import GameState
from src.engine.modules import room_access, seat_activity
from src.engine.player_control import set_control
from src.webui.character_sheet_authority import (
    ADOPT_REQUIRES_GM,
    DELETE_REQUIRES_GM,
    FIELD_REQUIRES_GM,
    level_up_allocation,
    player_field_violations,
)
from test_game_query_routes_http import (
    GM_UID,
    ROOM_HEADER,
    _owner,
    _owner_password,  # noqa: F401
    play_env,  # noqa: F401
)
from test_share_gm_seat_guard import CONFIRM, share_env  # noqa: F401


SHEET = {
    "race": "人类", "class": "游侠", "background": "旧背景",
    "level": 2, "xp": 10, "hp": 20, "max_hp": 30, "gold": 5,
    "currency": {"gp": 5}, "attributes": {"str": 10},
    "skills": [{"name": "侦查", "value": 40}],
    "equipment": [{"name": "短剑", "type": "weapon", "slot": "main_hand"}],
    "inventory": [{"name": "绳子"}], "key_items": [],
    "level_up_points": 0, "attr_points_max": 10,
}

MECHANICAL_CHANGES = {
    "hp": 999, "max_hp": 999, "level": 20, "xp": 99999, "gold": 99999,
    "currency": {"gp": 99999}, "attributes": {"str": 18},
    "skills": [{"name": "侦查", "value": 99}],
    "equipment": [{"name": "神剑", "type": "weapon", "slot": "main_hand"}],
    "inventory": [{"name": "万能药"}], "key_items": [{"name": "王冠"}],
    "resources": {"hp": {"current": 999, "max": 999}},
    "progression": {"level": 20}, "class": "法师",
}


@pytest.fixture
def table(share_env):
    env = share_env
    env.instance.players["p1"]["character_sheet"] = deepcopy(SHEET)
    env.instance.players["p2"]["character_sheet"] = deepcopy(SHEET)
    return env


def _url(env, uid="p1", query="share=1"):
    return f"/api/games/{env.key}/character/{uid}" + (f"?{query}" if query else "")


def _seat(env, uid="p1"):
    return {"X-Seat-Token": room_access.issue_seat_token(env.instance, uid), **CONFIRM}


def _sheet(env, uid="p1"):
    return env.instance.players[uid]["character_sheet"]


async def _put(env, json, *, headers, url=None):
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        response = await client.put(url or _url(env), headers=headers, json=json)
        return response.status, await response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", sorted(MECHANICAL_CHANGES))
async def test_seated_player_cannot_change_own_mechanics(table, field):
    before = deepcopy(_sheet(table))
    status, body = await _put(table, {field: MECHANICAL_CHANGES[field]}, headers=_seat(table))
    assert status == 403, body
    assert body["error_code"] == FIELD_REQUIRES_GM
    assert body["fields"] == [field]
    assert _sheet(table) == before


@pytest.mark.asyncio
async def test_one_mechanical_field_rejects_the_whole_player_patch(table):
    status, body = await _put(
        table, {"character_name": "改名", "background": "新背景", "gold": 99999},
        headers=_seat(table),
    )
    assert status == 403
    assert body["fields"] == ["gold"]
    assert table.instance.players["p1"]["character_name"] == "甲"
    assert _sheet(table)["background"] == "旧背景"


@pytest.mark.asyncio
async def test_seated_player_can_edit_profile(table):
    status, body = await _put(table, {
        "character_name": "新名字", "background": "新背景", "race": "精灵",
        "identity": {"origin": "精灵"},
        "portrait": {"kind": "builtin", "id": "freeform_fantasy:3"},
        # Resent unchanged mechanics (a whole-sheet client) are not a change.
        "hp": 20, "level": 2,
    }, headers=_seat(table))
    assert status == 200, body
    sheet = _sheet(table)
    assert table.instance.players["p1"]["character_name"] == "新名字"
    assert sheet["background"] == "新背景"
    assert sheet["race"] == "精灵"
    assert sheet["portrait"] == {"kind": "builtin", "id": "freeform_fantasy:3"}
    assert (sheet["hp"], sheet["max_hp"], sheet["level"], sheet["gold"]) == (20, 30, 2, 5)


@pytest.mark.asyncio
async def test_player_spends_only_granted_level_up_points(table):
    _sheet(table)["level_up_points"] = 2
    over, body = await _put(table, {"attributes": {"str": 13}}, headers=_seat(table))
    assert over == 403 and body["fields"] == ["attributes"]
    lowered, _ = await _put(table, {"attributes": {"str": 9}}, headers=_seat(table))
    assert lowered == 403
    new_key, _ = await _put(table, {"attributes": {"str": 10, "luck": 18}}, headers=_seat(table))
    assert new_key == 403
    assert _sheet(table)["attributes"] == {"str": 10}

    status, body = await _put(table, {"attributes": {"str": 12}}, headers=_seat(table))
    assert status == 200, body
    assert _sheet(table)["attributes"] == {"str": 12}
    assert _sheet(table)["level_up_points"] == 0
    again, _ = await _put(table, {"attributes": {"str": 13}}, headers=_seat(table))
    assert again == 403


@pytest.mark.asyncio
async def test_other_seat_cannot_edit_at_all(table):
    before = deepcopy(_sheet(table))
    status, body = await _put(
        table, {"background": "被别人改了"}, headers=_seat(table, "p2"),
    )
    assert status == 403
    assert _sheet(table) == before


@pytest.mark.asyncio
async def test_owner_keeps_full_edit(table):
    status, body = await _put(
        table, dict(MECHANICAL_CHANGES, resources={}, progression={}),
        headers={**_owner(), **CONFIRM}, url=_url(table, query=""),
    )
    assert status == 200, body
    sheet = _sheet(table)
    assert (sheet["level"], sheet["xp"], sheet["gold"], sheet["class"]) == (20, 99999, 99999, "法师")
    assert (sheet["hp"], sheet["max_hp"]) == (999, 999)
    assert sheet["attributes"] == {"str": 18}
    assert sheet["inventory"] == [{"name": "万能药"}]


@pytest.mark.asyncio
async def test_owner_preview_as_player_keeps_owner_authority(table):
    status, body = await _put(
        table, {"gold": 77}, headers={**_owner(), **CONFIRM},
        url=_url(table, query="user=p1&share=1"),
    )
    assert status == 200, body
    assert _sheet(table)["gold"] == 77


@pytest.mark.asyncio
async def test_p2p_guest_relayed_by_host_is_restricted(table):
    """The host executes guest writes owner-authenticated with ``delegate=1``."""
    relayed = {**_owner(), **CONFIRM}
    url = _url(table, query="user=p1&share=1&delegate=1")
    status, body = await _put(table, {"hp": 999, "attributes": {"str": 18}}, headers=relayed, url=url)
    assert status == 403, body
    assert body["fields"] == ["attributes", "hp"]
    assert _sheet(table)["hp"] == 20
    status, body = await _put(table, {"character_name": "访客改名"}, headers=relayed, url=url)
    assert status == 200, body
    assert table.instance.players["p1"]["character_name"] == "访客改名"


@pytest.mark.asyncio
async def test_bot_for_a_player_seat_is_restricted_but_gm_seat_is_not(table, monkeypatch):
    import web_server

    monkeypatch.setitem(web_server.STATE, "bot_token", "bot-secret")
    as_player = {"X-Bot-Token": "bot-secret", "X-Bot-Actor": "p1", **CONFIRM}
    status, body = await _put(table, {"gold": 99999}, headers=as_player, url=_url(table, query=""))
    assert status == 403, body
    assert body["error_code"] == FIELD_REQUIRES_GM
    assert _sheet(table)["gold"] == 5
    status, _ = await _put(table, {"background": "bot 写的"}, headers=as_player, url=_url(table, query=""))
    assert status == 200

    as_gm = {"X-Bot-Token": "bot-secret", "X-Bot-Actor": GM_UID, **CONFIRM}
    status, body = await _put(table, {"gold": 42}, headers=as_gm, url=_url(table, query=""))
    assert status == 200, body
    assert _sheet(table)["gold"] == 42


@pytest.mark.asyncio
async def test_player_adopts_a_library_card_by_id_only(table):
    """Classic adoption reads the card server-side; the request carries only its id."""
    assert table.api.save_character_card({
        "character_name": "Plugin Hero", "source_plugin": "starter-pack",
        "attributes": {"str": 14}, "hp": 25, "max_hp": 25,
    })["ok"]
    card = next(
        c for c in table.api.list_character_cards()["cards"]
        if c.get("character_name") == "Plugin Hero"
    )
    async with TestClient(TestServer(table.app), headers=ROOM_HEADER) as client:
        response = await client.post(
            _url(table).replace("/character/p1?", "/character/p1/adopt-card?"),
            headers=_seat(table),
            json={"card_id": card["id"], "hp": 999, "gold": 99999},
        )
        body = await response.json()
    assert response.status == 200, body
    sheet = _sheet(table)
    assert table.instance.players["p1"]["character_name"] == "Plugin Hero"
    assert sheet["attributes"] == {"str": 14}
    assert sheet["hp"] != 999 and sheet["gold"] != 99999


# ---- once a seat has acted, card adoption and deletion are GM-only ----------
# Adopting replaces stats, gold and equipment, and delete + rejoin is the same
# reset: after the seat played, either is a free refill / re-roll.  The table
# is a running web game (ACTIVE_ACTION), as every web-created game is.

ADOPT_CARD = {
    # Plugin-shipped, so seated players may see (and so adopt) it.
    "character_name": "Refill Hero", "source_plugin": "starter-pack", "attributes": {"str": 18},
    "hp": 99, "max_hp": 99, "gold": 9999,
    "equipment": [{"name": "神剑", "type": "weapon", "slot": "main_hand"}],
}


def _adopt_card_id(env) -> str:
    assert env.api.save_character_card(dict(ADOPT_CARD))["ok"]
    return next(
        c["id"] for c in env.api.list_character_cards()["cards"]
        if c.get("character_name") == "Refill Hero"
    )


def _adopt_url(env, uid="p1", query="share=1"):
    return _url(env, uid, query).replace(f"/character/{uid}", f"/character/{uid}/adopt-card")


async def _adopt(env, card_id, *, headers, url=None):
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        response = await client.post(
            url or _adopt_url(env), headers=headers, json={"card_id": card_id},
        )
        return response.status, await response.json()


async def _delete(env, *, headers, url=None):
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        response = await client.delete(url or _url(env), headers=headers)
        return response.status, await response.json()


async def _act(env, uid="p1"):
    """The seat declares an action through the engine's action boundary."""
    assert await env.instance.add_action(uid, "我拔剑冲向哨兵") is True
    assert seat_activity.has_acted(env.instance, uid)


@pytest.mark.asyncio
async def test_fresh_seat_in_a_running_game_self_adopts(table):
    """Claiming a GM-prepared seat, then switching to one's own card, still works."""
    assert table.instance.state == GameState.ACTIVE_ACTION
    card_id = _adopt_card_id(table)
    status, body = await _adopt(table, card_id, headers=_seat(table))
    assert status == 200, body
    assert _sheet(table)["gold"] == 9999
    assert table.instance.players["p1"]["character_name"] == "Refill Hero"


@pytest.mark.asyncio
async def test_seat_cannot_self_adopt_after_it_acted(table):
    card_id = _adopt_card_id(table)
    await _act(table)
    before = deepcopy(table.instance.players["p1"])
    status, body = await _adopt(table, card_id, headers=_seat(table))
    assert status == 403, body
    assert body["error_code"] == ADOPT_REQUIRES_GM
    assert table.instance.players["p1"] == before


@pytest.mark.asyncio
async def test_ai_hosted_actions_do_not_lock_the_seat(table):
    """A seat the AI played is still the claimer's to switch to their own card."""
    set_control(table.instance, "p1", "ai")
    assert await table.instance.add_action("p1", "AI 替这个席位行动") is True
    assert not seat_activity.has_acted(table.instance, "p1")


@pytest.mark.asyncio
async def test_gm_and_owner_always_adopt(table, monkeypatch):
    import web_server

    card_id = _adopt_card_id(table)
    await _act(table, "p1")
    await _act(table, "p2")
    status, body = await _adopt(
        table, card_id, headers={**_owner(), **CONFIRM}, url=_adopt_url(table, query=""),
    )
    assert status == 200, body
    assert _sheet(table)["gold"] == 9999

    monkeypatch.setitem(web_server.STATE, "bot_token", "bot-secret")
    as_gm = {"X-Bot-Token": "bot-secret", "X-Bot-Actor": GM_UID, **CONFIRM}
    status, body = await _adopt(table, card_id, headers=as_gm, url=_adopt_url(table, "p2", ""))
    assert status == 200, body
    assert _sheet(table, "p2")["gold"] == 9999


@pytest.mark.asyncio
async def test_bot_for_a_player_seat_follows_the_seat_rule(table, monkeypatch):
    import web_server

    monkeypatch.setitem(web_server.STATE, "bot_token", "bot-secret")
    card_id = _adopt_card_id(table)
    as_player = {"X-Bot-Token": "bot-secret", "X-Bot-Actor": "p1", **CONFIRM}
    await _act(table)
    before = deepcopy(table.instance.players["p1"])
    status, body = await _adopt(table, card_id, headers=as_player, url=_adopt_url(table, query=""))
    assert status == 403, body
    assert body["error_code"] == ADOPT_REQUIRES_GM
    assert table.instance.players["p1"] == before


@pytest.mark.asyncio
async def test_p2p_guest_relayed_by_host_follows_the_seat_rule(table):
    card_id = _adopt_card_id(table)
    relayed = {**_owner(), **CONFIRM}
    url = _adopt_url(table, query="user=p1&share=1&delegate=1")
    await _act(table)
    before = deepcopy(table.instance.players["p1"])
    status, body = await _adopt(table, card_id, headers=relayed, url=url)
    assert status == 403, body
    assert body["error_code"] == ADOPT_REQUIRES_GM
    assert table.instance.players["p1"] == before


# Share links (seat tokens) cannot DELETE a character at all (access policy)
# and the P2P bridge has no delete operation; the player-side caller that
# reaches the delete route is a bot acting for the seat.

def _bot_for(uid):
    return {"X-Bot-Token": "bot-secret", "X-Bot-Actor": uid, **CONFIRM}


@pytest.mark.asyncio
async def test_seat_that_never_acted_may_still_delete_itself(table, monkeypatch):
    import web_server

    monkeypatch.setitem(web_server.STATE, "bot_token", "bot-secret")
    status, body = await _delete(table, headers=_bot_for("p1"), url=_url(table, query=""))
    assert status == 200, body
    assert "p1" not in table.instance.players


@pytest.mark.asyncio
async def test_acted_seat_cannot_delete_itself_and_rejoin(table, monkeypatch):
    import web_server

    monkeypatch.setitem(web_server.STATE, "bot_token", "bot-secret")
    await _act(table)
    before = deepcopy(table.instance.players["p1"])
    status, body = await _delete(table, headers=_bot_for("p1"), url=_url(table, query=""))
    assert status == 403, body
    assert body["error_code"] == DELETE_REQUIRES_GM
    assert table.instance.players["p1"] == before

    status, body = await _delete(table, headers={**_owner(), **CONFIRM}, url=_url(table, query=""))
    assert status == 200, body
    assert "p1" not in table.instance.players
    assert not seat_activity.has_acted(table.instance, "p1")


@pytest.mark.asyncio
async def test_bot_for_the_gm_seat_deletes_an_acted_seat(table, monkeypatch):
    import web_server

    monkeypatch.setitem(web_server.STATE, "bot_token", "bot-secret")
    await _act(table)
    status, body = await _delete(table, headers=_bot_for(GM_UID), url=_url(table, query=""))
    assert status == 200, body
    assert "p1" not in table.instance.players


@pytest.mark.asyncio
async def test_new_player_still_joins_mid_game_from_a_card(table):
    """Joining creates a fresh seat (JoinView copies a card into the form)."""
    from test_share_gm_seat_guard import _cookie

    fresh, _ = table.sessions.get_or_create(None)
    async with TestClient(TestServer(table.app), headers=ROOM_HEADER) as client:
        response = await client.post(
            f"/api/games/{table.key}/players?share=1", headers=_cookie(fresh),
            json={"character_name": "Refill Hero", "attributes": {"str": 12},
                  "race": "人类", "class": "游侠", "join_as_new": True},
        )
        body = await response.json()
    assert response.status == 200, body
    assert table.instance.players[body["user_id"]]["character_name"] == "Refill Hero"
    assert not seat_activity.has_acted(table.instance, body["user_id"])


@pytest.mark.asyncio
async def test_roster_projects_has_acted_per_seat(table):
    await _act(table)
    async with TestClient(TestServer(table.app), headers=ROOM_HEADER) as client:
        roster = await (await client.get(
            f"/api/games/{table.key}/characters?share=1", headers=_seat(table),
        )).json()
    flags = {p["user_id"]: p["has_acted"] for p in roster["players"]}
    assert flags["p1"] is True and flags["p2"] is False


@pytest.mark.asyncio
async def test_acted_flag_survives_save_and_clears_with_the_run(table):
    await _act(table)
    restored = GameInstance.from_dict(table.instance.to_dict())
    assert seat_activity.has_acted(restored, "p1")
    await restored.reset()
    assert not seat_activity.has_acted(restored, "p1")


def test_policy_denies_rule_special_stats_and_unknown_mechanics():
    sheet = {"sanity": 50, "max_sanity": 99, "attributes": {"str": 10}}
    updates = {"sanity": 99, "max_sanity": 99, "portrait": None}
    assert player_field_violations(sheet, updates, rule_attrs=[]) == ["sanity"]


def test_level_up_allocation_respects_rule_maximum_and_keeps_omitted_attributes():
    sheet = {"attributes": {"str": 17, "dex": 12}, "level_up_points": 2}
    rule_attrs = [{"key": "str", "max": 18}, {"key": "dex", "max": 18}]
    assert level_up_allocation(sheet, {"str": 19}, rule_attrs) is None
    assert level_up_allocation(sheet, {"str": 18}, rule_attrs) == {"str": 18, "dex": 12}
    assert level_up_allocation(sheet, {"str": True}, rule_attrs) is None
    assert level_up_allocation(sheet, {"str": 18, "dex": 14}, rule_attrs) is None


# ---- review of #470: a level-up spend must not heal, revive or reset max HP ----
# The test rule's formula is ``20 + str``.


@pytest.mark.asyncio
async def test_spending_a_point_does_not_revive_a_downed_character(table):
    sheet = _sheet(table)
    sheet.update(hp=0, max_hp=30, level_up_points=2)
    status, body = await _put(table, {"attributes": {"str": 11}}, headers=_seat(table))
    assert status == 200, body
    sheet = _sheet(table)
    assert sheet["attributes"] == {"str": 11}
    assert sheet["hp"] == 0
    assert sheet["max_hp"] == 31


@pytest.mark.asyncio
async def test_player_spend_applies_only_the_formula_delta_to_gm_max_hp(table):
    sheet = _sheet(table)
    sheet.update(hp=40, max_hp=50, level_up_points=2)  # GM-adjusted max HP
    status, body = await _put(table, {"attributes": {"str": 12}}, headers=_seat(table))
    assert status == 200, body
    sheet = _sheet(table)
    assert (sheet["hp"], sheet["max_hp"]) == (42, 52)


@pytest.mark.asyncio
async def test_gm_attribute_edit_does_not_revive_a_downed_character(table):
    _sheet(table).update(hp=0, max_hp=30)
    status, body = await _put(
        table, {"attributes": {"str": 14}},
        headers={**_owner(), **CONFIRM}, url=_url(table, query=""),
    )
    assert status == 200, body
    assert _sheet(table)["hp"] == 0
