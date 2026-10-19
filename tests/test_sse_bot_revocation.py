"""An open bot SSE stream ends once the bot credential that opened it is gone.

A bot or channel plugin authenticates with ``X-Bot-Token`` (the global Bot API
token or a plugin's own API token) and acts as ``X-Bot-Actor``. That is checked
once, when the stream opens; without a re-check a rotated global token, an
uninstalled or disabled plugin, or an actor no longer allowed at the table
would keep receiving the seat's narration and private messages.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer
import pytest

import web_server
from src.engine.modules import room_access
from src.plugin_host import PluginHost
from src.webui.access_control import WebAccessControl
from src.webui.access_password import hash_access_password
from src.webui.sse_ticket import SseTicketStore
from test_game_query_routes_http import ROOM_HEADER, _owner, _owner_password  # noqa: F401
from test_game_query_routes_http import play_env  # noqa: F401
from test_share_gm_seat_guard import share_env  # noqa: F401
from test_sse_revocation import _rest_of_stream, _sse_app

GLOBAL_TOKEN = "global-bot-token"
PLUGIN_ID = "chat-adapter"
PLUGIN_TOKEN = "chat-adapter-api-token"


def _plugin_runtime(*, enabled=True, running=True, permissions=("diceframe.http",)):
    return SimpleNamespace(
        manifest={"permissions": list(permissions)},
        schema={},
        config={"enabled": enabled},
        process=SimpleNamespace(returncode=None) if running else None,
    )


@pytest.fixture()
def bot_env(share_env, tmp_path, monkeypatch):
    monkeypatch.setitem(web_server.STATE, "bot_token", GLOBAL_TOKEN)
    host = PluginHost(tmp_path / "plugins", tmp_path / "plugin-data")
    host.plugins = {PLUGIN_ID: _plugin_runtime()}
    host._api_tokens[PLUGIN_ID] = PLUGIN_TOKEN
    share_env.app["plugin_host"] = host
    share_env.plugin_host = host
    return share_env


def _bot(token, actor="p1"):
    return {"X-Bot-Token": token, "X-Bot-Actor": actor}


async def _open_bot_stream(client, env, headers, *, ticket=False):
    if ticket:
        issued = await client.post(f"/api/games/{env.key}/sse-ticket", headers=headers)
        body = await issued.json()
        assert issued.status == 200, body
        stream = await client.get(f"/api/games/{env.key}/sse?ticket={body['ticket']}")
    else:
        stream = await client.get(f"/api/games/{env.key}/sse", headers=headers)
    assert stream.status == 200
    first = await asyncio.wait_for(stream.content.readuntil(b"\n\n"), 5)
    assert b'"baseline"' in first
    return stream


async def _assert_stays_open(stream):
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(stream.content.read(), 1.5)


def _rotate_global_token(env):
    web_server.STATE["bot_token"] = "a-rotated-global-bot-token"


def _clear_global_token(env):
    web_server.STATE["bot_token"] = ""


def _uninstall_plugin(env):
    env.plugin_host.plugins.pop(PLUGIN_ID, None)
    env.plugin_host._api_tokens.pop(PLUGIN_ID, None)


def _replace_plugin_token(env):
    env.plugin_host._api_tokens[PLUGIN_ID] = "a-new-plugin-api-token"


def _drop_http_permission(env):
    env.plugin_host.plugins[PLUGIN_ID] = _plugin_runtime(permissions=())


def _disable_plugin(env):
    # PluginHost.stop(): enabled -> False, the process is gone.
    runtime = env.plugin_host.plugins[PLUGIN_ID]
    runtime.config["enabled"] = False
    runtime.process = None


async def _remove_actor(env):
    await env.instance.remove_player("p1")


def _close_player_access(env):
    room_access.replace_player_access_open(env.instance, False)


@pytest.mark.asyncio
@pytest.mark.parametrize("ticket", [False, True], ids=["header", "ticket"])
@pytest.mark.parametrize(
    ("token", "revoke", "code"),
    [
        (GLOBAL_TOKEN, _rotate_global_token, b"BOT_TOKEN_REVOKED"),
        (GLOBAL_TOKEN, _clear_global_token, b"BOT_TOKEN_REVOKED"),
        (PLUGIN_TOKEN, _uninstall_plugin, b"PLUGIN_TOKEN_REVOKED"),
        (PLUGIN_TOKEN, _replace_plugin_token, b"PLUGIN_TOKEN_REVOKED"),
        (PLUGIN_TOKEN, _drop_http_permission, b"PLUGIN_TOKEN_REVOKED"),
        (PLUGIN_TOKEN, _disable_plugin, b"PLUGIN_TOKEN_REVOKED"),
        (GLOBAL_TOKEN, _close_player_access, b"PLAYER_ACCESS_CLOSED"),
    ],
    ids=["rotate", "clear", "uninstall", "replace", "permission", "disable", "access-closed"],
)
async def test_revoked_bot_stream_ends(bot_env, token, revoke, code, ticket):
    env = bot_env
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_bot_stream(client, env, _bot(token), ticket=ticket)
        revoke(env)
        rest = await _rest_of_stream(stream)
    assert b"event: revoked" in rest
    assert code in rest


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [GLOBAL_TOKEN, PLUGIN_TOKEN], ids=["global", "plugin"])
async def test_bot_stream_ends_when_its_actor_leaves(bot_env, token):
    env = bot_env
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_bot_stream(client, env, _bot(token))
        await _remove_actor(env)
        rest = await _rest_of_stream(stream)
    assert b"event: revoked" in rest
    assert b"BOT_ACTOR_INVALID" in rest


@pytest.mark.asyncio
async def test_plugin_stream_survives_global_token_rotation(bot_env):
    env = bot_env
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_bot_stream(client, env, _bot(PLUGIN_TOKEN))
        _rotate_global_token(env)
        await _assert_stays_open(stream)


@pytest.mark.asyncio
async def test_global_stream_survives_plugin_changes(bot_env):
    env = bot_env
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_bot_stream(client, env, _bot(GLOBAL_TOKEN))
        _uninstall_plugin(env)
        await _assert_stays_open(stream)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "runtime",
    [
        # An enabled plugin between restart's stop and start (or in crash backoff).
        _plugin_runtime(enabled=True, running=False),
        # Started from the UI switch without being enabled (require_enabled=False).
        _plugin_runtime(enabled=False, running=True),
    ],
    ids=["restarting", "force-started"],
)
async def test_plugin_stream_survives_while_plugin_is_not_turned_off(bot_env, runtime):
    env = bot_env
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_bot_stream(client, env, _bot(PLUGIN_TOKEN))
        env.plugin_host.plugins[PLUGIN_ID] = runtime
        await _assert_stays_open(stream)


@pytest.mark.asyncio
async def test_bot_stream_ignores_owner_and_room_credentials(bot_env):
    """A bot stream rests on the bot credential only: the access password and
    room password, which a bot never presented, do not end it."""
    env = bot_env
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_bot_stream(client, env, _bot(GLOBAL_TOKEN))
        web_server.STATE["access_token"] = hash_access_password("a-brand-new-password")
        room_access.set_room_password(env.instance, "a-new-room-password")
        room_access.issue_seat_token(env.instance, "p1")
        # Ordinary bot requests do not disturb it either.
        detail = await client.get(f"/api/games/{env.key}", headers=_bot(GLOBAL_TOKEN))
        assert detail.status == 200
        await _assert_stays_open(stream)


@pytest.mark.asyncio
async def test_gm_bot_stream_survives_closed_player_access(bot_env):
    """The GM seat may still be driven by a bot after the player entrance closes."""
    env = bot_env
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_bot_stream(client, env, _bot(GLOBAL_TOKEN, actor=env.instance.gm_uid))
        _close_player_access(env)
        await _assert_stays_open(stream)


def _digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_plugin_stream_survives_restart_with_persisted_token(bot_env):
    """A restart stops the process and spawns a new one; the API token is
    persisted in the plugin's auth.json and reloaded unchanged."""
    env = bot_env
    host = env.plugin_host
    auth_file = host.data_dir / PLUGIN_ID / "auth.json"
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    auth_file.write_text('{"api_token": "%s"}' % PLUGIN_TOKEN, encoding="utf-8")
    async with TestClient(TestServer(_sse_app(env))) as client:
        stream = await _open_bot_stream(client, env, _bot(PLUGIN_TOKEN))
        runtime = host.plugins[PLUGIN_ID]
        runtime.process = None  # stop(keep_enabled=True): enabled stays on
        await _assert_stays_open(stream)
        # start() hands the new process the same token (TRPG_BOT_TOKEN).
        assert host._plugin_api_token(PLUGIN_ID) == PLUGIN_TOKEN
        runtime.process = SimpleNamespace(returncode=None)
        await _assert_stays_open(stream)


