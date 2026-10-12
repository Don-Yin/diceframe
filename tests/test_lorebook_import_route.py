from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.webui.routes.lorebooks import register_lorebooks


class _Api:
    def __init__(self) -> None:
        self.list_calls: list[tuple[str, str]] = []

    def list_lorebooks(self, world_id="", game_key=""):
        # 路由必须把 world_id 与 game_key 都转发下去：当前游戏 / 角色范围的 Book
        # 否则永远不会出现在管理列表里。
        self.list_calls.append((world_id, game_key))
        return {"books": [{"id": "world:w1", "name": "Demo", "primary": True, "scope": "world"}]}

    def preview_lorebook_import(self, payload):
        return {"format": "sillytavern", "book": {"name": "Demo"}, "counts": {"entries": 1, "mapped": 1, "warnings": 0, "unsupported": 0}, "warnings": []}

    def commit_lorebook_import(self, payload, binding=None, book_id=None):
        return {"ok": True, "book_id": book_id or "generated", "entries": 1, "warnings": []}


def _app(api: "_Api | None" = None) -> web.Application:
    app = web.Application()
    app["api"] = api or _Api()
    register_lorebooks(app)
    return app


@pytest.mark.asyncio
async def test_lorebook_import_preview_and_commit_routes():
    api = _Api()
    async with TestClient(TestServer(_app(api))) as client:
        books = await client.get("/api/lorebooks?world_id=w1&game_key=web|room|gm")
        assert api.list_calls == [("w1", "web|room|gm")]
        books_body = await books.json()
        preview = await client.post("/api/lorebooks/import/preview", json={"entries": []})
        preview_body = await preview.json()
        committed = await client.post(
            "/api/lorebooks/import",
            json={"payload": {"entries": []}, "book_id": "world:w1"},
        )
        committed_body = await committed.json()

    assert books.status == 200
    assert books_body["books"][0]["id"] == "world:w1"
    assert preview.status == 200
    assert preview_body["format"] == "sillytavern"
    assert committed.status == 200
    assert committed_body["book_id"] == "world:w1"


@pytest.mark.asyncio
async def test_lorebook_import_routes_reject_invalid_shapes():
    async with TestClient(TestServer(_app())) as client:
        preview = await client.post("/api/lorebooks/import/preview", json=[])
        committed = await client.post("/api/lorebooks/import", json={"payload": []})

    assert preview.status == 400
    assert committed.status == 400
