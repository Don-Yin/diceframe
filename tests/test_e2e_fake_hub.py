"""Exercise the E2E double over HTTP/WS and through the real HubClient validator."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import re

import aiohttp
import pytest

from scripts.e2e_fake_hub import FakeHub, running_fake_hub
from src.hub_client import HubClient, HubUnavailable


@asynccontextmanager
async def hub_client(tmp_path):
    hub = FakeHub()
    await hub.start()
    client = HubClient(tmp_path, base_url=hub.base_url)
    try:
        yield hub, client
    finally:
        await client.close()
        await hub.close()


@pytest.mark.asyncio
async def test_config_identity_room_shape_and_no_room_limit(tmp_path):
    async with hub_client(tmp_path) as (hub, client):
        assert await client.rendezvous_config() == {
            "enabled": True,
            "entry_visible": True,
            "message": "",
        }
        assert not client.identity_file.exists()
        codes = set()
        for count in [2, 6, 32] + [2] * 10:
            room = await client.create_rendezvous_room(count)
            assert room["protocol_version"] == 2
            assert room["topology"] == "host-star"
            assert len(room["invitations"]) == count - 1
            assert re.fullmatch(r"[A-Z0-9]{8}", room["room_code"])
            assert re.fullmatch(r"h_[A-Za-z0-9_-]{8,64}", room["host_peer_id"])
            for invitation in room["invitations"]:
                assert re.fullmatch(r"p_[A-Za-z0-9_-]{8,64}", invitation["peer_id"])
                assert 32 <= len(invitation["token"]) <= 256
            assert room["websocket_url"].startswith(
                hub.base_url.replace("http:", "ws:")
            )
            assert datetime.fromisoformat(room["expires_at"]) > datetime.now(
                timezone.utc
            )
            codes.add(room["room_code"])
        assert len(codes) == 13
        assert len(hub.installations) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patch",
    [
        {"protocol_version": 1},
        {"protocol_version": 3},
        {"topology": "mesh"},
        {"host_token": None},
        {"invitations": []},
        {"invitations": [{"peer_id": "p_invalid", "token": 1}]},
        {"websocket_url": "https://example.invalid/ws"},
    ],
)
async def test_real_client_still_rejects_bad_room_shapes(tmp_path, monkeypatch, patch):
    async with hub_client(tmp_path) as (_hub, client):
        room = await client.create_rendezvous_room(2)

        async def malformed_room(_count):
            return {**room, **patch}

        monkeypatch.setattr(client, "_create_rendezvous_room_request", malformed_room)
        with pytest.raises(HubUnavailable):
            await client.create_rendezvous_room(2)


async def receive(ws, kind):
    message = await ws.receive_json(timeout=3)
    assert message["type"] == kind, message
    return message


async def authenticate(session, room, peer, token):
    ws = await session.ws_connect(room["websocket_url"])
    await ws.send_json({"type": "authenticate", "peer_id": peer, "token": token})
    assert await receive(ws, "authenticated") == {
        "type": "authenticated",
        "peer_id": peer,
        "is_host": peer == room["host_peer_id"],
        "protocol_version": 2,
    }
    return ws


@pytest.mark.asyncio
@pytest.mark.parametrize("guest_first", [False, True])
async def test_authenticate_relay_all_signals_and_complete(tmp_path, guest_first):
    async with (
        hub_client(tmp_path) as (_hub, client),
        aiohttp.ClientSession() as session,
    ):
        room = await client.create_rendezvous_room(2)
        host_id = room["host_peer_id"]
        guest = room["invitations"][0]
        peers = [(host_id, room["host_token"]), (guest["peer_id"], guest["token"])]
        if guest_first:
            peers.reverse()
        first = await authenticate(session, room, *peers[0])
        await receive(first, "peer-waiting")
        second = await authenticate(session, room, *peers[1])
        assert (await receive(first, "peer-ready"))["peer_id"] == peers[1][0]
        assert (await receive(second, "peer-ready"))["peer_id"] == peers[0][0]
        host, guest_ws = (second, first) if guest_first else (first, second)
        for source, target, source_id, target_id, payload in [
            (
                host,
                guest_ws,
                host_id,
                guest["peer_id"],
                {
                    "type": "offer",
                    "description": {"type": "offer", "sdp": "test-offer"},
                },
            ),
            (
                guest_ws,
                host,
                guest["peer_id"],
                host_id,
                {
                    "type": "answer",
                    "description": {"type": "answer", "sdp": "test-answer"},
                },
            ),
            (
                host,
                guest_ws,
                host_id,
                guest["peer_id"],
                {"type": "ice", "candidate": {"candidate": "test-ice"}},
            ),
            (guest_ws, host, guest["peer_id"], host_id, {"type": "ice-complete"}),
            (host, guest_ws, host_id, guest["peer_id"], {"type": "complete"}),
            (guest_ws, host, guest["peer_id"], host_id, {"type": "complete"}),
        ]:
            await source.send_json(
                {**payload, "target_peer_id": target_id, "from_peer_id": "spoofed"}
            )
            assert await receive(target, payload["type"]) == {
                **payload,
                "from_peer_id": source_id,
                "target_peer_id": target_id,
            }
        await receive(host, "room-complete")
        await receive(guest_ws, "room-complete")
        await host.close()
        await guest_ws.close()


@pytest.mark.asyncio
async def test_auth_and_host_star_isolation_and_reconnect(tmp_path):
    async with (
        hub_client(tmp_path) as (hub, client),
        aiohttp.ClientSession() as session,
    ):
        room = await client.create_rendezvous_room(3)
        host_id = room["host_peer_id"]
        guest, other_guest = room["invitations"]
        async with session.ws_connect(room["websocket_url"]) as invalid:
            await invalid.send_json(
                {"type": "authenticate", "peer_id": host_id, "token": guest["token"]}
            )
            assert (await receive(invalid, "error"))["code"] == "invalid_authentication"
        host = await authenticate(session, room, host_id, room["host_token"])
        await receive(host, "peer-waiting")
        guest_ws = await authenticate(session, room, guest["peer_id"], guest["token"])
        await receive(guest_ws, "peer-ready")
        await receive(host, "peer-ready")
        # An unoccupied invitation must keep the room open after this edge completes.
        for source, target, target_id in [
            (host, guest_ws, guest["peer_id"]),
            (guest_ws, host, host_id),
        ]:
            await source.send_json({"type": "complete", "target_peer_id": target_id})
            await receive(target, "complete")
        assert not hub.rooms[room["room_code"]].finished
        await guest_ws.close()
        assert (await receive(host, "peer-left"))["peer_id"] == guest["peer_id"]
        guest_ws = await authenticate(session, room, guest["peer_id"], guest["token"])
        await receive(guest_ws, "peer-ready")
        await receive(host, "peer-ready")
        other = await authenticate(
            session, room, other_guest["peer_id"], other_guest["token"]
        )
        assert (await receive(other, "peer-ready"))["peer_id"] == host_id
        assert (await receive(host, "peer-ready"))["peer_id"] == other_guest["peer_id"]
        await guest_ws.send_json(
            {"type": "ice-complete", "target_peer_id": other_guest["peer_id"]}
        )
        await receive(guest_ws, "error")
        await guest_ws.close()
        await host.close()
        await other.close()


@pytest.mark.asyncio
async def test_http_auth_validation_and_unknown_routes(tmp_path):
    async with (
        hub_client(tmp_path) as (hub, client),
        aiohttp.ClientSession() as session,
    ):
        response = await session.post(
            f"{hub.base_url}/v1/rendezvous/rooms", json={"peer_count": 2}
        )
        assert response.status == 401
        await client.create_rendezvous_room(2)
        token = next(iter(hub.installations))
        for count in [True, 1, 33, "2"]:
            response = await session.post(
                f"{hub.base_url}/v1/rendezvous/rooms",
                json={"peer_count": count},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status == 400
        for path in ["/v1/plugins", "/unknown", "/v1/rendezvous/rooms/UNKNOWN0/ws"]:
            response = await session.get(hub.base_url + path)
            assert response.status == 404


def test_sync_lifecycle_stops_even_when_runner_fails():
    with pytest.raises(RuntimeError, match="simulated runner failure"):
        with running_fake_hub() as hub:
            url = hub.base_url
            raise RuntimeError("simulated runner failure")

    async def cannot_connect():
        async with aiohttp.ClientSession() as session:
            with pytest.raises(aiohttp.ClientConnectorError):
                await session.get(url)

    asyncio.run(cannot_connect())