@pytest.mark.asyncio
async def test_bot_grant_never_holds_the_plaintext_token(bot_env):
    env = bot_env
    captured = []
    access = WebAccessControl({"bot_token": GLOBAL_TOKEN})

    async def handler(request):
        from src.webui.access_control import BOT_GRANT_KEY
        captured.append(request[BOT_GRANT_KEY])
        from aiohttp import web
        return web.json_response({"ok": True})

    from aiohttp import web
    app = web.Application(middlewares=[access.middleware])
    app["plugin_host"] = env.plugin_host
    app.router.add_get("/api/bot/ping", handler)
    async with TestClient(TestServer(app)) as client:
        for token in (GLOBAL_TOKEN, PLUGIN_TOKEN):
            response = await client.get("/api/bot/ping", headers={"X-Bot-Token": token})
            assert response.status == 200
    store = SseTicketStore()
    for grant, token in zip(captured, (GLOBAL_TOKEN, PLUGIN_TOKEN)):
        store.issue("k", "p1", grant)
        ticket = next(iter(store._tickets.values()))
        store._tickets.clear()
        for obj in (grant, ticket):
            for view in (repr(obj), str(dataclasses.asdict(obj)), str(vars(obj))):
                assert token not in view
        assert grant.token_digest == _digest(token)


