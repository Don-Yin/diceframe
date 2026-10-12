"""Stable identity of one DiceFrame server installation.

Clients that sync content with several servers need to tell those servers
apart. A base URL is not an identity: a LAN address or a tunnel host changes
while the server (its data directory) stays the same. The instance id is a
random value generated once and stored in the data directory, so it follows
the data rather than the host, and it reveals nothing about the machine.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path

from aiohttp import web

logger = logging.getLogger("trpg")

SERVER_IDENTITY_FILE = "server_identity.json"
#: Error code for clients when the id cannot be produced.
SERVER_IDENTITY_UNAVAILABLE = "SERVER_IDENTITY_UNAVAILABLE"
_INSTANCE_ID_PATTERN = re.compile(r"^srv-[0-9a-f]{32}$")


class ServerIdentityError(RuntimeError):
    """The stored identity exists but cannot be trusted: fail closed."""


class ServerIdentityStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / SERVER_IDENTITY_FILE
        self._instance_id: str | None = None
        # A damaged file stays damaged until an operator repairs it: remember
        # the failure instead of re-reading (and re-logging) on every request.
        self._failure: ServerIdentityError | None = None
        self.failure_logged = False

    def instance_id(self) -> str:
        """Return the persisted id, generating it on first use.

        A present but unreadable or malformed file is never replaced: a fresh
        id would silently make every client treat this server as a new one.
        """

        if self._instance_id is not None:
            return self._instance_id
        if self._failure is not None:
            raise self._failure
        try:
            self._instance_id = self._read() if self.path.exists() else self._create()
        except ServerIdentityError as exc:
            self._failure = exc
            raise
        return self._instance_id

    def _create(self) -> str:
        """Publish a new id atomically; whoever publishes first wins.

        The content is written to a private temporary file and then hard-linked
        to the final name. The link fails if the name already exists, so two
        processes starting together can never both win, and a reader never
        sees a half-written file.
        """

        instance_id = f"srv-{uuid.uuid4().hex}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(temporary, "x", encoding="utf-8") as handle:
                handle.write(json.dumps({"version": 1, "instance_id": instance_id}))
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, self.path)
            except FileExistsError:
                return self._read()
        finally:
            temporary.unlink(missing_ok=True)
        return instance_id

    def _read(self) -> str:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ServerIdentityError("server identity file is unreadable") from exc
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ServerIdentityError("server identity file has an unknown shape")
        instance_id = payload.get("instance_id")
        if not isinstance(instance_id, str) or not _INSTANCE_ID_PATTERN.fullmatch(instance_id):
            raise ServerIdentityError("server identity file holds an invalid id")
        return instance_id


SERVER_IDENTITY_KEY = web.AppKey("server_identity", ServerIdentityStore)


def server_instance_id(app: web.Application) -> str | None:
    """The instance id for responses; ``None`` (and a log) if it is unusable."""

    store = app.get(SERVER_IDENTITY_KEY)
    if store is None:
        return None
    try:
        return store.instance_id()
    except (ServerIdentityError, OSError):
        if not store.failure_logged:
            store.failure_logged = True
            logger.error("服务器实例标识不可用，已从响应中省略", exc_info=True)
        return None
