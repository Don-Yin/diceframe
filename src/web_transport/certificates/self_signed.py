# -*- coding: utf-8 -*-
"""自签证书提供器。

生命周期：
    tls_mode=off           → 不生成任何文件
    首次切换 self_signed   → 生成并验证
    之后启动               → 复用原证书（fingerprint 不变）

SAN 覆盖 localhost / loopback / 主机名 / 当前 LAN 地址；LAN IP 变化
不自动换证书，由用户显式"重新生成本地证书"。
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from src.web_transport.certificates.base import CertificateError, PreparedCertificate
from src.web_transport.certificates.metadata import (
    CertificateMetadata,
    load_certificate_metadata,
    load_private_key,
    metadata_from_certificate,
)
from src.web_transport.certificates.storage import CertificateStore
from src.web_transport.local_addresses import local_ip_addresses

logger = logging.getLogger("trpg.web_transport")

CERTIFICATE_TYPE = "self_signed"
_VALID_DAYS = 365 * 5  # 自签证书不受公共 CA 398 天限制；5 年减少无谓的重新确认
_RENEW_BEFORE_EXPIRY = timedelta(days=30)


def _collect_san_entries() -> list[str]:
    """收集本机可达地址（去重、保持稳定顺序）。"""
    entries: list[str] = ["localhost", "127.0.0.1", "::1"]
    try:
        hostname = socket.gethostname()
        if hostname and hostname not in entries:
            entries.append(hostname)
    except OSError:
        pass
    for address in local_ip_addresses():
        text = str(address)
        if text not in entries:
            entries.append(text)
    return entries


class SelfSignedCertificateProvider:
    def __init__(self, store: CertificateStore) -> None:
        self._store = store

    # ---- 查询 ----

    def metadata(self) -> CertificateMetadata | None:
        cert_path = self._store.self_signed_cert_path
        if not cert_path.exists():
            return None
        try:
            return load_certificate_metadata(cert_path, CERTIFICATE_TYPE)
        except CertificateError as exc:
            logger.warning("自签证书读取失败：%s", exc)
            return None

    # ---- 生命周期 ----

    def prepare(self) -> PreparedCertificate:
        """返回可用证书：存在且有效则复用，否则生成。"""
        prepared = self._try_load_existing()
        if prepared is not None:
            return prepared
        return self._generate()

    def regenerate(self) -> PreparedCertificate:
        """显式重新生成（用户点击）。旧证书被原子替换，指纹必然变化。"""
        return self._generate()

    # ---- 内部 ----

    def _try_load_existing(self) -> PreparedCertificate | None:
        cert_path = self._store.self_signed_cert_path
        key_path = self._store.self_signed_key_path
        if not cert_path.exists() or not key_path.exists():
            return None
        try:
            metadata = load_certificate_metadata(cert_path, CERTIFICATE_TYPE)
            key = load_private_key(key_path)
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
            self._validate_pairing(cert, key)
            self._check_validity(metadata)
        except CertificateError as exc:
            logger.warning("自签证书不可复用，将重新生成：%s", exc)
            return None
        self._write_fingerprint(metadata)
        return PreparedCertificate(cert_path=cert_path, key_path=key_path, metadata=metadata)

    def _generate(self) -> PreparedCertificate:
        self._store.ensure_layout()
        cert_path = self._store.self_signed_cert_path
        key_path = self._store.self_signed_key_path

        now = datetime.now(timezone.utc)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DiceFrame Local")])
        san_entries = _collect_san_entries()
        builder = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=_VALID_DAYS))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName(_san_values(san_entries)),
                critical=False,
            )
        )
        cert = builder.sign(key, hashes.SHA256())

        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        key_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        # 先写 key 再写 cert：中断后至多是"有 key 无 cert"，下次启动重新生成。
        self._store.atomic_write_bytes(key_path, key_pem, private=True)
        self._store.atomic_write_bytes(cert_path, cert_pem)

        metadata = metadata_from_certificate(cert, CERTIFICATE_TYPE)
        self._write_fingerprint(metadata)
        logger.info(
            "已生成本地自签证书（SHA-256 指纹 %s...，SAN %d 项）",
            metadata.fingerprint_sha256[:23],
            len(metadata.san),
        )
        return PreparedCertificate(cert_path=cert_path, key_path=key_path, metadata=metadata)

    def _write_fingerprint(self, metadata: CertificateMetadata) -> None:
        # Launcher 依赖该文件做 fingerprint 固定，不解析 PEM。
        try:
            self._store.atomic_write_bytes(
                self._store.self_signed_fingerprint_path,
                metadata.fingerprint_sha256.encode("ascii"),
            )
        except CertificateError:
            # 指纹文件只影响 Launcher 校验；生成失败不阻断服务端。
            logger.warning("写入证书指纹文件失败", exc_info=True)

    @staticmethod
    def _validate_pairing(cert: x509.Certificate, key) -> None:
        cert_public = cert.public_key()
        if cert_public.public_numbers() != key.public_key().public_numbers():
            raise CertificateError("证书与私钥不匹配")

    @staticmethod
    def _check_validity(metadata: CertificateMetadata) -> None:
        not_after = datetime.strptime(metadata.not_after, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= not_after - _RENEW_BEFORE_EXPIRY:
            raise CertificateError("自签证书已过期或即将过期")
        not_before = datetime.strptime(metadata.not_before, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < not_before:
            raise CertificateError("自签证书尚未生效")


def _san_values(entries: list[str]):
    values = []
    for entry in entries:
        try:
            values.append(x509.IPAddress(ipaddress.ip_address(entry)))
            continue
        except ValueError:
            pass
        values.append(x509.DNSName(entry))
    return values
