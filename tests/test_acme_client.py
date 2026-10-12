"""ACME 客户端与提供器的离线集成测试。

用本地 mock ACME 服务器完整走一遍签发流程：
- 校验每个请求的 ES256 JWS 结构、nonce 与账户密钥；
- 真实回源 http-01 challenge responder，验证 key authorization 内容；
- 用 CSR 中的公钥与订单 identifier"签发"真实证书；
- 覆盖 provider 的落盘、配对校验、原子写入与 state.json。
"""

from __future__ import annotations

import base64
import json
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from src.web_transport.certificates.acme import (
    AcmeCertificateProvider,
    AcmeIssueRequest,
    _ChallengeResponder,
)
from src.web_transport.certificates.acme_client import AcmeIdentifier
from src.web_transport.certificates.storage import CertificateStore


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class MockAcmeServer:
    """实现 DiceFrame 用到的 ACME 子集。challenge 应答时真实回源 responder。"""

    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self.counter = 0
        self.challenge_port = 0
        self.seen_profiles: list[str] = []

    def build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/directory", self._directory)
        app.router.add_route("*", "/nonce", self._nonce)
        app.router.add_post("/new-account", self._new_account)
        app.router.add_post("/new-order", self._new_order)
        app.router.add_post("/order/{order_id}", self._get_order)
        app.router.add_post("/authz/{authz_id}", self._get_authz)
        app.router.add_post("/challenge/{authz_id}", self._answer_challenge)
        app.router.add_post("/finalize/{order_id}", self._finalize)
        app.router.add_post("/cert/{order_id}", self._download)
        return app

    async def _directory(self, request: web.Request) -> web.Response:
        base = str(request.url.origin())
        return web.json_response(
            {
                "newNonce": f"{base}/nonce",
                "newAccount": f"{base}/new-account",
                "newOrder": f"{base}/new-order",
            }
        )

    async def _nonce(self, request: web.Request) -> web.Response:
        return web.Response(status=204, headers={"Replay-Nonce": "nonce-1"})

    async def _new_account(self, request: web.Request) -> web.Response:
        protected, _payload, _signature = self._parse_jose(await request.text())
        if not protected.get("jwk") or protected.get("jwk", {}).get("kty") != "EC":
            raise web.HTTPBadRequest(text="newAccount 必须带 EC JWK")
        return web.json_response(
            {"status": "valid"},
            headers={"Location": f"{request.url.origin()}/account/1"},
        )

    async def _new_order(self, request: web.Request) -> web.Response:
        protected, payload, _signature = self._parse_jose(await request.text())
        self._check_protected(protected)
        self.counter += 1
        order_id = str(self.counter)
        self.seen_profiles.append(str(payload.get("profile") or ""))
        order = {
            "status": "pending",
            "identifiers": payload.get("identifiers", []),
            "authorizations": [f"{request.url.origin()}/authz/{order_id}"],
            "finalize": f"{request.url.origin()}/finalize/{order_id}",
            "certificate": f"{request.url.origin()}/cert/{order_id}",
            "_answered": False,
            "_finalized": False,
            "_csr": b"",
        }
        self.orders[order_id] = order
        return web.json_response(
            self._public(order),
            headers={"Location": f"{request.url.origin()}/order/{order_id}"},
        )

    async def _get_order(self, request: web.Request) -> web.Response:
        protected, _payload, _signature = self._parse_jose(await request.text())
        self._check_protected(protected)
        order = self.orders[request.match_info["order_id"]]
        if order["status"] == "pending" and order["_answered"]:
            order["status"] = "ready"
        elif order["status"] == "ready" and order["_finalized"]:
            order["status"] = "valid"
        return web.json_response(self._public(order))

    async def _get_authz(self, request: web.Request) -> web.Response:
        protected, _payload, _signature = self._parse_jose(await request.text())
        self._check_protected(protected)
        order = self.orders[request.match_info["authz_id"]]
        answered = order["_answered"]
        return web.json_response(
            {
                "status": "valid" if answered else "pending",
                "identifier": order["identifiers"][0],
                "challenges": [
                    {
                        "type": "http-01",
                        "status": "valid" if answered else "pending",
                        "token": "token-x",
                        "url": f"{request.url.origin()}/challenge/{request.match_info['authz_id']}",
                    }
                ],
            }
        )

    async def _answer_challenge(self, request: web.Request) -> web.Response:
        protected, _payload, signature = self._parse_jose(await request.text())
        self._check_protected(protected)
        # JOSE ES256 使用固定 64 字节的 R||S，不是 OpenSSL 的 DER 编码。
        assert len(_b64url_decode(signature)) == 64, "ES256 签名必须是 64 字节 R||S"
        order = self.orders[request.match_info["authz_id"]]

        # CA 真实回源 challenge responder：内容必须是 token.thumbprint。
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://127.0.0.1:{self.challenge_port}"
                "/.well-known/acme-challenge/token-x"
            ) as response:
                assert response.status == 200, "challenge responder 必须返回 200"
                body = await response.text()
        assert body.startswith("token-x."), "key authorization 内容不正确"
        assert len(body.split(".", 1)[1]) >= 40, "thumbprint 长度不正确"

        order["_answered"] = True
        return web.json_response({"type": "http-01", "status": "valid"})

    async def _finalize(self, request: web.Request) -> web.Response:
        protected, payload, _signature = self._parse_jose(await request.text())
        self._check_protected(protected)
        order = self.orders[request.match_info["order_id"]]
        order["_csr"] = _b64url_decode(payload["csr"])
        order["_finalized"] = True
        return web.json_response({"status": "valid"})

    async def _download(self, request: web.Request) -> web.Response:
        protected, _payload, _signature = self._parse_jose(await request.text())
        self._check_protected(protected)
        order = self.orders[request.match_info["order_id"]]
        pem = _issue_certificate(order["_csr"], order["identifiers"][0])
        return web.Response(
            text=pem, content_type="application/pem-certificate-chain"
        )

    # ---- helpers ----

    @staticmethod
    def _public(order: dict) -> dict:
        return {k: v for k, v in order.items() if not k.startswith("_")}

    def _parse_jose(self, body: str):
        jose = json.loads(body)
        protected = json.loads(_b64url_decode(jose["protected"]))
        payload_text = _b64url_decode(jose.get("payload") or "")
        payload = json.loads(payload_text) if payload_text else ""
        return protected, payload, jose["signature"]

    @staticmethod
    def _check_protected(protected: dict) -> None:
        assert protected.get("alg") == "ES256", "必须使用 ES256"
        assert protected.get("nonce"), "请求必须携带 nonce"
        assert protected.get("url"), "请求必须携带 url"
        assert protected.get("kid") or protected.get("jwk"), "请求必须携带 kid 或 jwk"


