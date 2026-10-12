"""An open owner SSE stream ends once the owner credential that opened it is gone.

The owner is authenticated once, when the ticket is issued (or the stream is
opened with the Authorization header). Without a re-check, a lost phone whose
pairing the owner revoked, or a browser still holding the old access password,
would keep receiving the stream.
"""

from __future__ import annotations

import asyncio

from aiohttp.test_utils import TestClient, TestServer
import pytest

import web_server
from src.webui.access_password import hash_access_password
from src.webui.device_tokens import DEVICE_TOKENS_KEY, DeviceTokenStore
from test_game_query_routes_http import ROOM_HEADER, _owner, _owner_password  # noqa: F401
from test_game_query_routes_http import play_env  # noqa: F401
from test_share_gm_seat_guard import _cookie, _share_url, share_env  # noqa: F401
from test_sse_revocation import _open_stream, _rest_of_stream, _sse_app


@pytest.fixture()
def device_env(share_env, tmp_path):
    devices = DeviceTokenStore(tmp_path / "devices")
    share_env.app[DEVICE_TOKENS_KEY] = devices
    phone_token, phone = devices.issue("phone")
    _, tablet = devices.issue("tablet")
    share_env.devices = devices
    share_env.phone = {"Authorization": f"Bearer {phone_token}"}
    share_env.phone_id = phone["id"]
    share_env.tablet_id = tablet["id"]
    return share_env


def _change_access_password():
    web_server.STATE["access_token"] = hash_access_password("a-brand-new-password")


async def _assert_stays_open(stream):
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(stream.content.read(), 1.5)


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke_all", [False, True], ids=["revoke", "revoke-all"])
async def test_device_stream_ends_when_its_pairing_is_revoked(device_env, revoke_all):
    env = device_env
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_stream(client, env, env.phone, uid="p1")
        if revoke_all:
            env.devices.revoke_all()
        else:
            env.devices.revoke(env.phone_id)
        rest = await _rest_of_stream(stream)
    assert b"event: revoked" in rest
    assert b"PAIRED_DEVICE_REVOKED" in rest


@pytest.mark.asyncio
async def test_device_stream_survives_unrelated_changes(device_env):
    """Another device's revocation and a password change (which keeps
    pairings) leave this device's stream alone."""
    env = device_env
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_stream(client, env, env.phone, uid="p1")
        env.devices.revoke(env.tablet_id)
        _change_access_password()
        # Ordinary requests by the device do not disturb it either.
        detail = await client.get(f"/api/games/{env.key}", headers=env.phone)
        assert detail.status == 200
        await _assert_stays_open(stream)


@pytest.mark.asyncio
async def test_password_stream_ends_when_the_access_password_changes(share_env):
    env = share_env
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_stream(client, env, _owner(), uid="p1")
        _change_access_password()
        rest = await _rest_of_stream(stream)
    assert b"event: revoked" in rest
    assert b"ACCESS_PASSWORD_CHANGED" in rest


@pytest.mark.asyncio
async def test_password_stream_survives_device_revocation(device_env):
    env = device_env
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_stream(client, env, _owner(), uid="p1")
        env.devices.revoke_all()
        detail = await client.get(f"/api/games/{env.key}", headers=_owner())
        assert detail.status == 200
        await _assert_stays_open(stream)


@pytest.mark.asyncio
@pytest.mark.parametrize("credential", ["password", "device"])
async def test_header_authorized_owner_stream_is_revalidated_too(device_env, credential):
    """``/sse`` also accepts the owner's Authorization header, without a ticket."""
    env = device_env
    headers = _owner() if credential == "password" else env.phone
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await client.get(_share_url(env, "sse", "p1"), headers=headers)
        assert stream.status == 200
        first = await asyncio.wait_for(stream.content.readuntil(b"\n\n"), 5)
        assert b'"baseline"' in first
        if credential == "password":
            _change_access_password()
        else:
            env.devices.revoke(env.phone_id)
        rest = await _rest_of_stream(stream)
    assert b"event: revoked" in rest
    expected = b"ACCESS_PASSWORD_CHANGED" if credential == "password" else b"PAIRED_DEVICE_REVOKED"
    assert expected in rest


@pytest.mark.asyncio
async def test_open_server_stream_ends_when_a_password_is_first_set(share_env):
    """Without an access password anyone who can reach the server is the
    owner; setting one locks the door on streams opened before it."""
    env = share_env
    web_server.STATE["access_token"] = ""
    async with TestClient(TestServer(_sse_app(env))) as client:
        issued = await client.post(
            f"/api/games/{env.key}/sse-ticket", headers=_cookie(env.token),
        )
        body = await issued.json()
        assert issued.status == 200, body
        stream = await client.get(f"/api/games/{env.key}/sse?ticket={body['ticket']}")
        first = await asyncio.wait_for(stream.content.readuntil(b"\n\n"), 5)
        assert b'"baseline"' in first
        _change_access_password()
        rest = await _rest_of_stream(stream)
    assert b"event: revoked" in rest
    assert b"ACCESS_PASSWORD_CHANGED" in rest
