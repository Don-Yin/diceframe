from __future__ import annotations

import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.webui.routes.ai_seats import register
from tests.test_ai_seat_settings import config, table
from webapi_harness import web_api  # noqa: F401


@pytest.mark.asyncio
async def test_ai_settings_routes_require_gm_and_deny_owner_player_preview(web_api):
    api, _, registry, _, _ = web_api
    inst = table()
    registry.register(inst)
    api._config_state.update(config())

    @web.middleware
    async def identity(request, handler):
        request["user_id"] = request.headers.get("User", "")
        request["owner_authenticated"] = request.headers.get("Owner") == "yes"
        request["player_preview"] = request.headers.get("Preview") == "yes"
        return await handler(request)

    app = web.Application(middlewares=[identity])
    app["api"] = api
    register(app)
    base = "/api/games/web%7Cseats%7Cbot/ai-seats"
    async with TestClient(TestServer(app)) as client:
        for headers in ({}, {"User": "a"}, {"User": "h", "Owner": "yes", "Preview": "yes"}):
            for method, suffix in (("get", ""), ("put", "/defaults"), ("put", "/seats/a"), ("post", "/seats/a/retry")):
                response = await getattr(client, method)(base + suffix, headers=headers, json={})
                assert response.status == 403
        headers = {"User": "h"}
        response = await client.get(base, headers=headers)
        assert response.status == 200
        assert "SECRET-KEY" not in json.dumps(await response.json())
        response = await client.put(base + "/seats/a", headers=headers, json={"expected_revision": 0,
            "settings": {"provider_ref": "other", "model": "large", "style": "bold"}})
        assert response.status == 200
        result = await response.json()
        assert result["seats"]["a"]["model"] == "large"
        assert result["revision"] == 1
        assert (await client.put(base + "/seats/b", headers=headers, json={"expected_revision": 0,
            "settings": {"style": "cautious"}})).status == 400
        assert (await client.put(base + "/seats/a", headers=headers, json={"expected_revision": 1,
            "settings": {"provider_ref": "other", "model": "image"}})).status == 400
        assert (await client.put(base + "/seats/a", headers=headers, json=[])).status == 400
        assert (await client.put(base + "/seats/a", headers=headers, data='{')).status == 400
        assert inst.modules["ai_seats"]["revision"] == 1
        await registry.load(inst.game_key)
        assert registry.get(inst.game_key).modules["ai_seats"]["seats"]["a"]["model"] == "large"


@pytest.mark.asyncio
async def test_seat_named_defaults_is_distinct_from_game_defaults(web_api):
    api, _, registry, _, _ = web_api
    inst = table()
    inst.put_player("defaults", {"user_id": "defaults", "character_name": "Defaults"})
    registry.register(inst)
    api._config_state.update(config())

    @web.middleware
    async def identity(request, handler):
        request["user_id"] = "h"
        return await handler(request)

    app = web.Application(middlewares=[identity])
    app["api"] = api
    register(app)
    async with TestClient(TestServer(app)) as client:
        result = await client.put("/api/games/web%7Cseats%7Cbot/ai-seats/seats/defaults",
                                  json={"expected_revision": 0, "settings": {"style": "bold"}})
        assert result.status == 200
        view = await result.json()
        assert view["seats"]["defaults"]["style"] == "bold"
        assert view["defaults"]["style"] == "character"
