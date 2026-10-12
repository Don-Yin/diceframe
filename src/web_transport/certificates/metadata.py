# -*- coding: utf-8 -*-
"""证书元数据解析。

只输出可公开的信息：类型、SAN、有效期、签发者、SHA-256 指纹。
私钥 PEM 绝不进入本模块的任何返回值。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.web_transport.certificates.base import CertificateError


@dataclass(frozen=True)
class CertificateMetadata:
    certificate_type: str
    subject: str
    issuer: str
    not_before: str  # ISO 8601 UTC
    not_after: str   # ISO 8601 UTC
    fingerprint_sha256: str  # 冒号分隔大写 hex
    san: tuple[str, ...] = ()

    def public_view(self) -> dict:
        """API / 前端使用的公开视图。"""
        return {
            "type": self.certificate_type,
            "subject": self.subject,
            "issuer": self.issuer,
            "not_before": self.not_before,
            "not_after": self.not_after,
            "fingerprint_sha256": self.fingerprint_sha256,
            "san": list(self.san),
        }


def _format_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(cert: x509.Certificate) -> str:
    digest = cert.fingerprint(hashes.SHA256())
    return ":".join(f"{byte:02X}" for byte in digest)


def _name_text(name: x509.Name) -> str:
    # 取 CN，缺失时退回完整 RFC4514 字符串，保证展示总有内容。
    attrs = name.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    if attrs:
        return attrs[0].value
    return name.rfc4514_string()


def _san_entries(cert: x509.Certificate) -> tuple[str, ...]:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return ()
    entries: list[str] = []
    for value in san.get_values_for_type(x509.DNSName):
        entries.append(value)
    for value in san.get_values_for_type(x509.IPAddress):
        entries.append(str(value))
    return tuple(entries)


def load_certificate_metadata(cert_path: Path, certificate_type: str) -> CertificateMetadata:
    """解析 PEM 证书为公开元数据。文件缺失 / 损坏抛 CertificateError。"""
    try:
        pem = cert_path.read_bytes()
    except OSError as exc:
        raise CertificateError(f"无法读取证书文件：{exc}") from exc
    try:
        cert = x509.load_pem_x509_certificate(pem)
    except ValueError as exc:
        raise CertificateError("证书文件损坏或不是有效的 PEM 证书") from exc
    return metadata_from_certificate(cert, certificate_type)


def metadata_from_certificate(cert: x509.Certificate, certificate_type: str) -> CertificateMetadata:
    return CertificateMetadata(
        certificate_type=certificate_type,
        subject=_name_text(cert.subject),
        issuer=_name_text(cert.issuer),
        not_before=_format_time(cert.not_valid_before_utc),
        not_after=_format_time(cert.not_valid_after_utc),
        fingerprint_sha256=_fingerprint(cert),
        san=_san_entries(cert),
    )


def load_private_key(key_path: Path):
    """读取私钥对象（仅服务端内部使用，用于配对校验与 SSLContext）。"""
    try:
        pem = key_path.read_bytes()
    except OSError as exc:
        raise CertificateError(f"无法读取私钥文件：{exc}") from exc
    try:
        key = serialization.load_pem_private_key(pem, password=None)
    except (ValueError, TypeError) as exc:
        raise CertificateError("私钥文件损坏或不是有效的 PEM 私钥") from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        # 当前自签提供器只签发 RSA 证书；遇到其他类型视为不匹配，
        # 触发重新生成而不是带着错误材料启动。
        raise CertificateError("私钥类型与自签证书不匹配")
    return key
