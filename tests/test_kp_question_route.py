from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.webui.routes.games import api_kp_question


class _Api:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str]] = []

    async def ask_kp_question(
        self, game_key: str, actor: str, question: str, visibility: str,
    ):
        self.calls.append((game_key, actor, question, visibility))
        return {
            "status": 200,
            "payload": {
                "ok": True,
                "answer": "这是一次桌外回答。",
                "advanced": False,
                "action_consumed": False,
                "visibility": visibility,
            },
        }


class _Pool:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def broadcast(self, game_key: str, payload: dict) -> None:
        self.events.append((game_key, payload))


@web.middleware
async def _player_identity(request: web.Request, handler):
    request["user_id"] = "p1"
    return await handler(request)


@pytest.mark.asyncio
async def test_kp_question_route_uses_question_channel_not_action_channel() -> None:
    api = _Api()
    app = web.Application(middlewares=[_player_identity])
    app["api"] = api
    app.router.add_post("/api/games/{game_key}/kp-question", api_kp_question)

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/games/web%7Croom%7Cbot/kp-question",
            json={"question": "我知道这扇门通向哪里吗？"},
        )
        body = await response.json()

    assert response.status == 200
    assert body["advanced"] is False
    assert body["action_consumed"] is False
    assert api.calls == [("web|room|bot", "p1", "我知道这扇门通向哪里吗？", "private")]


@pytest.mark.asyncio
async def test_kp_question_route_rejects_oversized_questions() -> None:
    api = _Api()
    app = web.Application(middlewares=[_player_identity])
    app["api"] = api
    app.router.add_post("/api/games/{game_key}/kp-question", api_kp_question)

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/games/web%7Croom%7Cbot/kp-question",
            json={"question": "问" * 1001},
        )
        body = await response.json()

    assert response.status == 400
    assert body["code"] == "QUESTION_TOO_LONG"
    assert api.calls == []


@pytest.mark.asyncio
async def test_party_question_notifies_the_table_talk_channel() -> None:
    api = _Api()
    pool = _Pool()
    app = web.Application(middlewares=[_player_identity])
    app["api"] = api
    app["connection_pool"] = pool
    app.router.add_post("/api/games/{game_key}/kp-question", api_kp_question)

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/games/web%7Croom%7Cbot/kp-question",
            json={"question": "大家都知道这件事吗？", "visibility": "party"},
        )

    assert response.status == 200
    assert api.calls == [("web|room|bot", "p1", "大家都知道这件事吗？", "party")]
    assert pool.events == [("web|room|bot", {"type": "table_talk_changed"})]
