from pathlib import Path

import pytest

from scripts.validate_portable_lock import validate_portable_lock


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_repository_portable_lock_covers_runtime_requirements() -> None:
    root = Path(__file__).resolve().parents[1]
    validate_portable_lock(root / "requirements.txt", root / "requirements-portable.lock")


def test_portable_lock_rejects_missing_direct_dependency(tmp_path: Path) -> None:
    requirements = _write(tmp_path / "requirements.txt", "aiohttp>=3\ncryptography>=43\n")
    lock = _write(
        tmp_path / "requirements-portable.lock",
        "aiohttp==3.14.1 --hash=sha256:" + "a" * 64 + "\n",
    )

    with pytest.raises(ValueError, match="cryptography"):
        validate_portable_lock(requirements, lock)


def test_portable_lock_requires_exact_version_and_hash(tmp_path: Path) -> None:
    requirements = _write(tmp_path / "requirements.txt", "aiohttp>=3\n")
    lock = _write(tmp_path / "requirements-portable.lock", "aiohttp==3.14.1\n")

    with pytest.raises(ValueError, match="SHA-256"):
        validate_portable_lock(requirements, lock)
