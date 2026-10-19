"""Owner gate and query forwarding for the Lorebook usage route."""

from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.webui.routes.auth import ACCESS_PASSWORD_CONFIGURED_KEY
from src.webui.routes.lorebooks import register_lorebooks


class _Api:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def lorebook_usage_summary(self, game_key: str, viewer: str):
        self.calls.append((game_key, viewer))
        return {
            "ok": True,
            "library": {"total": 0, "enabled": 0, "disabled": 0, "books": []},
            "game": {
                "status": "none", "game_key": "", "world_id": "", "world_name": "",
                "count": None, "books": [],
            },
        }


@web.middleware
async def _auth_middleware(request: web.Request, handler):
    request[ACCESS_PASSWORD_CONFIGURED_KEY] = True
    request["owner_authenticated"] = request.headers.get("X-Owner") == "1"
    return await handler(request)


def _build_app(api: _Api) -> web.Application:
    app = web.Application(middlewares=[_auth_middleware])
    app["api"] = api
    register_lorebooks(app)
    return app


@pytest.mark.asyncio
async def test_usage_requires_owner_and_forwards_game_viewer_queries() -> None:
    api = _Api()
    async with TestClient(TestServer(_build_app(api))) as client:
        denied = await client.get("/api/lorebooks/usage?game_key=g1&viewer=party")
        response = await client.get(
            "/api/lorebooks/usage?game_key=g1&viewer=party",
            headers={"X-Owner": "1"},
        )
        body = await response.json()

    assert denied.status == 403
    assert response.status == 200
    assert body["ok"] is True
    assert api.calls == [("g1", "party")]


@pytest.mark.asyncio
async def test_usage_route_is_registered_before_dynamic_book_routes() -> None:
    api = _Api()
    async with TestClient(TestServer(_build_app(api))) as client:
        response = await client.get("/api/lorebooks/usage", headers={"X-Owner": "1"})

    assert response.status == 200
    assert api.calls == [("", "gm")]
