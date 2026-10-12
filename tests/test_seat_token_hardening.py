"""Per-seat share tokens, hardening: visitor lobby view, per-game session
revocation, explicit takeover of bound seats, credential cleanup."""

from __future__ import annotations

from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.engine.modules import room_access
from test_game_query_routes_http import (
    ROOM_HEADER,
    ROOM_TOKEN,
    _make_game,
    _owner,
    _owner_password,  # noqa: F401
    play_env,  # noqa: F401
)
from test_share_gm_seat_guard import CONFIRM, _cookie, _share_url, share_env  # noqa: F401

# The visitor lobby contract, pinned here (and mirrored by the P2P bridge).
LOBBY_DETAIL_FIELDS = (
    "game_key", "player_access_open", "player_count", "max_players",
    "has_room_password", "world_name", "scene", "rule_id", "solo_mode",
)
LOBBY_MULTIPLAYER_FIELDS = (
    "state", "round_number", "solo_mode", "player_count", "max_players",
    "ready_count", "alive_count", "active_count", "away_count", "ai_count",
    "unclaimed_count", "can_accept_actions", "can_advance", "action_count",
    "pending_action_count", "player_access_open",
)
LOBBY_KEYS = set(LOBBY_DETAIL_FIELDS) | {"multiplayer", "viewer"}


def _detail_url(env, *, user: str | None = None) -> str:
    # The room token itself travels in the X-Room-Token header (ROOM_HEADER).
    url = f"/api/games/{env.key}?share=1"
    return url + (f"&user={user}" if user else "")


def _assert_lobby_only(body: dict) -> None:
    assert set(body) <= LOBBY_KEYS, set(body) - LOBBY_KEYS
    assert body["viewer"] == {"kind": "outsider"}
    assert set(body.get("multiplayer", {})) <= set(LOBBY_MULTIPLAYER_FIELDS)
    rendered = str(body)
    for secret in ("gm_uid", "p1", "p2", "plot_tracker", "recap", "pending_luck", "economy"):
        assert secret not in rendered, secret


# ---- F3: visitors get the lobby only ----------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["anonymous", "no-room-token", "forged-user"])
async def test_visitor_detail_is_lobby_only(share_env, case):
    env = share_env
    stranger, _ = env.sessions.get_or_create(None)
    url = {
        "anonymous": _detail_url(env),
        "no-room-token": _detail_url(env),
        "forged-user": _detail_url(env, user="p2"),
    }[case]
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        no_token = {"X-Room-Token": ""} if case == "no-room-token" else {}
        response = await client.get(url, headers={**_cookie(stranger), **no_token})
        body = await response.json()
    assert response.status == 200, body
    _assert_lobby_only(body)
    assert body["has_room_password"] is True
    assert body["player_count"] == len(env.instance.players)


@pytest.mark.asyncio
async def test_seated_player_and_owner_keep_the_full_detail(share_env):
    env = share_env
    token = room_access.issue_seat_token(env.instance, "p1")
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        seated = await (await client.get(_detail_url(env), headers={"X-Seat-Token": token})).json()
        owner = await (await client.get(f"/api/games/{env.key}", headers=_owner())).json()
    assert seated["viewer"] == {"kind": "seat", "uid": "p1"}
    assert seated["gm_uid"] == env.instance.gm_uid
    assert "plot_tracker" in seated and "economy_proposals" in seated
    assert owner["viewer"]["kind"] == "gm"
    assert owner["gm_uid"] == env.instance.gm_uid


# ---- removal and reset revoke the game's session bindings -------------------


@pytest.mark.asyncio
async def test_deleted_seat_session_is_only_a_visitor(share_env):
    env = share_env
    p2_session, _ = env.sessions.get_or_create(None)
    env.sessions.rebind(p2_session, "p2")
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        deleted = await client.delete(
            f"/api/games/{env.key}/character/p2", headers={**_owner(), **CONFIRM},
        )
        assert deleted.status == 200, await deleted.json()
    # A fresh client: the owner's request above put its own session in the jar.
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        detail = await (await client.get(_detail_url(env), headers=_cookie(p2_session))).json()
        claim = await client.post(
            _share_url(env, "seat-token/claim"), headers={**_cookie(p2_session), **CONFIRM},
        )
    _assert_lobby_only(detail)
    assert claim.status == 403
    assert env.sessions.count_bound("p2", env.key) == 0


