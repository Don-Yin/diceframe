"""Salted PBKDF2 password hashes shared by every password the host stores.

The owner access password (``src.webui.access_password``) and per-game room
passwords (``src.engine.modules.room_access``) use the same storage format:
``pbkdf2_sha256$<iterations>$<salt>$<hex digest>``.  This module only knows
the format; callers decide how candidates are normalized before comparing.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

HASH_PREFIX = "pbkdf2_sha256"
HASH_ITERATIONS = 210_000
MAX_HASH_ITERATIONS = 10_000_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), HASH_ITERATIONS)
    return f"{HASH_PREFIX}${HASH_ITERATIONS}${salt}${digest.hex()}"


def is_password_hash(value: object) -> bool:
    return isinstance(value, str) and value.startswith(f"{HASH_PREFIX}$")


def parse_password_hash(stored: object) -> tuple[int, str, str] | None:
    """Return ``(iterations, salt, hex digest)`` for a well-formed hash, else ``None``."""
    if not is_password_hash(stored):
        return None
    assert isinstance(stored, str)
    try:
        prefix, iterations_raw, salt, expected = stored.split("$", 3)
        iterations = int(iterations_raw)
        salt.encode("ascii")
        digest = bytes.fromhex(expected)
    except (UnicodeEncodeError, ValueError, TypeError):
        return None
    if (
        prefix != HASH_PREFIX
        or not 1 <= iterations <= MAX_HASH_ITERATIONS
        or not salt
        or len(digest) != hashlib.sha256().digest_size
    ):
        return None
    return iterations, salt, expected


def verify_password_hash(candidate: str, stored: object) -> bool:
    """Compare ``candidate`` to a stored hash in constant time.

    Anything that is not a well-formed hash (including a plaintext value)
    never matches.  The candidate is compared exactly as given.
    """
    parsed = parse_password_hash(stored)
    if parsed is None or not isinstance(candidate, str):
        return False
    iterations, salt, expected = parsed
    digest = hashlib.pbkdf2_hmac("sha256", candidate.encode("utf-8"), salt.encode("ascii"), iterations).hex()
    return hmac.compare_digest(digest, expected)
