from __future__ import annotations

import contextlib
import datetime
import ipaddress
import json
import ssl
import stat
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from src.docker_launcher import contracts
from src.docker_launcher.launcher import (
    DockerLauncher,
    _normalized_fingerprint,
    _resolve_health_endpoint,
    _verify_pinned_certificate,
    _version_key,
)


def _package_tree(root: Path, version: str = "2.4.0", probation: int = 0) -> Path:
    package = root / f"DiceFrame-v{version}-docker-update-linux-amd64"
    (package / "app" / "src").mkdir(parents=True)
    (package / "app" / "static-v2").mkdir(parents=True)
    (package / "runtime" / "site-packages").mkdir(parents=True)
    (package / "app" / "web_server.py").write_text("# server\n", encoding="utf-8")
    (package / "app" / "src" / "version.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8",
    )
    (package / "app" / "static-v2" / "index.html").write_text("ok", encoding="utf-8")
    (package / "runtime" / "site-packages" / "runtime.txt").write_text("ok", encoding="utf-8")
    (package / "manifest.json").write_text(json.dumps({
        "schema": 1,
        "version": version,
        "platform": "linux-amd64",
        "python_abi": "cp311",
        "launcher_schema_min": 1,
        "runtime_api": 1,
        "data_rollback_safe": True,
        "entrypoint": "app/web_server.py",
        "site_packages": "runtime/site-packages",
        "health_path": "/api/system/update/health",
        "probation_seconds": probation,
    }), encoding="utf-8")
    return package


def _archive(tmp_path: Path, version: str = "2.4.0") -> Path:
    package = _package_tree(tmp_path / "source", version)
    archive = tmp_path / f"DiceFrame-v{version}-docker-update-linux-amd64.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in package.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(package.parent).as_posix())
    return archive


def test_contract_rejects_links_and_path_traversal(tmp_path):
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as bundle:
        bundle.writestr("DiceFrame/../../outside", "bad")
    with pytest.raises(ValueError, match="unsafe update path"):
        contracts.safe_extract_package(traversal, tmp_path / "out-traversal")

    linked = tmp_path / "linked.zip"
    info = zipfile.ZipInfo("DiceFrame/link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(linked, "w") as bundle:
        bundle.writestr(info, "target")
    with pytest.raises(ValueError, match="symlink"):
        contracts.safe_extract_package(linked, tmp_path / "out-linked")


def test_manifest_binds_application_version(tmp_path):
    package = _package_tree(tmp_path, "2.4.0")
    contracts.validate_package_tree(package, expected_version="2.4.0")
    (package / "app" / "src" / "version.py").write_text(
        '__version__ = "2.4.1"', encoding="utf-8",
    )
    with pytest.raises(ValueError, match="application version"):
        contracts.validate_package_tree(package, expected_version="2.4.0")


def test_manifest_requires_data_safe_rollback(tmp_path):
    package = _package_tree(tmp_path, "2.4.0")
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["data_rollback_safe"] = False
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="data migrations"):
        contracts.validate_package_tree(package, expected_version="2.4.0")


def test_launcher_installs_verified_seed_and_commits_relative_pointer(tmp_path, monkeypatch):
    archive = _archive(tmp_path, "2.4.0")
    checksum = tmp_path / "update.sha256"
    checksum.write_text(
        f"{contracts.file_sha256(archive)}  {archive.name}\n", encoding="utf-8",
    )
    launcher = DockerLauncher(tmp_path / "runtime", archive, checksum, startup_timeout=0)
    seed_dir, manifest = launcher.ensure_seed()
    assert manifest["version"] == "2.4.0"
    assert seed_dir == launcher.versions_dir / "v2.4.0"
    assert json.loads(launcher.seed_state_file.read_text(encoding="utf-8"))["sha256"] == contracts.file_sha256(archive)

    monkeypatch.setattr(
        "src.docker_launcher.launcher.safe_extract_package",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("seed unpacked twice")),
    )
    cached_dir, cached_manifest = launcher.ensure_seed()
    assert cached_dir == seed_dir
    assert cached_manifest["version"] == "2.4.0"

    launcher._commit(seed_dir, None)
    pointer = json.loads(launcher.current_file.read_text(encoding="utf-8"))
    assert pointer["relative_dir"] == "docker-versions/v2.4.0"
    assert not Path(pointer["relative_dir"]).is_absolute()


