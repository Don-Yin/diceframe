"""自签证书生命周期契约：懒生成、复用、重新生成与不泄露私钥。"""

from __future__ import annotations

from pathlib import Path

from src.web_transport.certificates.self_signed import SelfSignedCertificateProvider
from src.web_transport.certificates.storage import CertificateStore
from src.web_transport.transport import build_server_transport
from src.web_transport.config import parse_web_transport


def _provider(tmp_path: Path) -> SelfSignedCertificateProvider:
    return SelfSignedCertificateProvider(CertificateStore(tmp_path))


def test_off_mode_generates_no_certificate_files(tmp_path: Path):
    transport = build_server_transport(parse_web_transport({}), tmp_path, 18000)
    assert transport.ssl_context is None
    assert transport.scheme == "http"
    assert not (tmp_path / "certs" / "self-signed").exists()


def test_first_enable_generates_certificate(tmp_path: Path):
    provider = _provider(tmp_path)
    assert provider.metadata() is None
    prepared = provider.prepare()
    assert prepared.cert_path.exists()
    assert prepared.key_path.exists()
    san = prepared.metadata.san
    assert "localhost" in san
    assert "127.0.0.1" in san
    assert "::1" in san


def test_reuse_keeps_fingerprint_stable(tmp_path: Path):
    provider = _provider(tmp_path)
    first = provider.prepare()
    second = provider.prepare()
    assert first.metadata.fingerprint_sha256 == second.metadata.fingerprint_sha256


def test_regenerate_changes_fingerprint_and_updates_fingerprint_file(tmp_path: Path):
    provider = _provider(tmp_path)
    first = provider.prepare()
    fingerprint_file = tmp_path / "certs" / "self-signed" / "fingerprint.txt"
    assert fingerprint_file.read_text(encoding="ascii") == first.metadata.fingerprint_sha256
    second = provider.regenerate()
    assert second.metadata.fingerprint_sha256 != first.metadata.fingerprint_sha256
    assert fingerprint_file.read_text(encoding="ascii") == second.metadata.fingerprint_sha256


def test_transport_reuses_certificate_across_restarts(tmp_path: Path):
    config = parse_web_transport({"tls_mode": "self_signed"})
    first = build_server_transport(config, tmp_path, 18000)
    second = build_server_transport(config, tmp_path, 18000)
    assert first.ssl_context is not None and second.ssl_context is not None
    assert (
        first.diagnostics["certificate"]["fingerprint_sha256"]
        == second.diagnostics["certificate"]["fingerprint_sha256"]
    )


def test_corrupt_certificate_is_regenerated_not_crash(tmp_path: Path):
    provider = _provider(tmp_path)
    first = provider.prepare()
    # 模拟文件损坏：cert 与 key 不再配对。
    (tmp_path / "certs" / "self-signed" / "server.key").write_bytes(b"not a key")
    second = provider.prepare()
    assert second.metadata.fingerprint_sha256 != first.metadata.fingerprint_sha256


def test_unwritable_directory_degrades_to_http_without_locking_service(tmp_path: Path):
    # 指向一个文件路径作为 data_dir，mkdir 必然失败。
    blocker = tmp_path / "blocker"
    blocker.write_text("occupied")
    config = parse_web_transport({"tls_mode": "self_signed"})
    transport = build_server_transport(config, blocker, 18000)
    assert transport.ssl_context is None
    assert transport.scheme == "http"
    assert "回退 HTTP" in transport.degraded_error


def test_metadata_never_contains_private_key(tmp_path: Path):
    provider = _provider(tmp_path)
    prepared = provider.prepare()
    key_pem = prepared.key_path.read_bytes()
    view = prepared.metadata.public_view()
    assert key_pem not in repr(view).encode()
    assert b"PRIVATE KEY" not in repr(view).encode()
    fingerprint = view["fingerprint_sha256"]
    assert fingerprint and ":" in fingerprint
    # 指纹为 SHA-256：32 字节 → 64 个 hex 字符。
    assert len(fingerprint.replace(":", "")) == 64


def test_lets_encrypt_without_certificate_falls_back_to_http_with_visible_error(tmp_path: Path):
    config = parse_web_transport(
        {"tls_mode": "lets_encrypt", "acme": {"identifier_type": "dns", "identifier": "game.example.com"}}
    )
    transport = build_server_transport(config, tmp_path, 18000)
    assert transport.ssl_context is None
    assert transport.scheme == "http"
    assert "回退 HTTP" in transport.degraded_error
    assert "重新申请" in transport.degraded_error
