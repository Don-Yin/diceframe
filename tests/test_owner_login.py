import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import web_server
from src.webui.access_password import hash_access_password
from src.webui.login_audit import LOGIN_AUDIT_KEY, LoginAuditStore
from src.webui.routes.auth import register_auth


def _login_app(tmp_path) -> web.Application:
    app = web.Application(middlewares=[web_server.auth_middleware])
    app[LOGIN_AUDIT_KEY] = LoginAuditStore(tmp_path)
    register_auth(app)
    return app


@pytest.mark.asyncio
async def test_owner_login_records_success_and_failure(tmp_path, monkeypatch):
    monkeypatch.setitem(
        web_server.STATE,
        "access_token",
        hash_access_password("correct-password"),
    )
    app = _login_app(tmp_path)

    async with TestClient(TestServer(app)) as client:
        failed = await client.post(
            "/api/login",
            headers={"Authorization": "Bearer wrong-password"},
        )
        succeeded = await client.post(
            "/api/login",
            headers={"Authorization": "Bearer correct-password"},
        )
        unauthorized_history = await client.get("/api/login-history")
        history = await client.get(
            "/api/login-history",
            headers={"Authorization": "Bearer correct-password"},
        )
        history_body = await history.json()

    assert failed.status == 401
    assert succeeded.status == 200
    assert unauthorized_history.status == 401
    assert history.status == 200
    assert history.headers["Cache-Control"] == "no-store"
    entries = history_body["entries"]
    assert [entry["success"] for entry in entries] == [True, False]
    assert all(entry["ip"] for entry in entries)


@pytest.mark.asyncio
async def test_login_succeeds_when_access_password_is_not_configured(tmp_path, monkeypatch):
    monkeypatch.setitem(web_server.STATE, "access_token", "")
    app = _login_app(tmp_path)

    async with TestClient(TestServer(app)) as client:
        response = await client.post("/api/login")

    assert response.status == 200


@pytest.mark.asyncio
async def test_stateless_ruleset_builder_is_public_but_rule_management_is_not(
    tmp_path, monkeypatch,
):
    monkeypatch.setitem(
        web_server.STATE,
        "access_token",
        hash_access_password("correct-password"),
    )
    app = _login_app(tmp_path)

    async def ok(_request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app.router.add_get("/api/rules/{rule_id}/experience", ok)
    for action in ("choices", "validate", "derive", "finalize"):
        app.router.add_post(f"/api/rules/{{rule_id}}/builder/{action}", ok)
    app.router.add_get("/api/rules/{rule_id}/progression", ok)
    for action in ("preview", "apply"):
        app.router.add_post(f"/api/rules/{{rule_id}}/advancement/{action}", ok)
    app.router.add_post("/api/rules/{rule_id}/rest/resolve", ok)
    app.router.add_get("/api/rules/{rule_id}", ok)

    async with TestClient(TestServer(app)) as client:
        experience = await client.get("/api/rules/dnd2024_srd/experience")
        builder_statuses = [
            (await client.post(f"/api/rules/dnd2024_srd/builder/{action}")).status
            for action in ("choices", "validate", "derive", "finalize")
        ]
        progression = await client.get("/api/rules/dnd2024_srd/progression")
        advancement_statuses = [
            (await client.post(f"/api/rules/dnd2024_srd/advancement/{action}")).status
            for action in ("preview", "apply")
        ]
        rest = await client.post("/api/rules/dnd2024_srd/rest/resolve")
        rule_detail = await client.get("/api/rules/dnd2024_srd")

    assert experience.status == 200
    assert builder_statuses == [200, 200, 200, 200]
    assert progression.status == 200
    assert advancement_statuses == [200, 200]
    assert rest.status == 200
    assert rule_detail.status == 401
