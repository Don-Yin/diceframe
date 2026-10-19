"""HTTP and share-link authority for recovery operations."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request
import pytest

from src.engine.game_instance import GameInstance
from src.engine.participant_view import Viewer
from src.engine.modules import room_access
from src.webui.access_control import WebAccessControl
from test_game_query_routes_http import (
    _make_app, _make_game, _owner,
    _owner_password,  # noqa: F401
    play_env,  # noqa: F401
)


async def client_for(service=None, instance=None):
    from src.webui.routes.resource_recovery import register

    if instance is None:
        instance = GameInstance(("web", "recovery", "host"))
        instance.gm_uid = "gm"
        instance.players["alice"] = {"character_name": "Alice", "character_sheet": {"hp": 10}}
    if service is None:
        service = SimpleNamespace(
            get=Mock(return_value={"ok": True, "sources": []}),
            mutate=AsyncMock(return_value={"ok": True, "source_id": "private-source", "seed": "secret"}),
        )

    @web.middleware
    async def identity(request, handler):
        request["user_id"] = request.headers.get("User", "")
        request["owner_authenticated"] = request.headers.get("Owner") == "yes"
        request["player_preview"] = request.headers.get("Preview") == "yes"
        request["player_delegate"] = request.headers.get("Delegate") == "yes"
        return await handler(request)

    app = web.Application(middlewares=[identity])
    app["api"] = SimpleNamespace(
        get_game_instance=lambda key: instance if key == "key" else None,
        resource_recovery=service,
    )
    pool = SimpleNamespace(broadcast=AsyncMock())
    app["connection_pool"] = pool
    register(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client, service, pool


@pytest.mark.asyncio
async def test_recovery_reads_require_membership_and_preserve_viewer_identity():
    client, service, _ = await client_for()
    async with client:
        assert (await client.get("/api/games/missing/recovery", headers={"User": "alice"})).status == 404
        assert (await client.get("/api/games/key/recovery")).status == 403
        service.get.assert_not_called()
        response = await client.get("/api/games/key/recovery", headers={"User": "alice"})
        assert response.status == 200
        service.get.assert_called_once_with("key", Viewer("seat", "alice"))


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["approve", "reject", "reward", "luck"])
async def test_keeper_recovery_operations_never_reach_service_for_a_player(action):
    client, service, pool = await client_for()
    async with client:
        response = await client.post(f"/api/games/key/recovery/{action}", json={}, headers={"User": "alice"})
        assert response.status == 403
        service.mutate.assert_not_called()
        pool.broadcast.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["request", "claim"])
async def test_preview_is_read_only_and_seat_cannot_choose_a_different_actor(action):
    client, service, _ = await client_for()
    async with client:
        path = f"/api/games/key/recovery/{action}"
        assert (await client.post(path, json={}, headers={"User": "alice", "Preview": "yes"})).status == 403
        assert (await client.post(path, json={"actor_uid": "bob"}, headers={"User": "alice"})).status == 403
        service.mutate.assert_not_called()
        response = await client.post(path, json={"run_id": "run"}, headers={"User": "alice", "Preview": "yes", "Delegate": "yes"})
        assert response.status == 200
        service.mutate.assert_awaited_once_with("key", Viewer("seat", "alice"), action, {"run_id": "run"})


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", ["{", "[]", "null", '"text"'])
async def test_invalid_recovery_json_returns_a_structured_bad_request(payload):
    client, service, _ = await client_for()
    async with client:
        response = await client.post("/api/games/key/recovery/request", data=payload,
                                     headers={"User": "alice", "Content-Type": "application/json"})
        assert response.status == 400
        assert (await response.json())["ok"] is False
        service.mutate.assert_not_called()


@pytest.mark.asyncio
async def test_recovery_broadcast_contains_only_an_invalidation_and_skips_duplicates_or_errors():
    client, service, pool = await client_for()
    async with client:
        path = "/api/games/key/recovery/request"
        headers = {"User": "alice"}
        assert (await client.post(path, json={}, headers=headers)).status == 200
        pool.broadcast.assert_awaited_once_with("key", {"type": "table_settings_changed"})
        service.mutate.return_value = {"ok": True, "duplicate": True}
        assert (await client.post(path, json={}, headers=headers)).status == 200
        service.mutate.return_value = {"ok": False, "code": "STALE_RECOVERY_REVISION", "error": "Refresh first"}
        response = await client.post(path, json={}, headers=headers)
        assert response.status == 409
        assert (await response.json())["code"] == "STALE_RECOVERY_REVISION"
        assert pool.broadcast.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["GM_ONLY", "MEMBER_REQUIRED", "ACTOR_FORBIDDEN", "NOT_SOURCE_OWNER", "READ_ONLY"])
async def test_service_permission_failures_remain_forbidden(code):
    client, service, _ = await client_for()
    service.mutate.return_value = {"ok": False, "code": code, "error": "Forbidden"}
    async with client:
        response = await client.post("/api/games/key/recovery/request", json={}, headers={"User": "alice"})
        assert response.status == 403
        assert (await response.json())["code"] == code


@pytest.mark.asyncio
@pytest.mark.parametrize("code,status", [("INVALID_REQUEST", 400), ("GAME_NOT_FOUND", 404), ("SAVE_FAILED", 500)])
async def test_service_failures_keep_their_structured_error_payload(code, status):
    client, service, pool = await client_for()
    failure = {"ok": False, "code": code, "error": "Recovery could not be saved"}
    service.mutate.return_value = failure
    async with client:
        response = await client.post("/api/games/key/recovery/request", json={}, headers={"User": "alice"})
        assert response.status == status
        assert await response.json() == failure
        pool.broadcast.assert_not_called()


@pytest.mark.parametrize("method,tail,kind", [
    ("GET", "recovery", "seat"),
    ("POST", "recovery/request", "seat"),
    ("POST", "recovery/claim", "seat"),
    ("POST", "recovery/approve", ""),
    ("POST", "recovery/reject", ""),
    ("POST", "recovery/reward", ""),
    ("POST", "recovery/luck", ""),
    ("GET", "recovery/reward", ""),
    ("GET", "recovery/claim/extra", ""),
    ("POST", "recovery/request/extra", ""),
    ("PUT", "recovery", ""),
])
def test_recovery_share_permissions_match_exact_player_operations(method, tail, kind):
    request = make_mocked_request(method, f"/api/games/key/{tail}")
    assert WebAccessControl.share_endpoint_kind(request) == kind


@pytest.mark.asyncio
async def test_recovery_registration_and_real_share_authentication_keep_seat_and_owner_separate(play_env):
    key, instance = _make_game(play_env, "recovery-http", bind_adventure=False, room_password=False)
    service = SimpleNamespace(get=Mock(return_value={"ok": True, "sources": []}),
                              mutate=AsyncMock(return_value={"ok": True}))
    play_env.api.resource_recovery = service
    seat = {"X-Seat-Token": room_access.issue_seat_token(instance, "p1")}
    path = f"/api/games/{key}/recovery"
    app = _make_app(play_env)
    async with TestClient(TestServer(app)) as client:
        response = await client.get(path + "?user=p1&share=1")
        assert response.status == 401
        assert (await response.json())["error_code"] == "SEAT_TOKEN_REQUIRED"
        response = await client.get(path + "?user=somebody-else&share=1", headers=seat)
        assert response.status == 200
        service.get.assert_called_once_with(key, Viewer("seat", "p1"))
        assert (await client.post(path + "/approve?share=1", headers=seat, json={})).status == 401
        service.mutate.assert_not_called()
        assert (await client.post(path + "/request?user=p1&share=1", headers=_owner(), json={})).status == 403
        assert (await client.post(path + "/request?user=p1&share=1&delegate=1", headers=_owner(), json={})).status == 200
        service.mutate.assert_awaited_once_with(key, Viewer("seat", "p1"), "request", {})
        assert (await client.post(path + "/approve", headers=_owner(), json={})).status == 200
        assert service.mutate.await_args.args[1].is_gm


@pytest.mark.asyncio
async def test_real_recovery_routes_keep_approval_authority_private_and_retry_once():
    from tests.test_resource_recovery_service import setup, body, GM
    from src.engine.world_state import clock_to_minutes, world_clock

    service, instance, _, _ = setup()
    client, _, pool = await client_for(service, instance)
    root = "/api/games/key/recovery"
    async with client:
        response = await client.post(root + "/request", json=body(service, instance, "rest-http", kind="overnight"),
                                     headers={"User": "alice"})
        assert response.status == 200
        pending = await response.json()
        source_id = pending["source_id"]
        assert pending["sources"][0]["status"] == "pending"
        assert instance.get_character_sheet("alice")["sanity"] == 40
        other = await (await client.get(root, headers={"User": "bob"})).json()
        assert other["sources"] == [] and other["receipts"] == []
        assert source_id not in str(other)
        approval = body(service, instance, "approve-http", source_id=source_id)
        assert (await client.post(root + "/approve", json=approval, headers={"User": "alice"})).status == 403
        response = await client.post(root + "/approve", json=approval, headers={"Owner": "yes"})
        assert response.status == 200
        settled = await response.json()
        assert settled["receipt"]["actor_uid"] == "alice"
        assert settled["receipt"]["time_advanced_minutes"] == 480
        sanity = instance.get_character_sheet("alice")["sanity"]
        assert 41 <= sanity <= 46
        assert clock_to_minutes(world_clock(instance.world_state)) == 480
        replay = await (await client.post(root + "/approve", json=approval, headers={"Owner": "yes"})).json()
        assert replay["duplicate"] is True
        assert instance.get_character_sheet("alice")["sanity"] == sanity
        assert clock_to_minutes(world_clock(instance.world_state)) == 480
        assert pool.broadcast.await_count == 2
        assert all(call.args[1] == {"type": "table_settings_changed"} for call in pool.broadcast.await_args_list)
        cross_actor = await client.post(root + "/claim", json=body(service, instance, "forged-http", source_id=source_id),
                                        headers={"User": "bob"})
        assert cross_actor.status == 403
        assert (await cross_actor.json())["code"] == "NOT_SOURCE_OWNER"
        for viewer_headers in ({"User": "alice"}, {"User": "bob"}, {"Owner": "yes"}):
            projected = await (await client.get(root, headers=viewer_headers)).json()
            assert "seed" not in str(projected)
            assert "commands" not in projected and "operations" not in projected
        assert service.get("key", GM)["receipts"][0]["after"] == sanity
