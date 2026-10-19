from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from src.bots.bridge_core.client import DiceFrameClient
from src.bots.bridge_core.errors import DiceFrameHTTPError


@pytest.mark.asyncio
async def test_scene_download_sends_game_and_actor_credentials_to_fixed_route(tmp_path):
    requests = []

    async def image(request):
        requests.append((request.match_info["game_key"], dict(request.headers)))
        return web.Response(body=b"image-bytes", content_type="image/webp")

    app = web.Application()
    app.router.add_get("/api/games/{game_key}/scene-image", image)
    async with TestServer(app) as server:
        client = DiceFrameClient(str(server.make_url("")), "synthetic-token")
        try:
            path = await client.download_scene_image("web|room|bot", "player", tmp_path)
        finally:
            await client.close()
    assert path.suffix == ".webp"
    assert path.read_bytes() == b"image-bytes"
    assert requests[0][0] == "web|room|bot"
    assert requests[0][1]["X-Bot-Actor"] == "player"
    assert requests[0][1]["X-Bot-Token"] == "synthetic-token"


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "content_type", "body"), [
    (403, "application/json", b"denied"),
    (302, "image/png", b"redirect"),
    (200, "text/html", b"not an image"),
    (200, "image/png", b""),
    (200, "image/png", b"x" * (10 * 1024 * 1024 + 1)),
], ids=["denied", "redirect", "html", "empty", "oversize"])
async def test_scene_download_rejects_unauthorized_redirect_and_invalid_payload(tmp_path, status, content_type, body):
    async def image(_request):
        return web.Response(status=status, body=body, content_type=content_type, headers={"Location": "/unexpected"})

    async def unexpected(_request):
        pytest.fail("must not follow a redirect with Bot credentials")

    app = web.Application()
    app.router.add_get("/api/games/{game_key}/scene-image", image)
    app.router.add_get("/unexpected", unexpected)
    async with TestServer(app) as server:
        client = DiceFrameClient(str(server.make_url("")), "synthetic-token")
        try:
            with pytest.raises(DiceFrameHTTPError):
                await client.download_scene_image("room", "player", tmp_path)
        finally:
            await client.close()
    assert not list(tmp_path.iterdir())
