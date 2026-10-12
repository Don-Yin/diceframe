"""Local, memory-only Hub subset for browser E2E (never imported by product code).

Contract sources: src/hub_client.py, frontend-v2/src/features/peer/inviteCode.ts,
and frontend-v2/src/peer/{protocol/signaling,session/MultiPeerConnectionSession}.ts.
Invites are decoded in the browser; there is no invite-resolution HTTP endpoint.
WS authenticate carries peer_id/token. authenticated and peer-waiting acknowledge
it; peer-ready announces only host/guest neighbors via peer_id. Directed offer,
answer, ice, ice-complete, and complete carry target_peer_id; relay supplies
from_peer_id. peer-left announces disconnects; error terminates invalid sessions.
The parser also accepts peer-complete (ignored by the session) and room-complete.
No plugin/marketplace API is needed by the smoke suite (installed plugins are local).
Unknown routes deliberately remain 404 rather than silently accepting new contracts.

The client does not specify Hub completion policy. Here room-complete is emitted
only after both ends of EVERY host/guest edge report complete. Until then sockets
remain available for unused invitations. Tokens may reconnect after disconnect.
This is a test double, not an implementation of production retention/rate limits.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import secrets
from threading import Thread
from typing import Any, Iterator

from aiohttp import WSMsgType, web


@dataclass
class Room:
    code: str
    host: str
    tokens: dict[str, str]
    expires_at: datetime
    sockets: dict[str, web.WebSocketResponse] = field(default_factory=dict)
    completed: set[tuple[str, str]] = field(default_factory=set)
    finished: bool = False

    def neighbors(self, peer: str) -> list[str]:
        return [
            other
            for other in self.tokens
            if other != peer and (peer == self.host or other == self.host)
        ]


class FakeHub:
    """An aiohttp server bound only to loopback; port 0 reserves a free port."""

    def __init__(self, port: int = 0) -> None:
        self.port = port
        self.base_url = ""
        self.installations: dict[str, str] = {}
        self.rooms: dict[str, Room] = {}
        self.app = web.Application()
        self.app.add_routes(
            [
                web.post("/v1/installations", self.register),
                web.get("/v1/rendezvous/config", self.config),
                web.post("/v1/rendezvous/rooms", self.create_room),
                web.get("/v1/rendezvous/rooms/{code}/ws", self.websocket),
            ]
        )
        self.app.on_shutdown.append(self.shutdown_sockets)
        self.runner = web.AppRunner(self.app, shutdown_timeout=2)

    async def start(self) -> None:
        try:
            await self.runner.setup()
            site = web.TCPSite(self.runner, "127.0.0.1", self.port)
            await site.start()
            self.base_url = f"http://127.0.0.1:{self.runner.addresses[0][1]}"
        except BaseException:
            await self.runner.cleanup()
            raise

    async def close(self) -> None:
        await self.runner.cleanup()

    async def shutdown_sockets(self, _app: web.Application) -> None:
        sockets = [ws for room in self.rooms.values() for ws in room.sockets.values()]
        await asyncio.gather(
            *(ws.close(code=1001, message=b"E2E Hub stopped") for ws in sockets)
        )

    @staticmethod
    async def body(request: web.Request) -> dict[str, Any]:
        try:
            value = await request.json()
        except ValueError:
            raise web.HTTPBadRequest(reason="Expected JSON object")
        if not isinstance(value, dict):
            raise web.HTTPBadRequest(reason="Expected JSON object")
        return value

    async def register(self, request: web.Request) -> web.Response:
        body = await self.body(request)
        if (
            not isinstance(body.get("app_version"), str)
            or not isinstance(body.get("platform"), str)
            or not isinstance(body.get("telemetry_enabled"), bool)
        ):
            raise web.HTTPBadRequest(reason="Invalid installation")
        token = secrets.token_urlsafe(32)
        installation_id = secrets.token_hex(16)
        self.installations[token] = installation_id
        return web.json_response(
            {"installation_id": installation_id, "installation_token": token},
            status=201,
        )

    async def config(self, _request: web.Request) -> web.Response:
        return web.json_response(
            {"enabled": True, "entry_visible": True, "message": ""}
        )

    async def create_room(self, request: web.Request) -> web.Response:
        authorization = request.headers.get("Authorization", "")
        if (
            not authorization.startswith("Bearer ")
            or authorization[7:] not in self.installations
        ):
            raise web.HTTPUnauthorized()
        body = await self.body(request)
        count = body.get("peer_count")
        if type(count) is not int or not 2 <= count <= 32:
            raise web.HTTPBadRequest(
                reason="peer_count must be an integer from 2 to 32"
            )
        code = secrets.token_hex(4).upper()
        while code in self.rooms:
            code = secrets.token_hex(4).upper()
        host = f"h_{secrets.token_urlsafe(12)}"
        tokens = {host: secrets.token_urlsafe(32)}
        tokens.update(
            {
                f"p_{secrets.token_urlsafe(12)}": secrets.token_urlsafe(32)
                for _ in range(count - 1)
            }
        )
        room = Room(code, host, tokens, datetime.now(timezone.utc) + timedelta(hours=4))
        self.rooms[code] = room
        return web.json_response(
            {
                "protocol_version": 2,
                "topology": "host-star",
                "room_code": code,
                "host_peer_id": host,
                "host_token": tokens[host],
                "invitations": [
                    {"peer_id": peer, "token": token}
                    for peer, token in tokens.items()
                    if peer != host
                ],
                "expires_at": room.expires_at.isoformat(),
                "websocket_url": f"{self.base_url.replace('http://', 'ws://')}/v1/rendezvous/rooms/{code}/ws",
            },
            status=201,
        )

    @staticmethod
    async def error(ws: web.WebSocketResponse, code: str) -> None:
        await ws.send_json({"type": "error", "code": code, "message": code})
        await ws.close(code=1008, message=code.encode())

    async def websocket(self, request: web.Request) -> web.WebSocketResponse:
        room = self.rooms.get(request.match_info["code"])
        if room is None:
            raise web.HTTPNotFound()
        ws = web.WebSocketResponse(max_msg_size=64 * 1024)
        await ws.prepare(request)
        peer = None
        try:
            try:
                auth = await ws.receive_json(timeout=5)
            except (ValueError, TypeError, asyncio.TimeoutError):
                await self.error(ws, "authentication_required")
                return ws
            if not isinstance(auth, dict):
                await self.error(ws, "invalid_authentication")
                return ws
            claimed_peer = auth.get("peer_id")
            if (
                auth.get("type") != "authenticate"
                or not isinstance(claimed_peer, str)
                or claimed_peer not in room.tokens
                or auth.get("token") != room.tokens[claimed_peer]
            ):
                await self.error(ws, "invalid_authentication")
                return ws
            if room.finished or datetime.now(timezone.utc) >= room.expires_at:
                await self.error(ws, "room_expired")
                return ws
            if claimed_peer in room.sockets:
                await self.error(ws, "peer_already_connected")
                return ws
            peer = claimed_peer
            room.sockets[peer] = ws
            await ws.send_json(
                {
                    "type": "authenticated",
                    "peer_id": peer,
                    "is_host": peer == room.host,
                    "protocol_version": 2,
                }
            )
            neighbors = [
                other for other in room.neighbors(peer) if other in room.sockets
            ]
            if not neighbors:
                await ws.send_json({"type": "peer-waiting"})
            for other in neighbors:
                await ws.send_json(
                    {
                        "type": "peer-ready",
                        "peer_id": other,
                        "is_host": other == room.host,
                    }
                )
                await room.sockets[other].send_json(
                    {
                        "type": "peer-ready",
                        "peer_id": peer,
                        "is_host": peer == room.host,
                    }
                )
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    break
                try:
                    signal = message.json()
                except ValueError:
                    await self.error(ws, "invalid_signal")
                    break
                if not await self.relay(room, peer, ws, signal):
                    break
        finally:
            if peer is not None:
                room.sockets.pop(peer, None)
                if not room.finished:
                    room.completed = {
                        edge for edge in room.completed if peer not in edge
                    }
                    for other in room.neighbors(peer):
                        other_ws = room.sockets.get(other)
                        if other_ws is not None and not other_ws.closed:
                            await other_ws.send_json(
                                {"type": "peer-left", "peer_id": peer}
                            )
        return ws

    async def relay(
        self, room: Room, peer: str, ws: web.WebSocketResponse, signal: Any
    ) -> bool:
        if not isinstance(signal, dict):
            await self.error(ws, "invalid_signal")
            return False
        kind = signal.get("type")
        target = signal.get("target_peer_id")
        if (
            kind not in ("offer", "answer", "ice", "ice-complete", "complete")
            or target not in room.neighbors(peer)
            or target not in room.sockets
            or (kind == "offer" and peer != room.host)
            or (kind == "answer" and peer == room.host)
        ):
            await self.error(ws, "invalid_signal_target_or_type")
            return False
        # Only the server supplies sender identity; never trust from_peer_id.
        forwarded = {"type": kind, "from_peer_id": peer, "target_peer_id": target}
        field_name = {
            "offer": "description",
            "answer": "description",
            "ice": "candidate",
        }.get(kind)
        if field_name:
            if not isinstance(signal.get(field_name), dict):
                await self.error(ws, "invalid_signal_payload")
                return False
            forwarded[field_name] = signal[field_name]
        await room.sockets[target].send_json(forwarded)
        if kind == "complete":
            room.completed.add((peer, target))
            if len(room.completed) == 2 * (len(room.tokens) - 1):
                room.finished = True
                for connection in list(room.sockets.values()):
                    await connection.send_json({"type": "room-complete"})
        return True


@contextmanager
def running_fake_hub(port: int = 0) -> Iterator[FakeHub]:
    """Serve on a dedicated event-loop thread while the synchronous runner waits."""
    ready: Future[tuple[FakeHub, asyncio.AbstractEventLoop]] = Future()

    def serve() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        hub = FakeHub(port)
        try:
            loop.run_until_complete(hub.start())
            ready.set_result((hub, loop))
            loop.run_forever()
        except BaseException as exc:
            if not ready.done():
                ready.set_exception(exc)
            else:
                raise
        finally:
            loop.run_until_complete(hub.close())
            loop.close()

    thread = Thread(target=serve, name="e2e-fake-hub", daemon=True)
    thread.start()
    try:
        hub, loop = ready.result(timeout=10)
        try:
            yield hub
        finally:
            loop.call_soon_threadsafe(loop.stop)
    finally:
        thread.join(timeout=10)
        if thread.is_alive():
            raise RuntimeError("E2E fake Hub failed to stop")
