from __future__ import annotations

import shutil
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.webui.routes.check_modes import register
from tests.test_check_mode_permissions import game, ROOT
from webapi_harness import web_api  # noqa: F401


@pytest.mark.asyncio
async def test_real_routes_actor_isolation_preview_and_refresh(web_api):
    api, _, registry, _, worlds = web_api
    for path in (ROOT / "templates/rules").glob("*.json"):
        shutil.copyfile(path, worlds.parent / "rules" / path.name)
    inst = game()
    inst.rule_id = "dnd5e"
    inst.world_id = "template_world"
    registry.register(inst)

    @web.middleware
    async def identity(request, handler):
        request["user_id"] = request.headers.get("User", "")
        request["owner_authenticated"] = request.headers.get("Owner") == "yes"
        request["player_preview"] = request.headers.get("Preview") == "yes"
        request["player_delegate"] = request.headers.get("Delegate") == "yes"
        return await handler(request)

    app = web.Application(middlewares=[identity])
    app["api"] = api
    register(app)
    base = "/api/games/web%7Cmodes%7Cbot/check-modes"
    async with TestClient(TestServer(app)) as client:
        assert (await client.get(base)).status == 403
        view = await (await client.get(base, headers={"User": "a"})).json()
        assert [seat["uid"] for seat in view["seats"]] == ["a"]
        data = {"expected_revision": view["revision"], "context_id": view["seats"][0]["context_id"],
                "run_id": view["run_id"], "mode": "advantage", "reason": "request"}
        assert (await client.post(base + "/seats/b/request", headers={"User": "a"}, json=data)).status == 403
        assert (await client.post(base + "/seats/a/grant", headers={"User": "a"}, json=data)).status == 403
        preview = {"User": "a", "Owner": "yes", "Preview": "yes"}
        assert (await client.post(base + "/seats/a/grant", headers=preview, json=data)).status == 403
        assert (await client.post(base + "/seats/a/request", headers=preview, json=data)).status == 403
        response = await client.post(base + "/seats/a/request", headers={"User": "a"}, json=data)
        assert response.status == 200
        data["expected_revision"] += 1
        assert (await client.post(base + "/seats/a/grant", headers={"User": "gm"}, json=data)).status == 200
        refreshed = await (await client.get(base, headers={"User": "a"})).json()
        assert refreshed["seats"][0]["grant"]["mode"] == "advantage"
        assert refreshed["revision"] == 2
