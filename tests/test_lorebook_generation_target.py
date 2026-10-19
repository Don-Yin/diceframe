from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from aiohttp import web

from src.llm.client import LLMResponse
from src.webui.routes.worlds import api_lorebook_generate
from webapi_harness import web_api  # noqa: F401  # pytest fixture


@pytest.mark.asyncio
async def test_lorebook_generation_writes_to_explicit_book_target(web_api):
    api, lorebook, _registry, fake_llm, _worlds_dir = web_api
    lorebook.create_world("target_world", "目标世界")
    lorebook.create_lorebook({"id": "book:target", "name": "目标资料册"})

    async def fake_call(system_prompt: str, user_message: str, **kwargs) -> LLMResponse:
        return LLMResponse(
            content=json.dumps({"entries": [{
                "name": "目标港口", "type": "location", "keywords": ["港口"],
                "content": "只应写入所选资料册。", "visibility": "public",
            }]}),
            narration="", state_update=None, memory_delta=None,
            info_asymmetry=None, plot_update=None, total_tokens=1,
            is_narration_only=True, provider_used="fake",
        )

    fake_llm.call = fake_call

    result = await api.generate_lorebook_entries(
        "target_world", "生成一个港口", book_id="book:target",
    )

    assert result["ok"] is True
    assert [entry["name"] for entry in lorebook.list_book_entries("book:target")] == ["目标港口"]
    assert lorebook.list_entries("target_world") == []


@pytest.mark.asyncio
async def test_lorebook_generation_rejects_book_bound_to_another_world(web_api):
    api, lorebook, _registry, _fake_llm, _worlds_dir = web_api
    lorebook.create_world("target_world", "目标世界")
    lorebook.create_world("other_world", "另一个世界")
    lorebook.create_lorebook({"id": "book:other-world", "name": "另一个世界的资料册"})
    lorebook.bind_lorebook({
        "id": "binding:other-world", "book_id": "book:other-world",
        "scope_kind": "world", "scope_id": "other_world",
    })

    result = await api.generate_lorebook_entries(
        "target_world", "不应写入", book_id="book:other-world",
    )

    assert result == {"ok": False, "error": "lorebook target is outside the current world/game scope"}


@pytest.mark.asyncio
async def test_lorebook_generation_rejects_game_target_from_another_world(web_api):
    api, lorebook, _registry, _fake_llm, _worlds_dir = web_api
    lorebook.create_world("target_world", "目标世界")
    lorebook.create_world("other_world", "另一个世界")
    lorebook.create_lorebook({"id": "book:game", "name": "游戏资料册"})
    lorebook.bind_lorebook({
        "id": "binding:game", "book_id": "book:game", "scope_kind": "game",
        "scope_id": "web|room|game-a",
    })
    api._world_dependencies = replace(api._world_dependencies, list_instances=lambda: [
        SimpleNamespace(game_key=("web", "room", "game-a"), world_id="other_world", players={"p1": {}}),
    ])

    result = await api.generate_lorebook_entries(
        "target_world", "不应跨世界写入", book_id="book:game", game_key="web|room|game-a",
    )

    assert result == {"ok": False, "error": "lorebook target is outside the current world/game scope"}


@pytest.mark.asyncio
async def test_lorebook_generation_rejects_game_binding_without_active_instance(web_api):
    api, lorebook, _registry, _fake_llm, _worlds_dir = web_api
    lorebook.create_world("target_world", "目标世界")
    lorebook.create_lorebook({"id": "book:missing-game", "name": "失效游戏资料册"})
    lorebook.bind_lorebook({
        "id": "binding:missing-game", "book_id": "book:missing-game", "scope_kind": "game",
        "scope_id": "web|room|missing",
    })

    result = await api.generate_lorebook_entries(
        "target_world", "不应写入不存在的游戏", book_id="book:missing-game", game_key="web|room|missing",
    )

    assert result == {"ok": False, "error": "lorebook target is outside the current world/game scope"}


def test_lorebook_list_entry_count_isolated_per_book(web_api):
    api, lorebook, _registry, _fake_llm, _worlds_dir = web_api
    lorebook.create_world("target_world", "目标世界")
    lorebook.create_lorebook({"id": "book:one", "name": "一号资料册"})
    lorebook.create_lorebook({"id": "book:two", "name": "二号资料册"})
    lorebook.add_book_entry("book:one", {"id": "entry:one", "name": "一号条目"})
    lorebook.add_book_entry("book:two", {"id": "entry:two", "name": "二号条目"})

    rows = {row["id"]: row for row in api.list_lorebooks("target_world")["books"]}

    assert rows["book:one"]["entry_count"] == 1
    assert rows["book:two"]["entry_count"] == 1


@pytest.mark.asyncio
async def test_lorebook_generation_route_rejects_shared_player_before_api_call():
    class Request(dict):
        app = {"api": SimpleNamespace(generate_lorebook_entries=lambda *args: pytest.fail("must not call API"))}
        match_info = {"world_id": "target_world"}
        query = {"user": "p1"}
        headers = {}

        async def json(self):
            return {"prompt": "玩家不应生成"}

    result = await api_lorebook_generate(Request())

    assert result.status == 403
    assert json.loads(result.text) == {"ok": False, "error_code": "OWNER_REQUIRED"}
