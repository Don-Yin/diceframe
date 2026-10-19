"""A closed player entrance is reported with a stable error code.

The web client keys its "the GM closed the entrance" notice (and stops
reconnecting) on ``error_code``; the Chinese ``error`` text stays for older
clients.
"""

from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from test_game_query_routes_http import (  # noqa: F401
    _make_app, _make_game, _owner_password, _player_url, _seat, play_env,
)


def _assert_closed(status, body):
    assert status == 403, body
    assert body == {
        "ok": False,
        "error_code": "PLAYER_ACCESS_CLOSED",
        "error": "本局玩家入口已关闭",
    }


@pytest.mark.asyncio
async def test_seat_request_to_closed_entrance_has_error_code(play_env) -> None:
    game_key, instance = _make_game(play_env, "closed-seat", open_access=False)
    async with TestClient(TestServer(_make_app(play_env))) as client:
        response = await client.get(
            _player_url(f"/api/games/{game_key}"), headers=_seat(instance),
        )
        body = await response.json()
    _assert_closed(response.status, body)


@pytest.mark.asyncio
async def test_lobby_request_to_closed_entrance_has_error_code(play_env) -> None:
    """A visitor without a seat yet (join page) gets the same code."""
    game_key, _ = _make_game(play_env, "closed-lobby", open_access=False)
    async with TestClient(TestServer(_make_app(play_env))) as client:
        response = await client.get(f"/api/games/{game_key}/characters?share=1")
        body = await response.json()
    _assert_closed(response.status, body)
