"""扫码配对与设备令牌的凭据边界。

保护的契约：
- 配对码一次性、短 TTL，过期/复用/伪造都拿不到任何凭据；
- 签发端点必须是 owner 会话（配置了访问密码时）才能调用——否则任何
  局域网匿名客户端都能自助签发再兑换，整套访问密码形同虚设；
- 兑换给出的是独立设备令牌，访问密码明文永不离开服务端；
- 设备令牌与访问密码平级可用，且可以逐台吊销（丢手机场景）；
- 令牌只以摘要落盘，设备清单不泄露任何可鉴权的字段；
- 兑换尝试写入与 /api/login 同一份登录审计。
"""

import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import web_server
from src.webui.access_password import hash_access_password
from src.webui.device_tokens import DEVICE_TOKENS_KEY, DeviceTokenStore
from src.webui.login_audit import LOGIN_AUDIT_KEY, LoginAuditStore
from src.webui.pairing import PairingCodeStore, PairingService
from src.webui.routes.auth import register_auth
from src.webui.routes.pairing import PAIRING_SERVICE_KEY, register_pairing


CONFIRM = {"X-TRPG-Confirm": "true"}
PASSWORD = "correct-password"


def _pairing_app(tmp_path, *, store: PairingCodeStore | None = None) -> web.Application:
    app = web.Application(middlewares=[web_server.auth_middleware])
    app[LOGIN_AUDIT_KEY] = LoginAuditStore(tmp_path)
    app[DEVICE_TOKENS_KEY] = DeviceTokenStore(tmp_path)
    app[PAIRING_SERVICE_KEY] = PairingService(
        app[DEVICE_TOKENS_KEY],
        store=store or PairingCodeStore(),
        audit=app[LOGIN_AUDIT_KEY],
    )
    register_auth(app)
    register_pairing(app)
    return app


def _owner(password: str = PASSWORD) -> dict:
    return {"Authorization": f"Bearer {password}", **CONFIRM}


def _with_password(monkeypatch) -> None:
    monkeypatch.setitem(web_server.STATE, "access_token", hash_access_password(PASSWORD))


async def _claim_device(client, *, label: str = "") -> str:
    issued = await client.post("/api/pairing", headers=_owner())
    code = (await issued.json())["code"]
    claimed = await client.post(
        "/api/pairing/claim",
        json={"code": code, "label": label},
        headers=CONFIRM,
    )
    return (await claimed.json())["device_token"]


@pytest.mark.asyncio
async def test_pairing_code_exchanges_once_for_a_device_token(tmp_path, monkeypatch):
    _with_password(monkeypatch)
    app = _pairing_app(tmp_path)

    async with TestClient(TestServer(app)) as client:
        issued = await client.post("/api/pairing", headers=_owner())
        issued_body = await issued.json()
        code = issued_body["code"]
        first = await client.post(
            "/api/pairing/claim", json={"code": code}, headers=CONFIRM
        )
        first_body = await first.json()
        replay = await client.post(
            "/api/pairing/claim", json={"code": code}, headers=CONFIRM
        )
        replay_body = await replay.json()

    assert issued.status == 200
    assert issued_body["expires_in"] > 0
    assert issued.headers["Cache-Control"] == "no-store"
    assert first.status == 200
    assert first_body["device_token"]
    # 访问密码明文永不离开服务端：兑换响应里不能出现它，也不能出现哈希。
    assert PASSWORD not in json.dumps(first_body)
    assert "access_password" not in first_body
    assert replay.status == 401
    assert replay_body["error_code"] == "PAIRING_CODE_INVALID"


@pytest.mark.asyncio
async def test_device_token_authenticates_as_owner_and_can_be_revoked(
    tmp_path, monkeypatch
):
    _with_password(monkeypatch)
    app = _pairing_app(tmp_path)

    async with TestClient(TestServer(app)) as client:
        token = await _claim_device(client, label="GM 的手机")
        as_owner = await client.post(
            "/api/login", headers={"Authorization": f"Bearer {token}"}
        )
        listed = await client.get("/api/devices", headers=_owner())
        devices = (await listed.json())["devices"]
        revoked = await client.delete(
            f"/api/devices/{devices[0]['id']}", headers=_owner()
        )
        after_revoke = await client.post(
            "/api/login", headers={"Authorization": f"Bearer {token}"}
        )

    assert as_owner.status == 200
    assert [device["label"] for device in devices] == ["GM 的手机"]
    # 清单只用于展示与吊销，不得带出任何可用来鉴权的字段。
    # install_id 是内容同步的来源标识（客户端自报，非凭据），可以展示。
    assert set(devices[0]) == {"id", "label", "created_at", "last_seen_at", "install_id"}
    assert revoked.status == 200
    assert after_revoke.status == 401


