import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.webui.routes.auth import ACCESS_PASSWORD_CONFIGURED_KEY
from tests.test_module_install_hardening import _make_api


@pytest.mark.asyncio
async def test_content_review_routes_require_owner_and_save_reviewed_text(tmp_path):
    from src.webui.routes.content_review import register
    api, _host, store = _make_api(tmp_path / "data")

    @web.middleware
    async def identity(request, handler):
        request[ACCESS_PASSWORD_CONFIGURED_KEY] = True
        request["owner_authenticated"] = request.headers.get("X-Test-Owner") == "yes"
        return await handler(request)

    app = web.Application(middlewares=[identity])
    app["api"] = api
    register(app)
    async with TestClient(TestServer(app)) as client:
        try:
            assert (await client.post("/api/content-review/preview", data="not-json")).status == 403
            headers = {"X-Test-Owner": "yes"}
            response = await client.post("/api/content-review/preview", json={"text": "# Note\nReviewed text", "filename": "note.md", "language": "en"}, headers=headers)
            assert response.status == 200
            checked = await response.json()
            body = {**checked["draft"], "reviewed": True, "plan_digest": checked["plan_digest"]}
            assert (await client.post("/api/content-review/commit", json=body)).status == 403
            assert not store.list_lorebooks()
            response = await client.post("/api/content-review/commit", json=body, headers=headers)
            assert response.status == 200 and (await response.json())["ok"]
            assert len(store.list_lorebooks()) == 1
        finally:
            store.close()
