from pathlib import Path

import pytest

from scripts import validate_docker_update


def test_docker_runtime_requires_cryptography_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        validate_docker_update, "_native_runtime_matches_target", lambda: False,
    )
    package_root = tmp_path / "package"
    site_packages = package_root / "runtime" / "site-packages"
    site_packages.mkdir(parents=True)

    with pytest.raises(ValueError, match="cffi, pycparser, _cffi_backend"):
        validate_docker_update.validate_runtime_dependencies(package_root)


def test_complete_docker_runtime_passes_structural_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        validate_docker_update, "_native_runtime_matches_target", lambda: False,
    )
    package_root = tmp_path / "package"
    site_packages = package_root / "runtime" / "site-packages"
    (site_packages / "cffi").mkdir(parents=True)
    (site_packages / "pycparser").mkdir()
    (site_packages / "_cffi_backend.cpython-311-x86_64-linux-gnu.so").touch()

    validate_docker_update.validate_runtime_dependencies(package_root)
