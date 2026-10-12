"""Shared contract for DiceFrame managed-Docker update packages.

This module intentionally uses only the Python standard library.  The image
launcher imports it before any versioned application dependencies are loaded.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = 1
LAUNCHER_SCHEMA = 1
RUNTIME_API = 1
PLATFORM = "linux-amd64"
PYTHON_ABI = "cp311"
MAX_ARCHIVE_MEMBERS = 20_000
MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024
DOCKER_ASSET_RE = re.compile(
    r"^DiceFrame-v(?P<version>[0-9A-Za-z][0-9A-Za-z._+-]{0,63})-"
    r"docker-update-linux-amd64\.zip$"
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    normalized = str(expected or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError(f"invalid SHA-256 for {path.name}")
    actual = file_sha256(path)
    if not hmac.compare_digest(actual, normalized):
        raise ValueError(
            f"SHA-256 mismatch for {path.name}: expected {normalized[:8]}..., "
            f"got {actual[:8]}..."
        )


def safe_version_dir(version: str) -> str:
    normalized = str(version or "").strip().lstrip("vV")
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}", normalized):
        raise ValueError(f"invalid version: {version}")
    return "v" + normalized


def path_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _member_path(name: str) -> PurePosixPath:
    normalized = str(name or "").replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"unsafe update path: {name}")
    return path


def safe_extract_package(archive: Path, destination: Path) -> Path:
    """Extract one Docker update ZIP without trusting archive paths or modes."""

    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        if not members or len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError("Docker update package is empty or has too many files")
        total_size = 0
        top_levels: set[str] = set()
        checked: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        for member in members:
            relative = _member_path(member.filename)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"Docker update package contains a symlink: {member.filename}")
            file_type = stat.S_IFMT(mode)
            if file_type and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ValueError(f"Docker update package contains a special file: {member.filename}")
            total_size += int(member.file_size)
            if total_size > MAX_EXTRACTED_BYTES:
                raise ValueError("Docker update package expands beyond the size limit")
            top_levels.add(relative.parts[0])
            checked.append((member, relative))
        if len(top_levels) != 1:
            raise ValueError("Docker update package must contain one top-level directory")

        root = destination.resolve()
        for member, relative in checked:
            target = (destination / Path(*relative.parts)).resolve()
            if not path_within(target, root):
                raise ValueError(f"Docker update path escapes extraction root: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)

    extracted = destination / next(iter(top_levels))
    if not extracted.is_dir():
        raise ValueError("Docker update top-level directory is invalid")
    return extracted


def load_manifest(package_root: Path) -> dict[str, Any]:
    manifest_path = package_root / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Docker update manifest is missing or invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("Docker update manifest must be an object")
    return payload


def validate_manifest(
    payload: dict[str, Any],
    *,
    expected_version: str | None = None,
    platform: str = PLATFORM,
    python_abi: str = PYTHON_ABI,
    runtime_api: int = RUNTIME_API,
    launcher_schema: int = LAUNCHER_SCHEMA,
) -> dict[str, Any]:
    required = {
        "schema", "version", "platform", "python_abi", "launcher_schema_min",
        "runtime_api", "entrypoint", "site_packages", "health_path",
        "probation_seconds", "data_rollback_safe",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError("Docker update manifest is missing: " + ", ".join(missing))
    if int(payload.get("schema", 0) or 0) != SCHEMA_VERSION:
        raise ValueError("unsupported Docker update manifest schema")
    version = str(payload.get("version") or "").strip().lstrip("vV")
    safe_version_dir(version)
    if not re.fullmatch(
        r"\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", version,
    ):
        raise ValueError("Docker update version must be semantic versioning")
    if expected_version and version != str(expected_version).strip().lstrip("vV"):
        raise ValueError("Docker update manifest version does not match the release")
    if str(payload.get("platform")) != platform:
        raise ValueError(f"Docker update requires {payload.get('platform')}, running {platform}")
    if str(payload.get("python_abi")) != python_abi:
        raise ValueError(f"Docker update requires {payload.get('python_abi')}, running {python_abi}")
    if int(payload.get("launcher_schema_min", 0) or 0) > launcher_schema:
        raise ValueError("Docker update requires a newer base image launcher")
    if int(payload.get("runtime_api", 0) or 0) != runtime_api:
        raise ValueError("Docker update requires a different Docker base runtime")
    if payload.get("data_rollback_safe") is not True:
        raise ValueError(
            "Docker update cannot be auto-applied because its data migrations "
            "are not safe for the previous version"
        )
    if str(payload.get("entrypoint")) != "app/web_server.py":
        raise ValueError("Docker update entrypoint is unsupported")
    if str(payload.get("site_packages")) != "runtime/site-packages":
        raise ValueError("Docker update site-packages path is unsupported")
    health_path = str(payload.get("health_path") or "")
    if not health_path.startswith("/") or ".." in health_path:
        raise ValueError("Docker update health path is invalid")
    probation = int(payload.get("probation_seconds", 0) or 0)
    if probation < 0 or probation > 600:
        raise ValueError("Docker update probation period is invalid")
    return {**payload, "version": version, "probation_seconds": probation}


def validate_package_tree(
    package_root: Path,
    *,
    expected_version: str | None = None,
    **compatibility: Any,
) -> dict[str, Any]:
    manifest = validate_manifest(
        load_manifest(package_root), expected_version=expected_version, **compatibility,
    )
    required_files = (
        package_root / "app" / "web_server.py",
        package_root / "app" / "src" / "version.py",
        package_root / "app" / "static-v2" / "index.html",
    )
    if not all(path.is_file() for path in required_files):
        raise ValueError("Docker update package is missing required application files")
    version_text = required_files[1].read_text(encoding="utf-8")
    version_match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', version_text)
    if not version_match or version_match.group(1).strip().lstrip("vV") != manifest["version"]:
        raise ValueError("Docker update application version does not match its manifest")
    site_packages = package_root / "runtime" / "site-packages"
    if not site_packages.is_dir() or not any(site_packages.iterdir()):
        raise ValueError("Docker update package is missing its Python runtime dependencies")
    return manifest


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def current_python_abi() -> str:
    return f"cp{sys.version_info.major}{sys.version_info.minor}"
