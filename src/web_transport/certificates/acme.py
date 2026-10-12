# -*- coding: utf-8 -*-
"""Let's Encrypt（ACME）证书提供器。

域名与公网 IP 走同一个 provider，区别只在 identifier 类型与证书
profile（IP 强制 shortlived）。统一流程（方案第九节）：

    1. 规范化并检查 identifier
    2. 检查 challenge 端口
    3. staging 预检（申请方显式开启时）
    4. production 签发
    5. 校验证书链 / identifier / key 配对 / 有效期
    6. 原子写入 live 目录
    7. 更新 state.json

失败时保留旧证书，绝不覆盖仍有效的 live 材料。
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from src.web_transport.certificates.acme_client import (
    AcmeClient,
    AcmeError,
    AcmeIdentifier,
    account_key_from_pem,
    account_key_to_pem,
    describe_authorization_failure,
    directory_url,
    find_http01_challenge,
    generate_account_key,
)
from src.web_transport.certificates.base import (
    CertificateError,
    PreparedCertificate,
)
from src.web_transport.certificates.metadata import (
    CertificateMetadata,
    load_certificate_metadata,
    load_private_key,
    metadata_from_certificate,
)
from src.web_transport.certificates.storage import CertificateStore

logger = logging.getLogger("trpg.web_transport")

CERTIFICATE_TYPE = "lets_encrypt"

# 续期窗口：IP 短期证书约 160 小时，在到期前 2 天续期；普通证书 90 天，
# 提前 30 天。统一按剩余寿命计算，不写死"90 天"。
_RENEWAL_FRACTION = 1.0 / 3.0
_RENEWAL_MAX_LEAD = timedelta(days=30)
_RENEWAL_MIN_LEAD = timedelta(hours=24)

_CHALLENGE_PATH_PREFIX = "/.well-known/acme-challenge/"


@dataclass
class AcmeIssueRequest:
    """一次签发请求的全部参数（canonical）。"""

    identifier: AcmeIdentifier
    contact_email: str
    directory: str  # "production" | "staging"
    profile: str  # "" 或 "shortlived"
    http_challenge_port: int
    staging_preflight: bool = True
    # 测试 / 内部部署用：目录名 → URL 覆盖。空时使用 Let's Encrypt 官方目录。
    directory_urls: dict[str, str] = field(default_factory=dict)

    def resolve_directory(self, name: str) -> str:
        return self.directory_urls.get(name) or directory_url(name)


@dataclass
class AcmeIssueResult:
    prepared: PreparedCertificate
    warnings: list[str] = field(default_factory=list)
    staging_ok: bool = False


class AcmeCertificateProvider:
    def __init__(self, store: CertificateStore) -> None:
        self._store = store

    # ---- 查询 ----

    def live_directory(self, identifier_type: str, identifier: str) -> Path:
        return self._store.acme_live_dir_for(
            CertificateStore.stable_identifier_id(identifier_type, identifier)
        )

    def metadata_for(self, identifier_type: str, identifier: str) -> CertificateMetadata | None:
        directory = self.live_directory(identifier_type, identifier)
        cert_path = directory / "fullchain.pem"
        if not cert_path.exists():
            return None
        try:
            return load_certificate_metadata(cert_path, CERTIFICATE_TYPE)
        except CertificateError as exc:
            logger.warning("ACME 证书读取失败：%s", exc)
            return None

    def load_live(self, identifier_type: str, identifier: str) -> PreparedCertificate:
        """启动期加载现有证书（不联网）。不存在 / 损坏 / 过期抛 CertificateError。"""
        directory = self.live_directory(identifier_type, identifier)
        cert_path = directory / "fullchain.pem"
        key_path = directory / "privkey.pem"
        if not cert_path.exists() or not key_path.exists():
            raise CertificateError(
                "Let's Encrypt 证书不存在。请在“设置 → 安全”重新申请，或先使用其他连接模式"
            )
        metadata = load_certificate_metadata(cert_path, CERTIFICATE_TYPE)
        key = load_private_key(key_path)
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        self._validate_pairing(cert, key)
        self._validate_identifier(cert, identifier)
        self._check_validity(metadata)
        return PreparedCertificate(cert_path=cert_path, key_path=key_path, metadata=metadata)

    # ---- 签发 ----

    async def issue(self, request: AcmeIssueRequest) -> AcmeIssueResult:
        """完整签发流程（联网）。成功后原子写入 live 目录。"""
        self._store.ensure_layout()
        warnings: list[str] = []

        if request.identifier.type == "dns":
            warnings.extend(self._check_dns_resolution(request.identifier.value))

        account_key = self._load_or_create_account_key()
        certificate_key, csr_der = _build_csr(request.identifier)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=180)
        ) as session:
            if request.staging_preflight:
                await self._run_order(
                    session,
                    request=request,
                    account_key=account_key,
                    certificate_key=certificate_key,
                    csr_der=csr_der,
                    directory=request.resolve_directory("staging"),
                )
                logger.info("Let's Encrypt staging 预检通过（%s）", request.identifier.value)

            # staging 通过后才请求 production 证书。
            outcome = await self._run_order(
                session,
                request=request,
                account_key=account_key,
                certificate_key=certificate_key,
                csr_der=csr_der,
                directory=request.resolve_directory(request.directory),
            )

        prepared = self._persist(request, certificate_key, outcome.cert_pem)
        self._record_state(request, prepared)
        return AcmeIssueResult(prepared=prepared, warnings=warnings, staging_ok=request.staging_preflight)

    async def _run_order(
        self,
        session: aiohttp.ClientSession,
        request: AcmeIssueRequest,
        account_key,
        certificate_key,
        csr_der: bytes,
        directory: str,
    ) -> "_OrderOutcome":
        """在指定目录（staging / production）完成一次完整订单。"""
        client = AcmeClient(session, directory, account_key)
        await client.ensure_account(request.contact_email)

        order, order_url = await client.new_order([request.identifier], request.profile)

        # 收集待验证的 http-01 token。
        challenge_tokens: dict[str, str] = {}
        pending: list[tuple[str, dict[str, Any]]] = []  # (challenge_url, authorization)
        for authorization_url in order.get("authorizations", []):
            authorization = await client.fetch(authorization_url)
            if str(authorization.get("status") or "") == "valid":
                continue
            challenge = find_http01_challenge(authorization)
            if challenge is None:
                raise AcmeError("CA 未提供 http-01 验证方式，无法自动申请")
            token = str(challenge.get("token") or "")
            challenge_url = str(challenge.get("url") or "")
            if not token or not challenge_url:
                raise AcmeError("http-01 验证缺少 token 或地址")
            challenge_tokens[token] = client.key_authorization(token)
            pending.append((challenge_url, authorization))

        if challenge_tokens:
            async with _ChallengeResponder(
                request.http_challenge_port, challenge_tokens
            ) as responder:
                await responder.start()
                for challenge_url, _authorization in pending:
                    await client.answer_challenge(challenge_url)
                # challenge 应答后订单进入 ready，才能提交 CSR。
                order = await _await_valid_order(client, order_url, order, target="ready")
        else:
            order = await _await_valid_order(client, order_url, order, target="ready")

        finalize_url = str(order.get("finalize") or "")
        if not finalize_url:
            raise AcmeError("订单缺少 finalize 地址")
        await client.finalize(finalize_url, csr_der)
        order = await client.wait_for_order(order_url, target="valid")
        cert_pem = await client.download_certificate(order)

        # 落盘前的完整校验：链、identifier、key 配对、有效期。
        verified = _verify_issued_certificate(cert_pem, certificate_key, request.identifier)
        return _OrderOutcome(cert_pem=cert_pem, metadata=verified)

    # ---- 续期 ----

    def renewal_due(self, metadata: CertificateMetadata) -> bool:
        not_after = datetime.strptime(metadata.not_after, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        now = datetime.now(timezone.utc)
        remaining = not_after - now
        if remaining <= _RENEWAL_MIN_LEAD:
            return True
        lifetime = not_after - datetime.strptime(
            metadata.not_before, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        lead = max(min(_RENEWAL_MAX_LEAD, lifetime * _RENEWAL_FRACTION), _RENEWAL_MIN_LEAD)
        return remaining <= lead

    def state(self) -> dict[str, Any]:
        return self._store.read_json(self._store.acme_state_path)

    # ---- 内部 ----

    def _load_or_create_account_key(self):
        path = self._store.acme_account_key_path
        if path.exists():
            try:
                return account_key_from_pem(path.read_bytes())
            except (AcmeError, ValueError):
                logger.warning("ACME 账户密钥损坏，将重新生成")
        key = generate_account_key()
        self._store.atomic_write_bytes(path, account_key_to_pem(key), private=True)
        return key

    def _check_dns_resolution(self, identifier: str) -> list[str]:
        """DNS 解析与本地地址不一致时给出明确警告（不阻断，由 CA 最终验证）。"""
        warnings: list[str] = []
        try:
            resolved = {info[4][0] for info in socket.getaddrinfo(identifier, None)}
        except OSError:
            return [f"域名 {identifier} 当前无法解析，Let's Encrypt 验证大概率会失败"]
        local = {str(address) for address in _local_addresses()}
        if resolved and not (resolved & local):
            warnings.append(
                f"域名 {identifier} 解析到 {', '.join(sorted(resolved))}，"
                "与当前服务器地址不一致，请确认 DNS 已指向本机公网地址"
            )
        return warnings

    def _persist(self, request: AcmeIssueRequest, certificate_key, cert_pem: str) -> PreparedCertificate:
        directory = self.live_directory(request.identifier.type, request.identifier.value)
        key_pem = certificate_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        # 先写 key 再写 cert：中断后至多是"有 key 无 cert"，可安全重来。
        self._store.atomic_write_bytes(directory / "privkey.pem", key_pem, private=True)
        self._store.atomic_write_bytes(directory / "fullchain.pem", cert_pem.encode("ascii"))
        metadata = load_certificate_metadata(directory / "fullchain.pem", CERTIFICATE_TYPE)
        self._store.atomic_write_json(
            directory / "metadata.json",
            {
                "identifier_type": request.identifier.type,
                "identifier": request.identifier.value,
                "directory": request.directory,
                "certificate_profile": request.profile,
                "issued_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        logger.info(
            "Let's Encrypt 证书已签发（%s，指纹 %s...）",
            request.identifier.value,
            metadata.fingerprint_sha256[:23],
        )
        return PreparedCertificate(
            cert_path=directory / "fullchain.pem",
            key_path=directory / "privkey.pem",
            metadata=metadata,
        )

    def _record_state(self, request: AcmeIssueRequest, prepared: PreparedCertificate) -> None:
        state = self.state()
        state.update(
            {
                "identifier_type": request.identifier.type,
                "identifier": request.identifier.value,
                "stable_id": CertificateStore.stable_identifier_id(
                    request.identifier.type, request.identifier.value
                ),
                "directory": request.directory,
                "certificate_profile": request.profile,
                "last_issued_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "renewal": {
                    "last_result": "ok",
                    "last_error": "",
                    "last_attempt_at": datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                },
            }
        )
        self._store.atomic_write_json(self._store.acme_state_path, state)

    def record_renewal(self, ok: bool, error: str = "") -> None:
        state = self.state()
        renewal = state.get("renewal") or {}
        renewal.update(
            {
                "last_result": "ok" if ok else "failed",
                "last_error": error[:500],
                "last_attempt_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        state["renewal"] = renewal
        self._store.atomic_write_json(self._store.acme_state_path, state)

    @staticmethod
    def _validate_pairing(cert: x509.Certificate, key) -> None:
        if cert.public_key().public_numbers() != key.public_key().public_numbers():
            raise CertificateError("证书与私钥不匹配")

    @staticmethod
    def _validate_identifier(cert: x509.Certificate, identifier: str) -> None:
        try:
            san = cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            ).value
        except x509.ExtensionNotFound:
            raise CertificateError("证书缺少 SAN，不能用于当前连接模式") from None
        entries = set(san.get_values_for_type(x509.DNSName))
        entries.update(str(value) for value in san.get_values_for_type(x509.IPAddress))
        try:
            entries.add(ipaddress.ip_address(identifier).compressed)
        except ValueError:
            pass
        if identifier not in entries:
            raise CertificateError("证书 SAN 不包含当前标识（identifier 不匹配）")

    @staticmethod
    def _check_validity(metadata: CertificateMetadata) -> None:
        not_after = datetime.strptime(metadata.not_after, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        now = datetime.now(timezone.utc)
        if now >= not_after:
            raise CertificateError("Let's Encrypt 证书已过期，请重新申请")
        if now < datetime.strptime(metadata.not_before, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ) - timedelta(minutes=5):
            raise CertificateError("证书尚未生效")


@dataclass
class _OrderOutcome:
    cert_pem: str
    metadata: CertificateMetadata


async def _await_valid_order(client: AcmeClient, order_url: str, order: dict[str, Any], target: str = "valid") -> dict[str, Any]:
    """等待订单到达目标状态，把 invalid 的具体原因翻译出来。"""
    result = await client.wait_for_order(order_url, target)
    if str(result.get("status")) != target:
        authorization_url = (order.get("authorizations") or [""])[0]
        if authorization_url:
            authorization = await client.fetch(authorization_url)
            raise AcmeError(describe_authorization_failure(authorization))
    return result


class _ChallengeResponder:
    """在验证端口临时监听 http-01 响应，只在签发期间存在。

    优先绑定 IPv6 双栈（公网 IPv6 验证必须），失败再退回 IPv4。
    """

    def __init__(self, port: int, tokens: dict[str, str]) -> None:
        self._port = port
        self._tokens = tokens
        self._runner: web.AppRunner | None = None

    async def __aenter__(self) -> "_ChallengeResponder":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.stop()

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get(_CHALLENGE_PATH_PREFIX + "{token}", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        bound = False
        errors: list[str] = []
        for host in ("::", "0.0.0.0"):
            site = web.TCPSite(self._runner, host, self._port)
            try:
                await site.start()
                bound = True
            except OSError as exc:
                errors.append(str(exc))
                continue
        if not bound:
            await self._runner.cleanup()
            self._runner = None
            raise AcmeError(
                f"无法监听验证端口 {self._port}（{'; '.join(errors)}）。"
                "请确认该端口未被占用并已放行防火墙；Docker 需显式映射该端口"
            )
        logger.info("http-01 验证响应器已监听端口 %d", self._port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _handle(self, request: web.Request) -> web.Response:
        token = request.match_info["token"]
        content = self._tokens.get(token)
        if content is None:
            return web.Response(status=404)
        return web.Response(text=content, content_type="text/plain")


def _build_csr(identifier: AcmeIdentifier) -> tuple[rsa.RSAPrivateKey, bytes]:
    """生成证书私钥与 CSR。key 每次签发生成；账户密钥与证书密钥分离。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, identifier.value)])
    if identifier.type == "ip":
        san = x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(identifier.value))])
    else:
        san = x509.SubjectAlternativeName([x509.DNSName(identifier.value)])
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(name)
        .add_extension(san, critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, csr.public_bytes(serialization.Encoding.DER)


def _verify_issued_certificate(
    cert_pem: str, certificate_key: rsa.RSAPrivateKey, identifier: AcmeIdentifier
) -> CertificateMetadata:
    """落盘前的完整校验：可解析、SAN 匹配、key 配对、有效期。"""
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("ascii"))
    except ValueError as exc:
        raise AcmeError(f"CA 返回的证书无法解析：{exc}") from exc
    AcmeCertificateProvider._validate_identifier(cert, identifier.value)
    AcmeCertificateProvider._validate_pairing(cert, certificate_key)
    metadata = metadata_from_certificate(cert, CERTIFICATE_TYPE)
    AcmeCertificateProvider._check_validity(metadata)
    return metadata


def _local_addresses() -> list[str]:
    """本机可能被公网访问到的地址（主机名解析 + 默认路由源地址）。"""
    addresses: list[str] = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None)
        addresses.extend(info[4][0] for info in infos)
    except OSError:
        pass
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.settimeout(0)
        probe.connect(("8.8.8.8", 80))
        addresses.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    return addresses