def test_launcher_seed_checksum_is_bound_to_container_filename(tmp_path):
    archive = _archive(tmp_path, "2.4.0")
    archive = archive.rename(tmp_path / "update.zip")
    checksum = tmp_path / "update.sha256"
    checksum.write_text(
        f"{contracts.file_sha256(archive)}  update.zip\n", encoding="utf-8",
    )
    launcher = DockerLauncher(tmp_path / "runtime", archive, checksum)

    seed_dir, manifest = launcher.ensure_seed()

    assert manifest["version"] == "2.4.0"
    assert seed_dir.is_dir()


def test_launcher_health_uses_manifest_path_and_normalizes_version(monkeypatch, tmp_path):
    archive = _archive(tmp_path, "2.4.0")
    checksum = tmp_path / "update.sha256"
    checksum.write_text(
        f"{contracts.file_sha256(archive)}  {archive.name}\n", encoding="utf-8",
    )
    launcher = DockerLauncher(tmp_path / "runtime", archive, checksum)
    launcher.child = SimpleNamespace(poll=lambda: None)
    requested: list[str] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok": true, "version": "v2.4.0"}'

    def fake_urlopen(requested_url, timeout):
        requested.append(requested_url)
        assert timeout == 2
        return Response()

    monkeypatch.setattr("src.docker_launcher.launcher.urllib.request.urlopen", fake_urlopen)

    assert launcher._health("2.4.0", "/custom/health") is True
    assert requested == ["http://127.0.0.1:9876/custom/health"]


