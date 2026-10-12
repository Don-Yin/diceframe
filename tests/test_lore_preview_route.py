"""世界书视角预览路由测试：参数透传与状态码透传。"""

from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.webui.routes.worlds import api_lorebook_preview


class _Api:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def preview_lore_visibility(self, world_id: str, viewer: str, game_key: str | None):
        self.calls.append((world_id, viewer, game_key))
        if not viewer:
            return {"status": 400, "payload": {"ok": False, "code": "INVALID_VIEWER", "error": "视角无效"}}
        return {
            "status": 200,
            "payload": {
                "ok": True,
                "world_id": world_id,
                "viewer": {"kind": viewer, "uid": "", "name": ""},
                "projections": {},
                "summary": {"total": 0, "visible": 0, "public": 0, "character_only": 0, "gm_secret": 0},
            },
        }


def _build_app(api: _Api) -> web.Application:
    app = web.Application()
    app["api"] = api
    app.router.add_get("/api/lorebook/{world_id}/preview", api_lorebook_preview)
    return app


@pytest.mark.asyncio
async def test_preview_passes_viewer_and_game_key() -> None:
    api = _Api()
    async with TestClient(TestServer(_build_app(api))) as client:
        response = await client.get("/api/lorebook/w1/preview?viewer=u1&game_key=g1")
        body = await response.json()

    assert response.status == 200
    assert body["ok"] is True
    assert body["world_id"] == "w1"
    assert api.calls == [("w1", "u1", "g1")]


@pytest.mark.asyncio
async def test_preview_without_game_key_passes_none() -> None:
    api = _Api()
    async with TestClient(TestServer(_build_app(api))) as client:
        response = await client.get("/api/lorebook/w1/preview?viewer=gm")

    assert response.status == 200
    assert api.calls == [("w1", "gm", None)]


@pytest.mark.asyncio
async def test_preview_propagates_error_status() -> None:
    api = _Api()
    async with TestClient(TestServer(_build_app(api))) as client:
        response = await client.get("/api/lorebook/w1/preview")
        body = await response.json()

    assert response.status == 400
    assert body["code"] == "INVALID_VIEWER"
