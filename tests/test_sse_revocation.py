"""An open player SSE stream ends once the credential that opened it is gone.

The ticket is checked only when the stream opens; without a re-check a device
cut off by seat-token rotation, seat removal or a room password change would
keep receiving the seat's narration and private messages.
"""

from __future__ import annotations

import asyncio

from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.engine.modules import room_access
from src.webui.connection_pool import ConnectionPool
from src.webui.routes.sse import register_sse
from src.webui.sse_ticket import SseTicketStore
from test_game_query_routes_http import ROOM_HEADER, _owner, _owner_password  # noqa: F401
from test_game_query_routes_http import play_env  # noqa: F401
from test_share_gm_seat_guard import _share_url, share_env  # noqa: F401


def _sse_app(env):
    env.app["sse_tickets"] = SseTicketStore()
    env.app["connection_pool"] = ConnectionPool()
    register_sse(env.app)
    return env.app


async def _open_stream(client, env, headers, uid=None):
    issued = await client.post(_share_url(env, "sse-ticket", uid), headers=headers)
    body = await issued.json()
    assert issued.status == 200, body
    stream = await client.get(f"/api/games/{env.key}/sse?ticket={body['ticket']}")
    assert stream.status == 200
    first = await asyncio.wait_for(stream.content.readuntil(b"\n\n"), 5)
    assert b'"baseline"' in first
    return stream


async def _rest_of_stream(stream) -> bytes:
    return await asyncio.wait_for(stream.content.read(), 5)


async def _rotate(env):
    room_access.issue_seat_token(env.instance, "p1")


async def _remove(env):
    await env.instance.remove_player("p1")


async def _change_room_password(env):
    room_access.set_room_password(env.instance, "a-new-room-password")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("revoke", "code"),
    [
        (_rotate, b"SEAT_TOKEN_INVALID"),
        (_remove, b"SEAT_TOKEN_INVALID"),
        (_change_room_password, b"ROOM_TOKEN_INVALID"),
    ],
    ids=["rotate", "remove", "room-password"],
)
async def test_revoked_seat_stream_ends(share_env, revoke, code):
    env = share_env
    seat = {"X-Seat-Token": room_access.issue_seat_token(env.instance, "p1")}
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_stream(client, env, {**seat, **ROOM_HEADER})
        await revoke(env)
        rest = await _rest_of_stream(stream)
    assert b"event: revoked" in rest
    assert code in rest


@pytest.mark.asyncio
async def test_owner_stream_survives_seat_rotation(share_env):
    env = share_env
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_stream(client, env, _owner(), uid="p1")
        await _rotate(env)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(stream.content.read(), 1.5)


@pytest.mark.asyncio
async def test_seat_stream_stays_open_while_its_credentials_hold(share_env):
    env = share_env
    seat = {"X-Seat-Token": room_access.issue_seat_token(env.instance, "p1")}
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_stream(client, env, {**seat, **ROOM_HEADER})
        # Another seat's rotation does not concern this stream.
        room_access.issue_seat_token(env.instance, "p2")
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(stream.content.read(), 1.5)


async def _close_entrance(env):
    room_access.replace_player_access_open(env.instance, False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("revoke", "code"),
    [
        (_rotate, b"SEAT_TOKEN_INVALID"),
        (_change_room_password, b"ROOM_TOKEN_INVALID"),
        (_close_entrance, b"PLAYER_ACCESS_CLOSED"),
    ],
    ids=["rotate", "room-password", "entrance-closed"],
)
async def test_header_authorized_stream_is_revalidated_too(share_env, revoke, code):
    """``/sse`` also accepts the seat headers directly, without a ticket."""
    env = share_env
    seat = {"X-Seat-Token": room_access.issue_seat_token(env.instance, "p1")}
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await client.get(_share_url(env, "sse"), headers={**seat, **ROOM_HEADER})
        assert stream.status == 200
        first = await asyncio.wait_for(stream.content.readuntil(b"\n\n"), 5)
        assert b'"baseline"' in first
        await revoke(env)
        rest = await _rest_of_stream(stream)
    assert b"event: revoked" in rest
    assert code in rest


@pytest.mark.asyncio
async def test_closed_entrance_ends_a_ticket_stream(share_env):
    env = share_env
    seat = {"X-Seat-Token": room_access.issue_seat_token(env.instance, "p1")}
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_stream(client, env, {**seat, **ROOM_HEADER})
        await _close_entrance(env)
        rest = await _rest_of_stream(stream)
    assert b"PLAYER_ACCESS_CLOSED" in rest
