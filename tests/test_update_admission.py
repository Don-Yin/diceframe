import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.webui.update_admission import update_admission
from tests.test_docker_version_data import installation
from src.docker_launcher.data_versions import prepare_version_data


@pytest.mark.asyncio
async def test_business_writes_wait_for_commit_and_auth_remains_available(tmp_path, monkeypatch):
    _, runtime, app_dir, env = installation(tmp_path)
    prepare_version_data(app_dir, env)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    calls = []

    async def write(request):
        calls.append(request.path)
        return web.json_response({"ok": True})

    app = web.Application(middlewares=[update_admission])
    app.router.add_post("/api/games/action", write)
    app.router.add_post("/api/login", write)
    async with TestClient(TestServer(app)) as client:
        response = await client.post("/api/games/action")
        assert response.status == 503
        assert (await response.json())["error_code"] == "UPDATE_VALIDATING"
        assert calls == []
        assert (await client.post("/api/login")).status == 200
        (runtime / "current.json").write_text(json.dumps({"relative_dir": "docker-versions/v3.0.0"}))
        assert (await client.post("/api/games/action")).status == 200
        assert calls[-1] == "/api/games/action"