def test_launcher_probation_tolerates_a_transient_probe_failure(monkeypatch, tmp_path):
    archive = _archive(tmp_path, "2.4.0")
    checksum = tmp_path / "update.sha256"
    checksum.write_text(
        f"{contracts.file_sha256(archive)}  {archive.name}\n", encoding="utf-8",
    )
    launcher = DockerLauncher(
        tmp_path / "runtime", archive, checksum,
        startup_timeout=9, poll_interval=0.5,
    )
    candidate = _package_tree(launcher.versions_dir, "2.4.0", probation=3)
    launcher.child = SimpleNamespace(poll=lambda: None)
    clock = [0.0]
    results = iter([True, False, True, True, True, True, True])

    monkeypatch.setattr("src.docker_launcher.launcher.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(
        "src.docker_launcher.launcher.time.sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    monkeypatch.setattr(launcher, "_health", lambda *_args: next(results, True))

    assert launcher._wait_healthy(candidate) is True


def test_launcher_commits_healthy_candidate_and_rolls_back_failed_one(tmp_path, monkeypatch):
    archive = _archive(tmp_path, "2.4.0")
    checksum = tmp_path / "update.sha256"
    checksum.write_text(
        f"{contracts.file_sha256(archive)}  {archive.name}\n", encoding="utf-8",
    )
    launcher = DockerLauncher(tmp_path / "runtime", archive, checksum)
    previous = _package_tree(launcher.versions_dir, "2.3.2")
    candidate = _package_tree(launcher.versions_dir, "2.4.0")
    spawned: list[Path] = []
    monkeypatch.setattr(launcher, "_stop_child", lambda *args, **kwargs: None)
    monkeypatch.setattr(launcher, "_spawn", lambda path: spawned.append(path))
    monkeypatch.setattr(launcher, "_prune", lambda: None)
    monkeypatch.setattr(launcher, "_wait_healthy", lambda path: path == candidate)

    assert launcher._launch_candidate(candidate, previous) is True
    assert json.loads(launcher.current_file.read_text(encoding="utf-8"))["version"] == "2.4.0"
    assert not launcher.signal_file.exists()

    broken = _package_tree(launcher.versions_dir, "2.5.0")
    monkeypatch.setattr(launcher, "_wait_healthy", lambda path: path == candidate)
    assert launcher._launch_candidate(broken, candidate) is False
    assert spawned[-2:] == [broken, candidate]
    assert json.loads(launcher.state_file.read_text(encoding="utf-8"))["state"] == "rolled-back"


def test_launcher_uses_previous_when_current_is_damaged(tmp_path):
    archive = _archive(tmp_path, "2.4.0")
    checksum = tmp_path / "update.sha256"
    checksum.write_text(
        f"{contracts.file_sha256(archive)}  {archive.name}\n", encoding="utf-8",
    )
    launcher = DockerLauncher(tmp_path / "runtime", archive, checksum)
    seed_source = _package_tree(launcher.versions_dir, "2.4.0")
    seed = seed_source.rename(launcher.versions_dir / "v2.4.0")
    previous_source = _package_tree(launcher.versions_dir, "2.3.2")
    previous = previous_source.rename(launcher.versions_dir / "v2.3.2")
    launcher.current_file.parent.mkdir(parents=True, exist_ok=True)
    launcher.current_file.write_text(json.dumps({
        "relative_dir": "docker-versions/v2.4.1",
        "previous_relative_dir": "docker-versions/v2.3.2",
    }), encoding="utf-8")

    selected, fallback = launcher._choose_startup(
        seed, contracts.validate_package_tree(seed),
    )
    assert selected == previous
    assert fallback is None


def test_version_order_handles_prereleases():
    assert _version_key("2.4.0-beta.1") < _version_key("2.4.0")
    assert _version_key("2.4.0-beta.10") > _version_key("2.4.0-beta.2")
    assert _version_key("2.4.1") > _version_key("2.4.0")


def _write_transport_config(data_dir: Path, tls_mode: str, fingerprint: str | None = None) -> None:
    (data_dir / "certs" / "self-signed").mkdir(parents=True, exist_ok=True)
    (data_dir / "config.json").write_text(
        json.dumps({"web_transport": {"tls_mode": tls_mode}}), encoding="utf-8",
    )
    fingerprint_path = data_dir / "certs" / "self-signed" / "fingerprint.txt"
    if fingerprint is None:
        fingerprint_path.unlink(missing_ok=True)
    else:
        fingerprint_path.write_text(fingerprint, encoding="utf-8")


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        payload = json.dumps({"ok": True, "version": "v2.4.0"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args) -> None:
        pass


class _QuietHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address) -> None:  # noqa: N802 - stdlib signature
        pass  # TLS 探测打到明文端口（或反之）是这些测试的正常路径


def _generate_self_signed() -> tuple[bytes, bytes, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "diceframe-health-test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    fingerprint = certificate.fingerprint(hashes.SHA256()).hex().upper()
    return cert_pem, key_pem, fingerprint


@contextlib.contextmanager
def _health_server(tmp_path: Path, *, tls: bool):
    fingerprint = ""
    server = _QuietHTTPServer(("127.0.0.1", 0), _HealthHandler)
    if tls:
        cert_pem, key_pem, fingerprint = _generate_self_signed()
        cert_file = tmp_path / "server.crt"
        key_file = tmp_path / "server.key"
        cert_file.write_bytes(cert_pem)
        key_file.write_bytes(key_pem)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert_file), str(key_file))
        server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(port=server.server_address[1], fingerprint=fingerprint)
    finally:
        server.shutdown()
        server.server_close()


def _launcher_with_data(tmp_path: Path, data_dir: Path) -> DockerLauncher:
    launcher = DockerLauncher(
        tmp_path / "runtime", tmp_path / "seed.zip", tmp_path / "seed.sha256",
        data_dir=data_dir,
    )
    launcher.child = SimpleNamespace(poll=lambda: None)
    return launcher


def test_resolve_health_endpoint_follows_transport_config(tmp_path):
    data_dir = tmp_path / "data"

    assert _resolve_health_endpoint(data_dir, {}) == ("http", "")

    _write_transport_config(data_dir, "self_signed", fingerprint="AA:BB:CC:DD\n")
    assert _resolve_health_endpoint(data_dir, {}) == ("https", "AABBCCDD")

    _write_transport_config(data_dir, "self_signed", fingerprint=None)
    assert _resolve_health_endpoint(data_dir, {}) == ("http", "")

    _write_transport_config(data_dir, "self_signed", fingerprint="   \n")
    assert _resolve_health_endpoint(data_dir, {}) == ("http", "")

    _write_transport_config(data_dir, "lets_encrypt")
    assert _resolve_health_endpoint(data_dir, {}) == ("https", "")

    _write_transport_config(data_dir, "off")
    assert _resolve_health_endpoint(data_dir, {}) == ("http", "")

    (data_dir / "config.json").write_text(
        json.dumps({"web_transport": "not-a-dict"}), encoding="utf-8",
    )
    assert _resolve_health_endpoint(data_dir, {}) == ("http", "")


