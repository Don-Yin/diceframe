from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.webui.cors import cors_middleware, cors_response_prepare, parse_cors_origins
from src.webui.config_update import prepare_config_update
from src.webui.session import SessionManager, session_middleware


def test_parse_cors_origins_rejects_wildcards_and_paths():
    assert parse_cors_origins("https://play.example.com, https://other.example.com/") == {
        "https://play.example.com",
        "https://other.example.com",
    }
    assert parse_cors_origins("*, https://play.example.com") == {"https://play.example.com"}
    assert parse_cors_origins("https://play.example.com/path") == set()


def test_cors_config_normalizes_valid_origins_and_rejects_invalid_values():
    prepared = prepare_config_update(
        {},
        {"web_cors_origins": "https://play.example.com/, http://localhost:5173"},
    )
    assert prepared.error == ""
    assert prepared.state["web_cors_origins"] == "http://localhost:5173, https://play.example.com"

    invalid = prepare_config_update({}, {"web_cors_origins": "*"})
    assert "完整的 http(s) Origin" in invalid.error


async def _ok(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def _stream(request: web.Request) -> web.StreamResponse:
    response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
    await response.prepare(request)
    await response.write(b"data: ready\n\n")
    await response.write_eof()
    return response


@pytest.mark.asyncio
async def test_cors_preflight_and_credentials_cookie(tmp_path):
    app = web.Application(middlewares=[cors_middleware, session_middleware])
    app["cors_origins"] = frozenset({"https://play.example.com"})
    app["session_manager"] = SessionManager(tmp_path)
    app.router.add_route("*", "/api/config", _ok)

    async with TestClient(TestServer(app)) as client:
        preflight = await client.options(
            "/api/config",
            headers={
                "Origin": "https://play.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        assert preflight.status == 204
        assert preflight.headers["Access-Control-Allow-Origin"] == "https://play.example.com"
        assert preflight.headers["Access-Control-Allow-Credentials"] == "true"
        # A standalone frontend's share players send their seat credential as a header.
        allowed = {
            part.strip().lower()
            for part in preflight.headers["Access-Control-Allow-Headers"].split(",")
        }
        assert "x-seat-token" in allowed

        response = await client.get("/api/config", headers={"Origin": "https://play.example.com"})
        assert response.status == 200
        assert response.headers["Access-Control-Allow-Origin"] == "https://play.example.com"
        assert "SameSite=None" in response.headers["Set-Cookie"]
        assert "Secure" in response.headers["Set-Cookie"]


@pytest.mark.asyncio
async def test_cors_headers_are_present_when_stream_prepares_before_middleware_returns():
    app = web.Application(middlewares=[cors_middleware])
    app["cors_origins"] = frozenset({"https://play.example.com"})
    app.on_response_prepare.append(cors_response_prepare)
    app.router.add_route("GET", "/events", _stream)

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/events", headers={"Origin": "https://play.example.com"})
        assert response.status == 200
        assert response.headers["Access-Control-Allow-Origin"] == "https://play.example.com"


@pytest.mark.asyncio
async def test_cors_response_keeps_request_start_origin_when_handler_changes_allowlist():
    async def change_allowlist(request: web.Request) -> web.Response:
        request.app["cors_origins"] = frozenset({"https://next.example.com"})
        return web.json_response({"ok": True})

    app = web.Application(middlewares=[cors_middleware])
    app["cors_origins"] = frozenset({"https://play.example.com"})
    app.on_response_prepare.append(cors_response_prepare)
    app.router.add_post("/api/config", change_allowlist)

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/config",
            headers={"Origin": "https://play.example.com"},
        )
        assert response.status == 200
        assert response.headers["Access-Control-Allow-Origin"] == "https://play.example.com"
        assert response.headers["Vary"] == "Origin"
