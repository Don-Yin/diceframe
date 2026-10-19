"""World definition route contract: owner gate, bounded projection and updates."""

from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.webui.routes.auth import ACCESS_PASSWORD_CONFIGURED_KEY
from src.webui.routes.worlds import api_world_create, api_world_definition, api_world_update


class _Api:
    def __init__(self) -> None:
        self.update_calls: list[dict] = []
        self.create_calls: list[dict] = []

    def create_world(self, *args, **kwargs):
        self.create_calls.append({"args": args, "kwargs": kwargs})
        return {"ok": True, "world_id": "new-world"}

    def get_world_definition(self, world_id: str, language: str):
        return {
            "ok": True,
            "world": {
                "world_id": world_id,
                "world_name": "World",
                "description": "Summary",
                "world_setting": "Setting",
                "starter_scene": "Opening",
                "language": language or "zh-CN",
                "source": "user",
                "editable": True,
            },
        }

    def update_world(self, *args, **kwargs):
        self.update_calls.append({"args": args, "kwargs": kwargs})
        return {"ok": True}


@web.middleware
async def _auth_middleware(request: web.Request, handler):
    request[ACCESS_PASSWORD_CONFIGURED_KEY] = True
    request["owner_authenticated"] = request.headers.get("X-Owner") == "1"
    return await handler(request)


def _build_app(api: _Api) -> web.Application:
    app = web.Application(middlewares=[_auth_middleware])
    app["api"] = api
    app.router.add_post("/api/worlds", api_world_create)
    app.router.add_get("/api/worlds/{world_id}/definition", api_world_definition)
    app.router.add_put("/api/worlds/{world_id}", api_world_update)
    return app


@pytest.mark.asyncio
async def test_world_create_validates_and_forwards_independent_narrative() -> None:
    api = _Api()
    async with TestClient(TestServer(_build_app(api))) as client:
        denied = await client.post("/api/worlds", json={"name": "World"})
        assert denied.status == 403
        for payload in ([], {"world_setting": None}, {"starter_scene": "x" * 8193}):
            invalid = await client.post("/api/worlds", json=payload, headers={"X-Owner": "1"})
            assert invalid.status == 400
        assert api.create_calls == []
        valid = await client.post("/api/worlds", json={
            "name": "World", "description": "Intro", "language": "en",
            "world_setting": "Full setting", "starter_scene": "",
        }, headers={"X-Owner": "1"})
        assert valid.status == 200
        assert api.create_calls == [{"args": ("World", "Intro", "en"), "kwargs": {"world_setting": "Full setting", "starter_scene": ""}}]


@pytest.mark.asyncio
async def test_definition_requires_owner_and_excludes_private_fields() -> None:
    api = _Api()
    async with TestClient(TestServer(_build_app(api))) as client:
        denied = await client.get("/api/worlds/world-1/definition")
        response = await client.get(
            "/api/worlds/world-1/definition?language=zh-CN",
            headers={"X-Owner": "1"},
        )
        body = await response.json()

    assert denied.status == 403
    assert response.status == 200
    assert set(body["world"]) == {
        "world_id", "world_name", "description", "world_setting",
        "starter_scene", "language", "source", "editable",
    }
    assert "starter_lorebook" not in body["world"]


@pytest.mark.asyncio
async def test_world_update_rejects_null_or_oversized_narrative_before_write() -> None:
    api = _Api()
    async with TestClient(TestServer(_build_app(api))) as client:
        denied = await client.put(
            "/api/worlds/world-1", json={"name": "World"},
        )
        null_response = await client.put(
            "/api/worlds/world-1", json={"name": "World", "world_setting": None},
            headers={"X-Owner": "1"},
        )
        long_response = await client.put(
            "/api/worlds/world-1", json={"name": "World", "starter_scene": "x" * 8193},
            headers={"X-Owner": "1"},
        )

    assert denied.status == 403
    assert null_response.status == 400
    assert long_response.status == 400
    assert api.update_calls == []


@pytest.mark.asyncio
async def test_world_update_forwards_valid_empty_and_omitted_narrative_fields() -> None:
    api = _Api()
    async with TestClient(TestServer(_build_app(api))) as client:
        valid = await client.put(
            "/api/worlds/world-1",
            json={
                "name": "World", "description": "Summary", "language": "en",
                "world_setting": "Full setting", "starter_scene": "",
            },
            headers={"X-Owner": "1"},
        )
        omitted = await client.put(
            "/api/worlds/world-1",
            json={"name": "World", "description": "Summary", "language": "en"},
            headers={"X-Owner": "1"},
        )

    assert valid.status == 200
    assert omitted.status == 200
    assert api.update_calls[0]["kwargs"] == {
        "world_setting": "Full setting", "starter_scene": "",
    }
    assert api.update_calls[1]["kwargs"] == {}
