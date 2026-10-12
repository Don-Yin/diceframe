# -*- coding: utf-8 -*-
"""最小 ACME v2（RFC 8555）客户端。

只实现 DiceFrame 需要的路径：ES256 账户、newOrder（含 profile 扩展）、
http-01 challenge、finalize、证书链下载。不引入第三方 ACME 依赖，
网络层复用 aiohttp。协议错误统一抛 AcmeError（中文说明，可直接给用户）。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

logger = logging.getLogger("trpg.web_transport")

DIRECTORY_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"
DIRECTORY_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"

_POLL_INTERVAL_SECONDS = 2.0
_POLL_TIMEOUT_SECONDS = 120.0


def directory_url(name: str) -> str:
    return DIRECTORY_STAGING if name == "staging" else DIRECTORY_PRODUCTION


class AcmeError(RuntimeError):
    """ACME 流程失败。message 面向用户，可直接返回给 API。"""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class AcmeIdentifier:
    """canonical identifier：type 显式保存，不做字符串模糊猜测。"""

    type: str  # "dns" | "ip"
    value: str

    def to_payload(self) -> dict[str, str]:
        return {"type": self.type, "value": self.value}


class AcmeClient:
    """一个实例对应一个账户密钥与一次目录会话。方法都要求已有事件循环。"""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        directory: str,
        account_key: ec.EllipticCurvePrivateKey,
    ) -> None:
        self._session = session
        self._directory_url = directory
        self._key = account_key
        self._directory: dict[str, str] = {}
        self._nonce: str | None = None
        self._kid: str | None = None
        self._jwk_thumbprint = _jwk_thumbprint(account_key)

    # ---- 账户 ----

    async def ensure_account(self, contact_email: str) -> str:
        """注册或复用账户，返回 kid（账户 URL）。已存在账户返回 200，新建返回 201。"""
        await self._load_directory()
        payload: dict[str, Any] = {"termsOfServiceAgreed": True}
        if contact_email:
            payload["contact"] = [f"mailto:{contact_email}"]
        await self._signed_request(
            self._directory["newAccount"], payload, use_kid=False
        )
        if not self._kid:
            raise AcmeError("ACME 账户注册失败：服务端未返回账户地址")
        return self._kid

    @property
    def jwk_thumbprint(self) -> str:
        return self._jwk_thumbprint

    def key_authorization(self, token: str) -> str:
        return f"{token}.{self._jwk_thumbprint}"

    # ---- 订单 ----

    async def new_order(
        self, identifiers: list[AcmeIdentifier], profile: str = ""
    ) -> tuple[dict[str, Any], str]:
        """创建订单。返回 (order, order_url)；order_url 来自 Location 头。"""
        payload: dict[str, Any] = {
            "identifiers": [identifier.to_payload() for identifier in identifiers]
        }
        if profile:
            payload["profile"] = profile
        body, _text, response = await self._signed_request(self._directory["newOrder"], payload)
        order_url = response.headers.get("Location") or ""
        if not order_url:
            raise AcmeError("订单响应缺少 Location 地址")
        return body, order_url

    async def fetch(self, url: str) -> dict[str, Any]:
        """POST-as-GET（RFC 8555 §6.3：只读资源也必须带签名请求）。"""
        body, _text, _response = await self._signed_request(url, _EMPTY_PAYLOAD)
        return body

    async def answer_challenge(self, challenge_url: str) -> dict[str, Any]:
        body, _text, _response = await self._signed_request(challenge_url, {})
        return body

    async def finalize(self, finalize_url: str, csr_der: bytes) -> dict[str, Any]:
        body, _text, _response = await self._signed_request(
            finalize_url, {"csr": _b64url(csr_der)}
        )
        return body

    async def download_certificate(self, order: dict[str, Any]) -> str:
        """下载完整证书链（PEM 文本）。order 必须处于 valid 状态。"""
        certificate_url = order.get("certificate")
        if not certificate_url:
            raise AcmeError("订单缺少证书下载地址")
        _body, text, _response = await self._signed_request(certificate_url, _EMPTY_PAYLOAD)
        if "-----BEGIN CERTIFICATE-----" not in text:
            raise AcmeError("证书响应不是有效的 PEM 证书链")
        return text

    async def wait_for_order(self, order_url: str, target: str = "valid") -> dict[str, Any]:
        """轮询订单直到目标状态（finalize 前 ready，之后 valid）或 invalid。"""
        deadline = asyncio.get_event_loop().time() + _POLL_TIMEOUT_SECONDS
        last_status = ""
        while asyncio.get_event_loop().time() < deadline:
            order = await self.fetch(order_url)
            last_status = str(order.get("status") or "")
            if last_status == target:
                return order
            if last_status == "invalid":
                raise AcmeError("证书申请被拒绝（订单无效），请检查标识与验证配置")
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        raise AcmeError(f"证书申请超时（订单状态长期停留在 {last_status or 'unknown'}）")

    # ---- JWS 签名 ----

    async def _load_directory(self) -> None:
        async with self._session.get(self._directory_url) as response:
            await self._capture_nonce(response)
            body = await response.json(content_type=None)
        if not isinstance(body, dict) or "newOrder" not in body:
            raise AcmeError("ACME 目录不可用或格式不正确")
        self._directory = body

    async def _ensure_nonce(self) -> None:
        if self._nonce:
            return
        nonce_url = self._directory.get("newNonce")
        if not nonce_url:
            raise AcmeError("ACME 目录缺少 newNonce 端点")
        async with self._session.head(nonce_url) as response:
            await self._capture_nonce(response)
            if response.status not in (200, 204):
                raise AcmeError(f"获取 ACME nonce 失败：HTTP {response.status}")

    async def _capture_nonce(self, response: aiohttp.ClientResponse) -> None:
        nonce = response.headers.get("Replay-Nonce")
        if nonce:
            self._nonce = nonce

    async def _signed_request(
        self, url: str, payload: Any, use_kid: bool = True
    ) -> tuple[dict[str, Any], str]:
        """发送签名请求。payload 为 _EMPTY_PAYLOAD 时是 POST-as-GET。"""
        await self._ensure_nonce()
        protected: dict[str, Any] = {
            "alg": "ES256",
            "nonce": self._nonce,
            "url": url,
        }
        if use_kid and self._kid:
            protected["kid"] = self._kid
        else:
            protected["jwk"] = _jwk_dict(self._key)

        payload_text = "" if payload is _EMPTY_PAYLOAD else json.dumps(payload, separators=(",", ":"))
        protected_b64 = _b64url(json.dumps(protected, separators=(",", ":")).encode())
        payload_b64 = _b64url(payload_text.encode()) if payload_text else ""
        signing_input = f"{protected_b64}.{payload_b64}".encode("ascii")
        # JOSE 的 ES256 签名不是 OpenSSL 默认的 DER，而是固定 32+32 字节的 R||S。
        der_signature = self._key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_signature)
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        body = json.dumps(
            {
                "protected": protected_b64,
                "payload": payload_b64,
                "signature": _b64url(signature),
            },
            separators=(",", ":"),
        )
        async with self._session.post(
            url,
            headers={"Content-Type": "application/jose+json"},
            data=body,
        ) as response:
            await self._capture_nonce(response)
            location = response.headers.get("Location")
            if location and not (use_kid and self._kid):
                self._kid = location
            text = await response.text()
            if response.status not in (200, 201):
                raise AcmeError(
                    f"ACME 请求失败（HTTP {response.status}）：{_problem_detail(text)}"
                )
            try:
                parsed = json.loads(text) if text else {}
            except ValueError:
                parsed = {}
            return parsed, text, response


class _EmptyPayload:
    """POST-as-GET 的哨兵值（区别于空对象 {}）。"""


_EMPTY_PAYLOAD = _EmptyPayload()


def _jwk_dict(key: ec.EllipticCurvePrivateKey) -> dict[str, str]:
    numbers = key.public_key().public_numbers()
    coordinate_bytes = 32  # P-256
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(numbers.x.to_bytes(coordinate_bytes, "big")),
        "y": _b64url(numbers.y.to_bytes(coordinate_bytes, "big")),
    }


def _jwk_thumbprint(key: ec.EllipticCurvePrivateKey) -> str:
    jwk = json.dumps(_jwk_dict(key), separators=(",", ":"), sort_keys=True).encode()
    return _b64url(hashlib.sha256(jwk).digest())


def _problem_detail(text: str) -> str:
    try:
        problem = json.loads(text)
    except ValueError:
        return (text or "").strip()[:200]
    detail = problem.get("detail") or problem.get("title") or "未知错误"
    return str(detail)[:200]


def find_http01_challenge(authorization: dict[str, Any]) -> dict[str, Any] | None:
    """从 authorization 中取 http-01 challenge（本版本唯一支持的类型）。"""
    for challenge in authorization.get("challenges", []):
        if challenge.get("type") == "http-01":
            return challenge
    return None


def describe_authorization_failure(authorization: dict[str, Any]) -> str:
    """把 authorization 里第一个 challenge 错误转成可行动的中文说明。"""
    for challenge in authorization.get("challenges", []):
        error = challenge.get("error")
        if isinstance(error, dict):
            detail = str(error.get("detail") or error.get("type") or "")
            return f"http-01 验证失败：{detail[:200]}"
    return "http-01 验证失败"


def generate_account_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def account_key_from_pem(pem: bytes) -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise AcmeError("ACME 账户密钥类型不正确")
    return key


def account_key_to_pem(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
