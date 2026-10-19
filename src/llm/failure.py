"""Safe failure categories for participant-facing AI recovery status."""
from __future__ import annotations

from aiohttp import ClientConnectionError, ClientResponseError


def safe_failure_reason(error: BaseException) -> str:
    cause = error
    seen: set[int] = set()
    for _ in range(8):
        if id(cause) in seen:
            break
        seen.add(id(cause))
        if isinstance(cause, TimeoutError):
            return "provider_timeout"
        if isinstance(cause, ClientResponseError):
            if cause.status in {401, 403}:
                return "provider_auth_failed"
            if cause.status == 429:
                return "provider_rate_limited"
        if isinstance(cause, ClientConnectionError):
            return "provider_connection_failed"
        if cause.__cause__ is None:
            break
        cause = cause.__cause__
    # Preserve the existing diagnostic contract without exposing exception text.
    return f"call_failed:{type(error).__name__}"