@pytest.mark.asyncio
async def test_device_token_grants_no_access_after_revoke_all(tmp_path, monkeypatch):
    _with_password(monkeypatch)
    app = _pairing_app(tmp_path)

    async with TestClient(TestServer(app)) as client:
        first = await _claim_device(client)
        second = await _claim_device(client)
        cleared = await client.post("/api/devices/revoke-all", headers=_owner())
        cleared_body = await cleared.json()
        denied = await client.post(
            "/api/login", headers={"Authorization": f"Bearer {first}"}
        )
        also_denied = await client.post(
            "/api/login", headers={"Authorization": f"Bearer {second}"}
        )

    assert cleared_body["revoked"] == 2
    assert denied.status == 401
    assert also_denied.status == 401


@pytest.mark.asyncio
async def test_device_endpoints_reject_anonymous_and_player_callers(
    tmp_path, monkeypatch
):
    _with_password(monkeypatch)
    app = _pairing_app(tmp_path)

    async with TestClient(TestServer(app)) as client:
        issue = await client.post("/api/pairing", headers=CONFIRM)
        wrong_password = await client.post(
            "/api/pairing",
            headers={"Authorization": "Bearer wrong-password", **CONFIRM},
        )
        listing = await client.get("/api/devices")
        revoke = await client.delete("/api/devices/whatever", headers=CONFIRM)
        revoke_all = await client.post("/api/devices/revoke-all", headers=CONFIRM)

    assert issue.status == 401
    assert wrong_password.status == 401
    assert listing.status == 401
    assert revoke.status == 401
    assert revoke_all.status == 401


@pytest.mark.asyncio
async def test_claim_rejects_unknown_and_expired_codes(tmp_path, monkeypatch):
    _with_password(monkeypatch)
    expiring = PairingCodeStore(ttl_seconds=10)
    app = _pairing_app(tmp_path, store=expiring)

    async with TestClient(TestServer(app)) as client:
        issued = await client.post("/api/pairing", headers=_owner())
        code = (await issued.json())["code"]
        # 不等真实时间：把已登记的过期时刻直接推到过去。
        expiring._codes = {digest: 0.0 for digest in expiring._codes}
        stale = await client.post(
            "/api/pairing/claim", json={"code": code}, headers=CONFIRM
        )
        unknown = await client.post(
            "/api/pairing/claim", json={"code": "ZZZZZZZZ"}, headers=CONFIRM
        )
        blank = await client.post("/api/pairing/claim", json={}, headers=CONFIRM)

    assert stale.status == 401
    assert unknown.status == 401
    assert blank.status == 401


@pytest.mark.asyncio
async def test_claim_requires_the_confirmation_header(tmp_path, monkeypatch):
    monkeypatch.setitem(web_server.STATE, "access_token", "")
    app = _pairing_app(tmp_path)

    async with TestClient(TestServer(app)) as client:
        unconfirmed = await client.post("/api/pairing/claim", json={"code": "WHATEVER"})

    assert unconfirmed.status == 403


@pytest.mark.asyncio
async def test_password_free_server_still_pairs(tmp_path, monkeypatch):
    monkeypatch.setitem(web_server.STATE, "access_token", "")
    app = _pairing_app(tmp_path)

    async with TestClient(TestServer(app)) as client:
        issued = await client.post("/api/pairing", headers=CONFIRM)
        code = (await issued.json())["code"]
        claimed = await client.post(
            "/api/pairing/claim", json={"code": code}, headers=CONFIRM
        )
        claimed_body = await claimed.json()

    assert issued.status == 200
    assert claimed.status == 200
    assert claimed_body["device_token"]