def test_plugin_api_token_active_tracks_authentication_and_shutdown(tmp_path):
    host = PluginHost(tmp_path / "plugins", tmp_path / "plugin-data")
    host.plugins = {PLUGIN_ID: _plugin_runtime()}
    host._api_tokens[PLUGIN_ID] = PLUGIN_TOKEN
    digest = _digest(PLUGIN_TOKEN)
    assert host.api_token_active(PLUGIN_ID, digest) is True
    assert host.api_token_active(PLUGIN_ID, PLUGIN_TOKEN) is False  # plaintext is not a digest
    assert host.api_token_active(PLUGIN_ID, _digest("wrong")) is False
    assert host.api_token_active(PLUGIN_ID, "") is False
    assert host.api_token_active("other-plugin", digest) is False
    host.plugins[PLUGIN_ID] = _plugin_runtime(permissions=())
    assert host.api_token_active(PLUGIN_ID, digest) is False
    host.plugins[PLUGIN_ID] = _plugin_runtime(enabled=True, running=False)
    assert host.api_token_active(PLUGIN_ID, digest) is True
    host.plugins[PLUGIN_ID] = _plugin_runtime(enabled=False, running=True)
    assert host.api_token_active(PLUGIN_ID, digest) is True
    host.plugins[PLUGIN_ID] = _plugin_runtime(enabled=False, running=False)
    assert host.api_token_active(PLUGIN_ID, digest) is False