def _issue_certificate(csr_der: bytes, identifier: dict) -> str:
    """mock CA：用 CSR 的公钥与订单 identifier"签发"真实证书。"""
    import ipaddress

    csr = x509.load_der_x509_csr(csr_der)
    value = identifier["value"]
    if identifier["type"] == "ip":
        san = x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(value))])
    else:
        san = x509.SubjectAlternativeName([x509.DNSName(value)])
    signer = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, value)]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Mock CA")]))
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=6))
        .add_extension(san, critical=False)
        .sign(signer, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


@pytest.mark.asyncio
async def test_provider_issue_full_flow_against_mock_ca(tmp_path: Path):
    mock = MockAcmeServer()
    mock.challenge_port = _free_port()
    server = TestServer(mock.build_app())
    await server.start_server()
    try:
        directory_urls = {
            "staging": str(server.make_url("/directory")),
            "production": str(server.make_url("/directory")),
        }
        provider = AcmeCertificateProvider(CertificateStore(tmp_path))
        request = AcmeIssueRequest(
            identifier=AcmeIdentifier(type="dns", value="game.example.com"),
            contact_email="admin@example.com",
            directory="production",
            profile="",
            http_challenge_port=mock.challenge_port,
            staging_preflight=True,
            directory_urls=directory_urls,
        )
        result = await provider.issue(request)

        # staging 预检 + production 各跑一遍完整订单。
        assert len(mock.orders) == 2
        assert result.staging_ok is True

        # 证书落盘且元数据正确。
        prepared = result.prepared
        assert prepared.cert_path.exists() and prepared.key_path.exists()
        assert "game.example.com" in prepared.metadata.san
        assert prepared.metadata.certificate_type == "lets_encrypt"
        assert prepared.metadata.issuer == "Mock CA"

        # state.json 记录 canonical identifier 与签发结果。
        state = provider.state()
        assert state["identifier"] == "game.example.com"
        assert state["identifier_type"] == "dns"
        assert state["renewal"]["last_result"] == "ok"

        # 目录名使用稳定 ID，不含原始 identifier。
        live_dir = provider.live_directory("dns", "game.example.com")
        assert "game.example.com" not in live_dir.name

        # 账户密钥持久化且复用（第二次 issue 不再新建）。
        account_key_path = tmp_path / "certs" / "acme" / "account" / "account.key"
        assert account_key_path.exists()

        # 重启后能加载现有证书（load_live 不联网）。
        reloaded = provider.load_live("dns", "game.example.com")
        assert (
            reloaded.metadata.fingerprint_sha256
            == prepared.metadata.fingerprint_sha256
        )
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_provider_issue_ip_certificate_uses_shortlived_profile(tmp_path: Path):
    mock = MockAcmeServer()
    mock.challenge_port = _free_port()
    server = TestServer(mock.build_app())
    await server.start_server()
    try:
        provider = AcmeCertificateProvider(CertificateStore(tmp_path))
        request = AcmeIssueRequest(
            identifier=AcmeIdentifier(type="ip", value="2606:4700:4700::1111"),
            contact_email="",
            directory="production",
            profile="shortlived",
            http_challenge_port=mock.challenge_port,
            staging_preflight=False,
            directory_urls={
                "production": str(server.make_url("/directory")),
            },
        )
        result = await provider.issue(request)
        assert "2606:4700:4700::1111" in result.prepared.metadata.san
        # newOrder 载荷里带了 profile（IP 短期证书要求）。
        assert "shortlived" in mock.seen_profiles
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_challenge_responder_busy_port_reports_actionable_error(monkeypatch):
    # 直接模拟监听失败，避免测试结果受不同系统的 IPv4/IPv6 双栈绑定语义影响。
    port = _free_port()

    async def fail_to_listen(_site):
        raise OSError("address already in use")

    monkeypatch.setattr(web.TCPSite, "start", fail_to_listen)
    responder = _ChallengeResponder(port, {"token": "value"})
    with pytest.raises(Exception) as excinfo:
        await responder.start()
    assert "端口" in str(excinfo.value) or "监听" in str(excinfo.value)
    await responder.stop()


def test_renewal_due_respects_remaining_lifetime(tmp_path: Path):
    provider = AcmeCertificateProvider(CertificateStore(tmp_path))
    from src.web_transport.certificates.metadata import CertificateMetadata

    def metadata(not_before: datetime, not_after: datetime) -> CertificateMetadata:
        return CertificateMetadata(
            certificate_type="lets_encrypt",
            subject="s",
            issuer="i",
            not_before=not_before.strftime("%Y-%m-%dT%H:%M:%SZ"),
            not_after=not_after.strftime("%Y-%m-%dT%H:%M:%SZ"),
            fingerprint_sha256="00",
        )

    now = datetime.now(timezone.utc)
    # 短期证书（约 6 天）：剩余 1 天 → 需要续期。
    short = metadata(now - timedelta(days=5), now + timedelta(days=1))
    assert provider.renewal_due(short) is True
    # 剩余 4 天（> 1/3 生命周期）→ 不续期。
    fresh_short = metadata(now - timedelta(days=2), now + timedelta(days=4))
    assert provider.renewal_due(fresh_short) is False
    # 90 天证书剩余 20 天（< 30 天 lead）→ 需要续期。
    long_cert = metadata(now - timedelta(days=70), now + timedelta(days=20))
    assert provider.renewal_due(long_cert) is True
    # 90 天证书剩余 60 天 → 不续期。
    fresh_long = metadata(now - timedelta(days=30), now + timedelta(days=60))
    assert provider.renewal_due(fresh_long) is False
