"""连接安全 API 事务契约：prepare / activate / disable / regenerate。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.webui.routes import security as security_routes
from src.webui.services.security import SecurityTransportService
from src.web_transport import build_server_transport, parse_web_transport


def _make_app(tmp_path, state=None):
    state = state if state is not None else {"web_transport": {}}
    saved_files = []
    transport = build_server_transport(parse_web_transport(state.get("web_transport") or {}), tmp_path, 18000)

    def save_config():
        saved_files.append(json.dumps(state))

    service = SecurityTransportService(state, save_config, tmp_path, transport)
    control = {"boot_id": "boot-test", "restart_requested": False, "restart_task": None}
    app = {"security_transport": service, "runtime_control": control}
    return app, state, control, saved_files


def _request(app, body=None, confirm=True, host="127.0.0.1:18000"):
    headers = {"Host": host}
    if confirm:
        headers["X-TRPG-Confirm"] = "true"

    async def json_body():
        return body if body is not None else {}

    return SimpleNamespace(app=app, headers=headers, json=json_body)


def _payload(response) -> dict:
    return json.loads(response.text)


def test_target_origin_uses_certificate_address_and_keeps_game_port():
    request = SimpleNamespace(headers={"Host": "203.0.113.24:18000"})

    assert (
        security_routes._target_origin(request, "https", "game.example.com")
        == "https://game.example.com:18000"
    )


def test_target_origin_brackets_ipv6_certificate_address():
    request = SimpleNamespace(headers={"Host": "diceframe.local:9876"})

    assert (
        security_routes._target_origin(request, "https", "2001:db8::20")
        == "https://[2001:db8::20]:9876"
    )


async def _consume_restart(control) -> None:
    task = control.get("restart_task")
    if task is not None:
        control["restart_task"] = None
        # 不真正触发 SIGINT：替换为已完成的假任务即可。
        task.cancel()


@pytest.mark.asyncio
async def test_get_status_reports_http_by_default(tmp_path):
    app, _, _, _ = _make_app(tmp_path)
    response = await security_routes.api_security_transport_get(SimpleNamespace(app=app))
    payload = _payload(response)
    assert payload["ok"] is True
    assert payload["tls_mode"] == "off"
    assert payload["scheme"] == "http"
    assert "certificate" not in payload or payload.get("certificate") is None


@pytest.mark.asyncio
async def test_get_status_returns_editable_acme_settings_without_key_material(tmp_path):
    app, _, _, _ = _make_app(
        tmp_path,
        {
            "web_transport": {
                "tls_mode": "lets_encrypt",
                "acme": {
                    "identifier_type": "dns",
                    "identifier": "game.example.com",
                    "contact_email": "owner@example.com",
                    "http_challenge_port": 8080,
                },
            }
        },
    )
    response = await security_routes.api_security_transport_get(SimpleNamespace(app=app))
    payload = _payload(response)

    assert payload["acme"]["identifier"] == "game.example.com"
    assert payload["acme"]["contact_email"] == "owner@example.com"
    assert payload["acme"]["http_challenge_port"] == 8080
    assert "account_key" not in payload["acme"]
    assert "key_path" not in payload["acme"]


@pytest.mark.asyncio
async def test_prepare_without_confirmation_is_rejected(tmp_path):
    app, _, control, _ = _make_app(tmp_path)
    response = await security_routes.api_security_transport_prepare(_request(app, {"mode": "self_signed"}, confirm=False))
    assert response.status == 403
    assert control["restart_requested"] is False


@pytest.mark.asyncio
async def test_prepare_lets_encrypt_requires_identifier(tmp_path):
    app, _, _, _ = _make_app(tmp_path)
    response = await security_routes.api_security_transport_prepare(_request(app, {"mode": "lets_encrypt"}))
    assert response.status == 400
    assert "标识不能为空" in _payload(response)["error"]


@pytest.mark.asyncio
async def test_prepare_lets_encrypt_persists_canonical_acme_candidate(tmp_path, monkeypatch):
    app, _, _, _ = _make_app(tmp_path)
    service = app["security_transport"]
    signed = service._self_signed_provider.prepare()

    async def fake_issue(request):
        assert request.identifier.type == "dns"
        assert request.identifier.value == "game.example.com"
        return SimpleNamespace(prepared=signed, warnings=[])

    monkeypatch.setattr(service._acme_provider, "issue", fake_issue)
    response = await security_routes.api_security_transport_prepare(
        _request(
            app,
            {
                "mode": "lets_encrypt",
                "acme": {
                    "identifier_type": "dns",
                    "identifier": "Game.Example.COM.",
                    "contact_email": "owner@example.com",
                },
            },
        )
    )
    payload = _payload(response)
    assert payload["ok"] is True
    assert payload["mode"] == "lets_encrypt"
    assert payload["token"]
    assert payload["certificate"]["fingerprint_sha256"]
    prep = service._preparations[payload["token"]]
    assert prep["config"]["acme"]["identifier"] == "game.example.com"


@pytest.mark.asyncio
async def test_prepare_lets_encrypt_converts_network_failure_to_actionable_error(tmp_path, monkeypatch):
    app, _, _, _ = _make_app(tmp_path)
    service = app["security_transport"]

    async def failed_issue(_request):
        raise __import__("aiohttp").ClientConnectionError("CA unavailable")

    monkeypatch.setattr(service._acme_provider, "issue", failed_issue)
    response = await security_routes.api_security_transport_prepare(
        _request(
            app,
            {"mode": "lets_encrypt", "acme": {"identifier_type": "dns", "identifier": "game.example.com"}},
        )
    )
    assert response.status == 400
    assert "证书申请失败" in _payload(response)["error"]


@pytest.mark.asyncio
async def test_prepare_off_mode_directs_to_disable(tmp_path):
    app, _, _, _ = _make_app(tmp_path)
    response = await security_routes.api_security_transport_prepare(_request(app, {"mode": "off"}))
    assert response.status == 400
    assert "disable" in _payload(response)["error"]


@pytest.mark.asyncio
async def test_activate_without_valid_token_fails_and_keeps_mode(tmp_path):
    app, state, _, _ = _make_app(tmp_path)
    response = await security_routes.api_security_transport_activate(_request(app, {"token": "missing"}))
    assert response.status == 400
    assert state["web_transport"] == {}


@pytest.mark.asyncio
async def test_full_enable_flow_persists_config_and_schedules_restart(tmp_path):
    app, state, control, saved = _make_app(tmp_path)
    prepared = _payload(
        await security_routes.api_security_transport_prepare(_request(app, {"mode": "self_signed"}))
    )
    assert prepared["ok"] is True
    assert prepared["certificate"]["fingerprint_sha256"]
    token = prepared["token"]

    activated = _payload(
        await security_routes.api_security_transport_activate(_request(app, {"token": token}))
    )
    assert activated["ok"] is True
    assert activated["tls_mode"] == "self_signed"
    assert activated["target_origin"].startswith("https://")
    assert state["web_transport"] == {"tls_mode": "self_signed"}
    assert saved, "配置必须落盘"
    assert control["restart_requested"] is True
    await _consume_restart(control)

    # token 一次性：重复 activate 失败。
    replay = await security_routes.api_security_transport_activate(_request(app, {"token": token}))
    assert replay.status == 400


@pytest.mark.asyncio
async def test_disable_keeps_certificate_files_and_returns_http_origin(tmp_path):
    app, state, control, _ = _make_app(
        tmp_path, {"web_transport": {"tls_mode": "self_signed"}}
    )
    provider = app["security_transport"]._provider
    prepared = provider.prepare()
    assert prepared.cert_path.exists()

    response = await security_routes.api_security_transport_disable(_request(app))
    payload = _payload(response)
    assert payload["ok"] is True
    assert payload["target_origin"].startswith("http://")
    assert state["web_transport"] == {"tls_mode": "off"}
    # 关闭不删除证书与指纹文件。
    assert prepared.cert_path.exists()
    assert prepared.key_path.exists()
    assert control["restart_requested"] is True
    await _consume_restart(control)


@pytest.mark.asyncio
async def test_regenerate_changes_fingerprint_and_requires_restart_when_active(tmp_path):
    app, _, control, _ = _make_app(
        tmp_path, {"web_transport": {"tls_mode": "self_signed"}}
    )
    service = app["security_transport"]
    first = service._provider.prepare()

    response = await security_routes.api_security_self_signed_regenerate(_request(app))
    payload = _payload(response)
    assert payload["ok"] is True
    assert payload["restart_required"] is True
    assert payload["previous_fingerprint"] == first.metadata.fingerprint_sha256
    assert payload["certificate"]["fingerprint_sha256"] != first.metadata.fingerprint_sha256
    # regenerate 本身不触发重启：由前端在确认后显式重启。
    assert control["restart_requested"] is False


@pytest.mark.asyncio
async def test_env_tls_mode_blocks_conflicting_activation(tmp_path, monkeypatch):
    monkeypatch.setenv("TRPG_TLS_MODE", "off")
    app, state, _, _ = _make_app(tmp_path)
    response = await security_routes.api_security_transport_prepare(_request(app, {"mode": "self_signed"}))
    assert response.status == 400
    assert "环境变量" in _payload(response)["error"]
    assert state["web_transport"] == {}
