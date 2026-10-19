from src.engine.modules import checks
import shutil
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.webui.routes.check_decisions import register
from tests.test_push_decisions import ROOT, prepared
from webapi_harness import web_api  # noqa: F401


@pytest.mark.asyncio
async def test_real_push_routes_keep_actor_identity_and_resume_through_turn_boundary(web_api):
    api, _, registry, _, worlds = web_api
    for path in (ROOT / "templates/rules").glob("*.json"):
        shutil.copyfile(path, worlds.parent / "rules" / path.name)
    inst, _ = prepared()
    inst.world_id = "template_world"
    inst.rule_id = "freeform_coc"
    registry.register(inst)
    process = AsyncMock(return_value=("resolved story", None))
    api._turn_dependencies = replace(api._turn_dependencies, process_round=process)

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
    base = "/api/games/web%7Cpush%7Cbot/checks/c1/push/"
    def body(**extra):
        return {"run_id": inst.run_id, "round_number": inst.round_number,
                "expected_revision": checks.last_checks(inst)[0]["push"]["revision"], **extra}

    async with TestClient(TestServer(app)) as client:
        assert (await client.post(base + "request", json=body(reason="test"))).status == 403
        assert (await client.post(base + "request", headers={"User": "b"}, json=body(reason="test"))).status == 403
        assert (await client.post(base + "request", headers={"User": "a", "Preview": "yes"}, json=body(reason="test"))).status == 403
        response = await client.post(base + "request", headers={"User": "a"}, json=body(reason="light the lamp"))
        assert response.status == 200 and not (await response.json())["advanced"]
        assert (await client.post(base + "offer", headers={"User": "a"}, json=body(consequence="alarm"))).status == 403
        assert (await client.post(base + "offer", headers={"User": "gm"}, json=body(consequence="alarm"))).status == 200
        process.assert_not_called()
        response = await client.post(base + "confirm", headers={"User": "a"}, json=body())
        assert response.status == 200 and (await response.json())["advanced"]
        process.assert_awaited_once()
        refreshed = await registry.load(inst.game_key)
        assert checks.last_checks(refreshed)[0]["push"]["original"]["roll"] == 60
