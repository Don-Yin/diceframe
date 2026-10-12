"""Validate a managed-Docker update artifact without installing it."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.docker_launcher.contracts import (  # noqa: E402
    DOCKER_ASSET_RE,
    safe_extract_package,
    validate_package_tree,
)

FORBIDDEN_PARTS = {
    ".git", ".codex", ".claude", "data", "tests", "node_modules",
    "frontend-v2", "test-results", "playwright-report",
}


def _native_runtime_matches_target() -> bool:
    machine = platform.machine().lower()
    return (
        sys.platform.startswith("linux")
        and machine in {"amd64", "x86_64"}
        and sys.version_info[:2] == (3, 11)
    )


def validate_runtime_dependencies(package_root: Path) -> None:
    """Ensure the bundled Linux runtime is complete and actually importable."""
    site_packages = package_root / "runtime" / "site-packages"
    missing: list[str] = []
    for package_name in ("cffi", "pycparser"):
        if not (site_packages / package_name).is_dir():
            missing.append(package_name)
    if not any(site_packages.glob("_cffi_backend*.so")):
        missing.append("_cffi_backend")
    if missing:
        raise ValueError(
            "Docker update runtime is missing required dependencies: "
            + ", ".join(missing)
        )

    # The archive targets Linux AMD64 CPython 3.11. On the matching release
    # runner, load the compiled modules too; other hosts still get the
    # platform-neutral completeness checks above.
    if not _native_runtime_matches_target():
        return
    command = [
        sys.executable,
        "-S",
        "-c",
        (
            "import sys; "
            "sys.path.insert(0, sys.argv[1]); "
            "import _cffi_backend; "
            "from cryptography import x509; "
            "from cryptography.hazmat.bindings import _rust"
        ),
        str(site_packages.resolve()),
    ]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    result = subprocess.run(
        command,
        cwd=package_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        message = detail[-1] if detail else f"exit code {result.returncode}"
        raise ValueError(f"Docker update runtime import failed: {message}")


def validate_archive(archive: Path, expected_version: str | None = None) -> dict:
    match = DOCKER_ASSET_RE.fullmatch(archive.name)
    if not match:
        raise ValueError(f"invalid Docker update asset name: {archive.name}")
    filename_version = match.group("version")
    if expected_version and filename_version != expected_version.strip().lstrip("vV"):
        raise ValueError("Docker update filename version does not match the build version")
    with zipfile.ZipFile(archive) as package:
        for name in package.namelist():
            parts = set(Path(name.replace("\\", "/")).parts)
            if parts & FORBIDDEN_PARTS or Path(name).name.startswith(".env"):
                raise ValueError(f"Docker update contains forbidden content: {name}")

    temporary = Path(tempfile.mkdtemp(prefix="diceframe-docker-validate-"))
    try:
        package_root = safe_extract_package(archive, temporary)
        if package_root.name != archive.stem:
            raise ValueError("Docker update top-level directory must match the asset name")
        manifest = validate_package_tree(package_root, expected_version=filename_version)
        validate_runtime_dependencies(package_root)
        return manifest
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--version", default=None)
    args = parser.parse_args()
    manifest = validate_archive(args.archive.resolve(), args.version)
    print(
        f"valid Docker update: version={manifest['version']} "
        f"platform={manifest['platform']} runtime_api={manifest['runtime_api']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
