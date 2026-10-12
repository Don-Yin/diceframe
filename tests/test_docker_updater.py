from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.plugin_host.mirrors import FetchResult
from src.webui.services import updater


async def _unavailable_update_check() -> dict:
    return {"ok": False, "error": "update check not configured"}


def _service(
    data_dir: Path,
    root: Path,
    mirrors,
    check_updates=_unavailable_update_check,
) -> updater.UpdaterService:
    return updater.UpdaterService(
        updater.UpdaterDependencies(
            data_dir=data_dir,
            root=root,
            mirrors=mirrors,
            check_updates=check_updates,
        )
    )


def _asset(name: str, size: int = 1024) -> dict:
    return {"name": name, "download_url": f"https://example.com/{name}", "size": size}


def _docker_archive(path: Path, version: str = "2.4.0") -> None:
    top = f"DiceFrame-v{version}-docker-update-linux-amd64"
    manifest = {
        "schema": 1, "version": version, "platform": "linux-amd64",
        "python_abi": "cp311", "launcher_schema_min": 1, "runtime_api": 1,
        "data_rollback_safe": True,
        "entrypoint": "app/web_server.py", "site_packages": "runtime/site-packages",
        "health_path": "/api/system/update/health", "probation_seconds": 0,
    }
    with zipfile.ZipFile(path, "w") as package:
        package.writestr(f"{top}/manifest.json", json.dumps(manifest))
        package.writestr(f"{top}/app/web_server.py", "# server")
        package.writestr(f"{top}/app/src/version.py", f'__version__ = "{version}"')
        package.writestr(f"{top}/app/static-v2/index.html", "ok")
        package.writestr(f"{top}/runtime/site-packages/runtime.txt", "ok")


def test_docker_asset_selection_is_version_exact_and_prefers_manifest():
    name = "DiceFrame-v2.4.0-docker-update-linux-amd64.zip"
    latest = {"assets": [_asset(name), _asset("SHA256SUMS"), _asset(name + ".sha256")]}
    selected = updater.select_asset(latest, "docker", "2.4.0")
    assert selected and selected[0]["name"] == name
    assert selected[1] and selected[1]["name"] == "SHA256SUMS"
    assert updater.select_asset(latest, "docker", "2.4.1") is None


def test_checksum_manifest_requires_one_exact_filename():
    name = "update.zip"
    digest = "a" * 64
    assert updater.parse_sha256_manifest(f"{digest}  {name}\n", name) == digest
    with pytest.raises(ValueError, match="必须且只能"):
        updater.parse_sha256_manifest(f"{digest}  {name}\n{digest}  {name}\n", name)
    with pytest.raises(ValueError, match="必须且只能"):
        updater.parse_sha256_manifest(f"{digest}  other.zip\n", name)


def test_managed_docker_mode_requires_explicit_writable_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("TRPG_INSTALL_MODE", "docker-managed")
    monkeypatch.setenv("TRPG_DOCKER_RUNTIME_ROOT", str(tmp_path))
    result = updater.is_self_update_supported(tmp_path)
    assert result == {"supported": True, "mode": "docker", "reason": "", "hint": ""}


@pytest.mark.asyncio
async def test_docker_download_requires_checksum_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("TRPG_INSTALL_MODE", "docker-managed")
    monkeypatch.setenv("TRPG_DOCKER_RUNTIME_ROOT", str(tmp_path / "_updater"))
    (tmp_path / "_updater").mkdir()
    name = "DiceFrame-v2.4.0-docker-update-linux-amd64.zip"

    async def check_updates():
        return {"ok": True, "latest": {"version": "2.4.0", "assets": [_asset(name)]}}

    service = _service(tmp_path, tmp_path, SimpleNamespace(), check_updates)
    result = await service.download_update("docker")
    assert result["ok"] is False
    assert "SHA256SUMS" in result["error"]


@pytest.mark.asyncio
async def test_docker_download_and_prepare_candidate(tmp_path, monkeypatch):
    data = tmp_path / "data"
    runtime = data / "_updater"
    runtime.mkdir(parents=True)
    source = tmp_path / "source.zip"
    _docker_archive(source)
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    name = "DiceFrame-v2.4.0-docker-update-linux-amd64.zip"
    mirrors = SimpleNamespace()

    async def fetch(_url, **_kwargs):
        return FetchResult(ok=True, data=f"{digest}  {name}\n")

    async def download(_url, target, **_kwargs):
        target.write_bytes(content)
        return FetchResult(ok=True, mirror_name="test")

    mirrors.fetch_github_url = fetch
    mirrors.download_to_file = download
    monkeypatch.setenv("TRPG_INSTALL_MODE", "docker-managed")
    monkeypatch.setenv("TRPG_DOCKER_RUNTIME_ROOT", str(runtime))
    monkeypatch.setenv("TRPG_LEGACY_PLUGIN_DIR", str(tmp_path / "plugins"))
    async def check_updates():
        return {"ok": True, "latest": {
            "version": "2.4.0", "assets": [_asset(name, len(content)), _asset("SHA256SUMS")],
        }}

    service = _service(data, tmp_path, mirrors, check_updates)
    started = await service.download_update("docker")
    assert started["ok"] is True
    await service._task
    assert service.get_status()["state"] == "staged"
    applied = await service.apply_update()
    assert applied["ok"] is True
    await service._task
    assert service.get_status()["state"] == "restarting"
    signal = json.loads((runtime / "restart_signal.json").read_text(encoding="utf-8"))
    assert signal["relative_dir"] == "docker-versions/v2.4.0"
    assert (runtime / signal["relative_dir"] / "manifest.json").is_file()


def test_docker_prepare_reuses_matching_version_without_overwrite(tmp_path, monkeypatch):
    data = tmp_path / "data"
    runtime = data / "_updater"
    runtime.mkdir(parents=True)
    archive = tmp_path / "source.zip"
    _docker_archive(archive)
    monkeypatch.setenv("TRPG_DOCKER_RUNTIME_ROOT", str(runtime))
    monkeypatch.setenv("TRPG_LEGACY_PLUGIN_DIR", str(tmp_path / "plugins"))
    service = _service(data, tmp_path, SimpleNamespace())

    first = service._prepare_docker_update(archive, "2.4.0")
    marker = Path(first["candidate_dir"]) / "keep.txt"
    marker.write_text("preserved", encoding="utf-8")
    second = service._prepare_docker_update(archive, "2.4.0")

    assert second["candidate_dir"] == first["candidate_dir"]
    assert marker.read_text(encoding="utf-8") == "preserved"