@pytest.mark.asyncio
async def test_reset_revokes_departed_seat_sessions_and_credentials(share_env, monkeypatch):
    env = share_env
    room_access.issue_seat_token(env.instance, "p2")

    async def reset_in_place(game_key):
        # This harness has no game handler; reset the live instance the way
        # a run reset leaves it: no seats.
        await env.instance.reset()
        return {"ok": True}

    monkeypatch.setattr(env.api, "reset_game", reset_in_place)
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        reset = await client.post(
            f"/api/games/{env.key}/reset", headers={**_owner(), **CONFIRM},
        )
        assert reset.status == 200, await reset.json()
    current = env.api.get_game_instance(env.key)
    assert room_access.has_seat_token(current, "p2") is False
    assert env.sessions.count_bound("p1", env.key) == 0


@pytest.mark.asyncio
async def test_instance_reset_drops_credentials_of_departed_seats(share_env):
    env = share_env
    room_access.issue_seat_token(env.instance, "p1")
    await env.instance.reset()
    assert env.instance.players == {}
    assert env.instance.modules["room_access"]["seat_credentials"] == {}


# ---- revocation is per game -------------------------------------------------


@pytest.mark.asyncio
async def test_rotation_in_one_game_keeps_the_same_uid_seated_elsewhere(share_env, play_env):
    env = share_env
    other_key, other = _make_game(play_env, "share-guard-elsewhere", bind_adventure=False)
    other.players["p1"] = {"character_name": "elsewhere", "character_sheet": {}}
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        rotated = await client.post(
            _share_url(env, "players/p1/seat-token"),
            headers={**_owner(), **CONFIRM}, json={"rotate": True},
        )
        assert rotated.status == 200
    # A fresh client: the owner's request above put its own session in the jar.
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        here = await (await client.get(_detail_url(env), headers=_cookie(env.token))).json()
        there = await (await client.get(
            f"/api/games/{other_key}?share=1", headers=_cookie(env.token),
        )).json()
    _assert_lobby_only(here)
    assert there["viewer"] == {"kind": "seat", "uid": "p1"}
    assert env.sessions.count_bound("p1", other_key) == 1


# ---- first link on a bound seat is an explicit takeover ---------------------


@pytest.mark.asyncio
async def test_first_link_for_a_seat_with_bound_devices_needs_explicit_rotate(share_env):
    env = share_env
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        plain = await client.post(
            _share_url(env, "players/p1/seat-token"), headers={**_owner(), **CONFIRM},
        )
        plain_body = await plain.json()
        bound_before = env.sessions.count_bound("p1", env.key)
        rotated = await client.post(
            _share_url(env, "players/p1/seat-token"),
            headers={**_owner(), **CONFIRM}, json={"rotate": True},
        )
    assert plain.status == 409
    assert plain_body["error_code"] == "SEAT_TOKEN_EXISTS"
    assert plain_body["bound_sessions"] == 1
    assert plain_body["has_link"] is False
    assert bound_before == 1
    assert rotated.status == 200
    assert env.sessions.count_bound("p1", env.key) == 0


@pytest.mark.asyncio
async def test_seat_without_devices_gets_its_first_link_silently(share_env):
    env = share_env
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        response = await client.post(
            _share_url(env, "players/p2/seat-token"), headers={**_owner(), **CONFIRM},
        )
    assert response.status == 200


# ---- the GM's cached link is re-validated, never silently rotated -----------


@pytest.mark.asyncio
async def test_cached_link_is_returned_while_current_and_refused_once_stale(share_env):
    env = share_env
    current = room_access.issue_seat_token(env.instance, "p2")
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        still = await client.post(
            _share_url(env, "players/p2/seat-token"),
            headers={**_owner(), **CONFIRM}, json={"check": current},
        )
        still_body = await still.json()
        room_access.issue_seat_token(env.instance, "p2")  # another GM device rotated
        stale = await client.post(
            _share_url(env, "players/p2/seat-token"),
            headers={**_owner(), **CONFIRM}, json={"check": current},
        )
        stale_body = await stale.json()
    assert still.status == 200
    assert still_body == {"ok": True, "user_id": "p2", "seat_token": current, "reused": True}
    assert stale.status == 409
    assert stale_body["error_code"] == "SEAT_TOKEN_EXISTS"
    assert "seat_token" not in stale_body


def test_server_lobby_fields_match_the_pinned_contract():
    from src.webui.services import game_queries

    assert game_queries.LOBBY_DETAIL_FIELDS == LOBBY_DETAIL_FIELDS
    assert game_queries.LOBBY_MULTIPLAYER_FIELDS == LOBBY_MULTIPLAYER_FIELDS


# ---- review of #467 ---------------------------------------------------------


def test_game_keys_with_extra_parts_are_refused_and_canonical():
    from src.webui.services._common import _INVALID_GAME_KEY, _parse_game_key, canonical_game_key

    assert _parse_game_key("web|g|web") == ("web", "g", "web")
    assert _parse_game_key("web|g|web|anything") == _INVALID_GAME_KEY
    assert canonical_game_key("web|g|web") == "web|g|web"
    assert canonical_game_key("web|g|web|anything") != "web|g|web"


