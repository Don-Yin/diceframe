import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from src.webui.routes.auth import ACCESS_PASSWORD_CONFIGURED_KEY
from tests.test_module_install_hardening import _make_api, _zip_payload, MODULE_ID
from tests.test_module_resources import module_with_image


@pytest.mark.asyncio
async def test_module_resource_routes_require_owner_before_body_or_gm_content(tmp_path):
    from src.webui.routes.module_resources import register
    api, _host, store = _make_api(tmp_path / "data")
    await api.import_module(_zip_payload(module_with_image()))

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
            root = f"/api/modules/{MODULE_ID}/resources"
            assert (await client.get(root)).status == 403
            assert (await client.post(root + "/fork/preview", data="invalid")).status == 403
            headers = {"X-Test-Owner": "yes"}
            result = await (await client.get(root, headers=headers)).json()
            resource = next(row for row in result["resources"] if row["kind"] == "character_template")
            response = await client.post(root + "/fork/preview", json={"selector": resource["selector"], "language": "en"}, headers=headers)
            assert response.status == 200
            checked = await response.json()
            body = {**checked["draft"], "reviewed": True, "plan_digest": checked["plan_digest"]}
            response = await client.post(root + "/fork/commit", json=body, headers=headers)
            assert response.status == 200 and (await response.json())["ok"]
        finally:
            store.close()
