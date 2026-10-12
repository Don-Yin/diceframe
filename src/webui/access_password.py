from __future__ import annotations

import hmac
from pathlib import Path

from src.password_hashing import (
    HASH_ITERATIONS,
    HASH_PREFIX,
    hash_password,
    is_password_hash,
    parse_password_hash,
    verify_password_hash,
)

__all__ = [
    "HASH_ITERATIONS",
    "HASH_PREFIX",
    "RESET_FILENAME",
    "consume_reset_password",
    "hash_access_password",
    "is_hashed_access_password",
    "is_valid_access_password",
    "mask_access_password",
    "normalize_access_password",
    "reset_file_path",
    "verify_access_password",
]

RESET_FILENAME = "reset_access_password.txt"


def normalize_access_password(value: object) -> str:
    """Treat empty or whitespace-only configuration as no password."""
    return str(value or "").strip()


def hash_access_password(password: str) -> str:
    return hash_password(password)


def is_hashed_access_password(value: str) -> bool:
    return is_password_hash(str(value or ""))


def is_valid_access_password(value: object) -> bool:
    stored = normalize_access_password(value)
    if not stored:
        return False
    if not is_hashed_access_password(stored):
        return True
    return parse_password_hash(stored) is not None


def verify_access_password(candidate: str, stored: str) -> bool:
    candidate = normalize_access_password(candidate)
    stored = normalize_access_password(stored)
    if not candidate or not is_valid_access_password(stored):
        return False
    if not is_hashed_access_password(stored):
        return hmac.compare_digest(candidate, stored)
    return verify_password_hash(candidate, stored)


def mask_access_password(value: str) -> dict[str, object]:
    if not is_valid_access_password(value):
        return {"configured": False, "masked": ""}
    return {"configured": True, "masked": "已设置"}


def reset_file_path(data_dir: Path) -> Path:
    return data_dir / RESET_FILENAME


def consume_reset_password(data_dir: Path) -> str:
    path = reset_file_path(data_dir)
    if not path.exists():
        return ""
    password = path.read_text(encoding="utf-8").strip()
    if len(password) < 6:
        raise RuntimeError(f"{path} 中的新访问密码至少需要 6 位。请修改后重新启动。")
    path.unlink()
    return password