def test_resolve_health_endpoint_env_override_wins(tmp_path):
    data_dir = tmp_path / "data"
    _write_transport_config(data_dir, "self_signed", fingerprint="AABB")
    assert _resolve_health_endpoint(
        data_dir, {"TRPG_DOCKER_HEALTH_SCHEME": "http"}
    ) == ("http", "")
    assert _resolve_health_endpoint(
        data_dir, {"TRPG_DOCKER_HEALTH_SCHEME": "https"}
    ) == ("https", "AABB")
    assert _resolve_health_endpoint(
        data_dir, {"TRPG_DOCKER_HEALTH_SCHEME": "ftp"}
    ) == ("https", "AABB")


def test_normalized_fingerprint_strips_separators():
    assert _normalized_fingerprint("ab:cd-ef GH\n") == "ABCDEFGH"
    assert _normalized_fingerprint("") == ""


def test_verify_pinned_certificate_matches_and_rejects():
    import hashlib

    der = b"certificate-bytes"
    good = hashlib.sha256(der).hexdigest().upper()
    _verify_pinned_certificate(der, good)  # 匹配时不抛异常
    with pytest.raises(ssl.SSLError):
        _verify_pinned_certificate(der, "00" * 32)


def test_launcher_health_falls_back_to_http_when_https_unreachable(monkeypatch, tmp_path):
    from src.docker_launcher.launcher import _PinnedHTTPSHandler

    data_dir = tmp_path / "data"
    _write_transport_config(data_dir, "self_signed", fingerprint="AA" * 32)
    launcher = _launcher_with_data(tmp_path, data_dir)

    http_urls: list[str] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok": true, "version": "2.4.0"}'

    captured_handlers: list = []

    def fake_build_opener(*handlers):
        captured_handlers.extend(handlers)

        def _raise(_url, timeout):
            raise OSError("TLS nowhere")

        return SimpleNamespace(open=_raise)

    def fake_urlopen(url, timeout):
        http_urls.append(url)
        return Response()

    monkeypatch.setattr("src.docker_launcher.launcher.urllib.request.build_opener", fake_build_opener)
    monkeypatch.setattr("src.docker_launcher.launcher.urllib.request.urlopen", fake_urlopen)

    assert launcher._health("2.4.0") is True
    assert http_urls == ["http://127.0.0.1:9876/api/system/update/health"]
    assert isinstance(captured_handlers[0], _PinnedHTTPSHandler)


def test_launcher_health_accepts_pinned_self_signed_https(tmp_path):
    data_dir = tmp_path / "data"
    launcher = _launcher_with_data(tmp_path, data_dir)

    with _health_server(tmp_path, tls=True) as server:
        fingerprint = server.fingerprint
        colon_fingerprint = ":".join(fingerprint[i:i + 2] for i in range(0, len(fingerprint), 2))
        _write_transport_config(data_dir, "self_signed", fingerprint=colon_fingerprint + "\n")
        assert fingerprint == _normalized_fingerprint(colon_fingerprint)
        launcher.port = server.port
        assert launcher._health("2.4.0") is True
        assert launcher._last_health_error == ""


def test_launcher_health_rejects_mismatched_fingerprint(tmp_path):
    data_dir = tmp_path / "data"
    _write_transport_config(data_dir, "self_signed", fingerprint="BB" * 32)
    launcher = _launcher_with_data(tmp_path, data_dir)

    with _health_server(tmp_path, tls=True) as server:
        launcher.port = server.port
        assert launcher._health("2.4.0") is False


def test_launcher_health_survives_degraded_http_fallback(tmp_path):
    """配置声称 self_signed，但服务端证书加载失败回退 HTTP（原始 bug 场景）。"""
    data_dir = tmp_path / "data"
    _write_transport_config(data_dir, "self_signed", fingerprint="AA" * 32)
    launcher = _launcher_with_data(tmp_path, data_dir)

    with _health_server(tmp_path, tls=False) as server:
        launcher.port = server.port
        assert launcher._health("2.4.0") is True