@pytest.mark.asyncio
async def test_alias_key_cannot_recreate_a_deleted_seat(share_env):
    """Deleted p2 cannot come back through an aliased game key."""
    env = share_env
    p2_session, _ = env.sessions.get_or_create(None)
    env.sessions.rebind(p2_session, "p2", env.key)
    alias = f"{env.key}|alias"
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        deleted = await client.delete(
            f"/api/games/{env.key}/character/p2",
            headers={**_owner(), **CONFIRM, **_cookie(env.gm_token)},
        )
        assert deleted.status == 200, await deleted.json()
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        rejoin = await client.post(
            f"/api/games/{alias}/players?share=1",
            headers={**_cookie(p2_session), **CONFIRM}, json={},
        )
        rejoin_body = await rejoin.json()
    assert "p2" not in env.instance.players
    assert rejoin_body.get("user_id") != "p2"
    assert "seat_token" not in rejoin_body or rejoin_body.get("user_id") != "p2"


@pytest.mark.asyncio
async def test_reset_keeps_the_gm_session_and_gm_identity(share_env, monkeypatch):
    env = share_env
    gm_uid = env.instance.gm_uid

    async def reset_in_place(game_key):
        await env.instance.reset()
        return {"ok": True}

    monkeypatch.setattr(env.api, "reset_game", reset_in_place)
    gm = {**_owner(), **CONFIRM, **_cookie(env.gm_token)}
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        reset = await client.post(f"/api/games/{env.key}/reset", headers=gm)
        assert reset.status == 200
        recreated = await client.post(
            f"/api/games/{env.key}/players", headers=gm, json={"character_name": "GM again"},
        )
        body = await recreated.json()
    assert env.key not in env.sessions.revoked_games(env.gm_token)
    assert body["user_id"] == gm_uid
    assert "seat_token" not in body
    assert not room_access.has_seat_token(env.instance, gm_uid)


@pytest.mark.asyncio
async def test_deleting_the_gm_character_keeps_the_gm_session(share_env):
    env = share_env
    gm_uid = env.instance.gm_uid
    gm = {**_owner(), **CONFIRM, **_cookie(env.gm_token)}
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        deleted = await client.delete(f"/api/games/{env.key}/character/{gm_uid}", headers=gm)
        assert deleted.status == 200, await deleted.json()
        recreated = await client.post(
            f"/api/games/{env.key}/players", headers=gm, json={"character_name": "GM again"},
        )
        body = await recreated.json()
    assert env.key not in env.sessions.revoked_games(env.gm_token)
    assert body["user_id"] == gm_uid
    assert "seat_token" not in body


@pytest.mark.asyncio
async def test_visitor_characters_is_the_join_bootstrap_only(share_env):
    env = share_env
    env.instance.npcs = {"npc-1": {"character_name": "Hidden NPC"}}
    stranger, _ = env.sessions.get_or_create(None)
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        response = await client.get(_share_url(env, "characters"), headers=_cookie(stranger))
        body = await response.json()
    assert response.status == 200
    assert body["players"] == [] and body["npcs"] == []
    assert set(body) <= {"players", "npcs", "rule_attrs", "rule_attrs_total", "rule_classes",
                         "rule_special_stats", "rule_meta", "ruleset_runtime"}
    rendered = str(body)
    for secret in ("p1", "p2", env.instance.gm_uid, "Hidden NPC"):
        assert secret not in rendered


def test_rebind_lifts_only_the_game_being_entered(share_env):
    env = share_env
    env.sessions.revoke_game_binding("p1", "web|a|web")
    env.sessions.revoke_game_binding("p1", "web|b|web")
    env.sessions.rebind(env.token, "p1", "web|a|web")
    assert env.sessions.revoked_games(env.token) == frozenset({"web|b|web"})


def test_count_bound_is_scoped_to_the_game(share_env):
    env = share_env
    elsewhere, _ = env.sessions.get_or_create(None)
    env.sessions.rebind(elsewhere, "p1", "web|other|web")
    # env.token predates game records (counted conservatively); `elsewhere`
    # entered only another game and must not be counted here.
    assert env.sessions.count_bound("p1", env.key) == 1
    assert env.sessions.count_bound("p1", "web|other|web") == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("header", ["", "   "])
async def test_empty_seat_token_header_is_treated_as_absent(share_env, header):
    env = share_env
    async with TestClient(TestServer(env.app), headers=ROOM_HEADER) as client:
        response = await client.get(
            _share_url(env, "private-log"), headers={"X-Seat-Token": header},
        )
        body = await response.json()
    assert response.status == 401
    assert body["error_code"] == "SEAT_TOKEN_REQUIRED"
