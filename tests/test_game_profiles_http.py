"""Real auth middleware, profile routes, save registry and actor authority."""

from urllib.parse import quote

import pytest
from aiohttp.test_utils import TestClient, TestServer
from aiohttp import web

from test_game_query_routes_http import (
    _make_app,
    _owner,
    _owner_password,
    play_env,  # noqa: F401
)


@pytest.mark.asyncio
async def test_shared_profile_read_and_own_move_preserve_gm_and_actor_authority(
    play_env,
):
    app = _make_app(play_env)

    @web.middleware
    async def owner_session(request, handler):
        request["user_id"] = "authenticated-owner-session"
        return await handler(request)

    app.middlewares.insert(0, owner_session)
    async with TestClient(TestServer(app)) as client:
        created = await client.post(
            "/api/game-profiles/create",
            headers=_owner(),
            json={
                "profile_id": "core:demo-survival",
                "names": ["Leader", "Scout"],
                "language": "en",
            },
        )
        assert created.status == 200
        payload = await created.json()
        initial = payload["view"]
        key = quote(payload["game_key"], safe="")
        uid = next(
            actor["uid"]
            for actor in initial["actors"]
            if actor["uid"] != initial["gm_uid"]
        )
        path = f"/api/games/{key}/profile"
        from src.engine.modules import room_access
        from src.webui.access_control import SEAT_TOKEN_HEADER
        instance = play_env.api.get_game_instance(payload["game_key"])
        seat_token = room_access.issue_seat_token(instance, uid)
        participant_headers = {SEAT_TOKEN_HEADER: seat_token}
        query = {"user": uid, "share": "1"}
        response = await client.get(path, params=query, headers=participant_headers)
        assert response.status == 200
        view = await response.json()
        assert (
            view["actor_uid"] == uid and not view["is_gm"] and not view["can_advance"]
        )
        body = {
            "type": "move",
            "move_id": "forage",
            "actor_uid": uid,
            "expected_run_id": view["run_id"],
            "expected_revision": 0,
            "expected_control_revision": 0,
        }
        for invalid in (
            {**body, "actor_uid": initial["gm_uid"]},
            {
                "type": "advance",
                "expected_run_id": view["run_id"],
                "expected_revision": 0,
            },
        ):
            rejected = await client.post(path + "/actions", params=query, headers=participant_headers, json=invalid)
            assert rejected.status == 400
        moved = await client.post(path + "/actions", params=query, headers=participant_headers, json=body)
        assert moved.status == 200
        assert (await moved.json())["view"]["revision"] == 1
        reloaded = await client.get(path, params=query, headers=participant_headers)
        assert (await reloaded.json())["revision"] == 1
        advanced = await client.post(
            path + "/actions",
            headers=_owner(),
            json={
                "type": "advance",
                "expected_revision": 1,
                "expected_run_id": view["run_id"],
            },
        )
        assert advanced.status == 200
        after = (await advanced.json())["view"]
        assert after["revision"] == 2 and after["progression"]["day"] == 2
        assert after["history"][-1]["actor_uid"] == initial["gm_uid"]
        for suffix in ("", "/actions"):
            outsider = await client.request(
                "POST" if suffix else "GET",
                path + suffix,
                params={"user": "outsider", "share": "1"},
                json=body if suffix else None,
            )
            assert outsider.status == 401
        gm_spoof = await client.get(
            path, params={"user": initial["gm_uid"], "share": "1"}
        )
        assert gm_spoof.status == 401
        # A valid non-owner token fixes the actor regardless of a spoofed uid.
        bound = await client.get(
            path, params={"user": initial["gm_uid"], "share": "1"},
            headers=participant_headers,
        )
        assert bound.status == 200
        bound_view = await bound.json()
        assert bound_view["actor_uid"] == uid and not bound_view["is_gm"]
        create_spoof = await client.post(
            "/api/game-profiles/create", params=query, json={}
        )
        assert create_spoof.status == 401


@pytest.mark.asyncio
async def test_profile_share_allowlist_is_limited_to_declared_methods_and_paths(
    play_env,
):
    app = _make_app(play_env)
    async with TestClient(TestServer(app)) as client:
        query = {"user": "player", "share": "1"}
        for method, suffix in [
            ("POST", ""),
            ("PUT", ""),
            ("GET", "/actions"),
            ("POST", "/actions/extra"),
        ]:
            response = await client.request(
                method, "/api/games/web%7Croom%7Cweb/profile" + suffix, params=query
            )
            assert response.status == 401