@pytest.mark.asyncio
async def test_claim_attempts_land_in_the_login_audit(tmp_path, monkeypatch):
    _with_password(monkeypatch)
    app = _pairing_app(tmp_path)

    async with TestClient(TestServer(app)) as client:
        issued = await client.post("/api/pairing", headers=_owner())
        code = (await issued.json())["code"]
        await client.post("/api/pairing/claim", json={"code": "ZZZZZZZZ"}, headers=CONFIRM)
        await client.post("/api/pairing/claim", json={"code": code}, headers=CONFIRM)
        history = await client.get("/api/login-history", headers=_owner())
        entries = (await history.json())["entries"]

    assert [entry["success"] for entry in entries] == [True, False]


def test_pairing_codes_are_stored_only_as_digests():
    store = PairingCodeStore()
    code = store.issue().code

    assert code not in store._codes
    assert all(len(digest) == 64 for digest in store._codes)
    # 大小写与首尾空白是扫码/手输的正常噪声，不应因此判成无效码。
    assert store.consume(f"  {code.lower()} ") is True


def test_device_tokens_survive_restart_but_never_land_in_plaintext(tmp_path):
    store = DeviceTokenStore(tmp_path)
    token, device = store.issue("平板")

    reloaded = DeviceTokenStore(tmp_path)

    assert token not in store.path.read_text(encoding="utf-8")
    assert reloaded.verify(token) is not None
    assert reloaded.verify(token[:-1] + ("A" if token[-1] != "A" else "B")) is None
    assert [entry["id"] for entry in reloaded.entries()] == [device["id"]]


def test_corrupt_device_file_denies_access_instead_of_trusting_it(tmp_path):
    (tmp_path / "paired_devices.json").write_text("{not json", encoding="utf-8")

    store = DeviceTokenStore(tmp_path)

    assert store.entries() == []
    assert store.verify("anything") is None


class _ConfigRequest:
    """api_config_post 只用到 headers / json() / app，这里按最小面搭壳。"""

    def __init__(self, body: dict, app: dict) -> None:
        self._body = body
        self.headers = CONFIRM
        self.app = app

    async def json(self) -> dict:
        return self._body


def _lockdown_app(tmp_path) -> dict:
    devices = DeviceTokenStore(tmp_path)
    return {
        DEVICE_TOKENS_KEY: devices,
        PAIRING_SERVICE_KEY: PairingService(devices),
    }


def _prepare_config_post(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(web_server, "ACCESS_TOKEN_FILE", tmp_path / "access_token.txt")
    monkeypatch.setattr(web_server, "save_config", lambda: None)
    monkeypatch.setitem(web_server.STATE, "proxy_enabled", False)


@pytest.mark.asyncio
async def test_first_access_password_revokes_passwordless_era_credentials(tmp_path, monkeypatch):
    """免密期任何人都能自助签发配对码；锁门时这批凭据必须一起作废。

    否则「设置访问密码」只挡住了不知道密码的人，却放过了在免密窗口里
    配过对的设备——它们在锁门后依然是 owner。
    """
    _prepare_config_post(tmp_path, monkeypatch)
    monkeypatch.setitem(web_server.STATE, "access_token", "")
    app = _lockdown_app(tmp_path)
    devices, pairing = app[DEVICE_TOKENS_KEY], app[PAIRING_SERVICE_KEY]
    token, _device = devices.issue("免密期配对的手机")
    pending = pairing.store.issue().code

    response = await web_server.api_config_post(
        _ConfigRequest({"access_token": PASSWORD}, app)
    )

    assert response.status == 200
    assert json.loads(response.text)["access_password_changed"] is True
    assert devices.verify(token) is None
    assert devices.entries() == []
    assert pairing.store.consume(pending) is False


@pytest.mark.asyncio
async def test_changing_an_existing_password_keeps_paired_devices(tmp_path, monkeypatch):
    """改密码不吊销设备令牌：两者是平级的独立凭据。

    设置页有逐台 / 全部吊销入口；把改密码悄悄变成「全设备下线」会让
    已配对的手机在用户毫无预期时集体掉线。
    """
    _prepare_config_post(tmp_path, monkeypatch)
    monkeypatch.setitem(web_server.STATE, "access_token", hash_access_password("old-password"))
    app = _lockdown_app(tmp_path)
    devices = app[DEVICE_TOKENS_KEY]
    token, _device = devices.issue("早就配好的手机")

    response = await web_server.api_config_post(
        _ConfigRequest({"access_token": PASSWORD}, app)
    )

    assert response.status == 200
    assert devices.verify(token) is not None
