"""Short-lived, single-use authorization tickets for browser EventSource."""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass

from aiohttp import web


@dataclass(frozen=True)
class SseGrant:
    """What a non-owner stream was authorized by; it must stay true while open.

    ``seat_credential`` is the stored digest of the seat token that issued the
    ticket ('' when no seat token was involved). ``room_password_hash`` is the
    room password hash at issue time ('' for a room without one).
    """

    seat_credential: str = ""
    room_password_hash: str = ""


@dataclass(frozen=True)
class OwnerGrant:
    """The owner credential a stream was opened with; it must stay valid.

    ``paired_device_id`` is the paired device whose token authenticated the
    owner ('' for the access password, or a server without one).
    ``access_password_hash`` is the stored access password hash at that time
    ('' when none was configured). A device-token owner is bound to its
    pairing only: changing the access password keeps pairings.
    """

    paired_device_id: str = ""
    access_password_hash: str = ""


def token_digest(token: str) -> str:
    """SHA-256 hex digest a grant keeps instead of a plaintext token."""
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BotGrant:
    """The bot credential (``X-Bot-Token``) a stream was opened with.

    ``token_digest`` is the SHA-256 of that token; the plaintext is never
    kept. ``via_global`` is true when the token was the global Bot API token;
    ``plugin_id`` names the plugin whose API token it was ('' for none). The
    stream stays authorized while either still holds for the token. The
    actor is the stream's user id and is re-checked against the table
    separately.
    """

    token_digest: str = ""
    via_global: bool = False
    plugin_id: str = ""


#: The grant a ticket-opened stream was issued under (None for a stream with
#: no credential to re-check, e.g. one served without the access middleware).
SSE_GRANT_KEY = web.RequestKey("sse_grant", object)


@dataclass(frozen=True)
class SseTicket:
    game_key: str
    user_id: str
    expires_at: float
    grant: SseGrant | OwnerGrant | BotGrant | None = None


class SseTicketStore:
    def __init__(self, ttl_seconds: int = 30, max_pending: int = 4096) -> None:
        self.ttl_seconds = max(5, int(ttl_seconds))
        self.max_pending = max(16, int(max_pending))
        self._tickets: dict[str, SseTicket] = {}

    @staticmethod
    def _digest(token: str) -> str:
        return token_digest(token)

    def _purge(self, now: float) -> None:
        expired = [digest for digest, ticket in self._tickets.items() if ticket.expires_at <= now]
        for digest in expired:
            self._tickets.pop(digest, None)
        while len(self._tickets) >= self.max_pending:
            oldest = min(self._tickets, key=lambda key: self._tickets[key].expires_at)
            self._tickets.pop(oldest, None)

    def issue(
        self,
        game_key: str,
        user_id: str,
        grant: SseGrant | OwnerGrant | BotGrant | None = None,
    ) -> tuple[str, int]:
        now = time.monotonic()
        self._purge(now)
        token = secrets.token_urlsafe(32)
        self._tickets[self._digest(token)] = SseTicket(
            game_key=game_key,
            user_id=user_id,
            expires_at=now + self.ttl_seconds,
            grant=grant,
        )
        return token, self.ttl_seconds

    def consume(self, token: str, game_key: str) -> SseTicket | None:
        if not token:
            return None
        ticket = self._tickets.pop(self._digest(token), None)
        if not ticket or ticket.expires_at <= time.monotonic() or ticket.game_key != game_key:
            return None
        return ticket
