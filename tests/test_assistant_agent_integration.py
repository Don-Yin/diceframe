"""Use real content owners, registry, game handler and saves; only LLM is fake."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from src.llm.client import LLMToolResponse

pytest_plugins = ["tests.webapi_harness"]


@pytest.mark.asyncio
async def test_web_api_uses_agent_budget_without_changing_text_generation_budget(web_api, monkeypatch):
    from src.webui.api import WebAPI

    original, store, registry, llm, worlds_dir = web_api
    requests = []

    async def call_tools(*args, **kwargs):
        requests.append(kwargs)
        return native_response({"tool": "respond", "answer": "Hello."})

    monkeypatch.setattr(llm, "call_tools", call_tools, raising=False)
    api = WebAPI(
        registry=registry, lorebook=store, memory=None,
        rules_dir=original._rules_dir, llm_client=llm, worlds_dir=worlds_dir,
        text_gen_max_tokens=2048, assistant_agent_max_tokens=8192,
    )
    events = []

    async def emit(event, data):
        events.append((event, data))

    await api.assistant_agent_run("owner", [{"role": "user", "content": "Write a short greeting."}], "en", {}, "", emit)
    assert len(requests) == 1
    assert requests[0]["max_tokens"] == 8192
    assert api.text_gen_max_tokens == 2048
    assert ("delta", {"delta": "Hello."}) in events


def native_response(step):
    """Translate the conceptual test step into the registered native contract."""
    if step.get("tool") == "respond":
        return LLMToolResponse(
            tool_calls=[{"name": "final_result", "arguments": {"answer": step.get("answer", "")}}],
            total_tokens=0,
            provider_used="test",
        )
    return LLMToolResponse(
        tool_calls=[{"name": step["tool"], "arguments": step.get("arguments", {})}],
        total_tokens=0,
        provider_used="test",
    )


@pytest.fixture
def content_api(tmp_path):
    from tests.test_module_install_hardening import _make_api
    from tests.webapi_harness import FakeLLMClient
    api, _host, store = _make_api(tmp_path / "data")
    llm = FakeLLMClient()
    api._llm_client = llm
    api._generation_dependencies = replace(api._generation_dependencies, llm_client=llm)
    try:
        yield api, store, llm
    finally:
        store.close()


@pytest.mark.asyncio
async def test_agent_drafts_reviews_saves_and_starts_real_game_without_duplicate_writes(web_api):
    api, store, registry, llm, worlds_dir = web_api
    api._assistant_agent.deps = replace(api._assistant_agent.deps, knowledge=None)
    mode = ["draft"]
    step_index = [0]
    draft_id_for_save = [None]
    async def plan(system, user, **kwargs):
        if mode[0] == "draft":
            if step_index[0] == 0:
                step = {"tool": "draft_content", "arguments": {"kind": "world", "prompt": "Write a coastal town", "language": "en"}}
            elif draft_id_for_save[0] is None:
                step = {"tool": "respond", "answer": "Draft is ready for review."}
            else:
                step = {"tool": "save_content", "arguments": {"draft_id": draft_id_for_save[0]}}
        else:
            card_id = api.list_character_cards()["cards"][0]["id"]
            step = {"tool": "create_game", "arguments": {"world_id": mode[0], "character_card_ids": [card_id], "language": "zh-CN"}}
        step_index[0] += 1
        return native_response(step)
    llm.call_tools = plan
    events = []
    async def emit(event, value):
        events.append((event, deepcopy(value)))

    before_worlds = len(store.list_worlds())
    await api.assistant_agent_run("alice", [{"role": "user", "content": "Write a world"}], "en", {"route": "creator"}, "", emit)
    assert len(store.list_worlds()) == before_worlds  # No generation side effects.
    sid = next(v["session_id"] for e, v in events if e == "session")
    draft_event = next(v for e, v in events if e == "draft")
    draft_id_for_save[0] = draft_event["draft_id"]
    edited = deepcopy(draft_event["review"]["draft"])
    edited["items"][0].update(name="Coastal town", text="A harbor with a lighthouse.")
    checked = await api.assistant_agent_review("alice", sid, draft_event["draft_id"], edited)
    assert not checked["review"]["blockers"]
    events.clear()
    await api.assistant_agent_run("alice", [{"role": "user", "content": "Save the edited draft"}], "en", {}, sid, emit)
    approval = next(v for e, v in events if e == "approval")
    result = await api.assistant_agent_confirm("alice", sid, approval["approval_id"], approval["plan_digest"], True)
    assert approval["preview"]["target_name"] == "Coastal town"
    assert result["ok"]
    saved_world = result["result"]["results"][0]["result"]["world_id"]
    assert store.get_world(saved_world)["description"] == "A harbor with a lighthouse."
    assert await api.assistant_agent_confirm("alice", sid, approval["approval_id"], approval["plan_digest"], True) == result
    assert len(store.list_worlds()) == before_worlds + 1

    api.save_character_card({"character_name": "Harbor explorer", "attributes": {"str": 10}})
    mode[0] = saved_world
    events.clear()
    await api.assistant_agent_run("alice", [{"role": "user", "content": "Start a game in my new world"}], "zh-CN", {}, sid, emit)
    approval = next(v for e, v in events if e == "approval")
    assert not registry.list_all()
    assert approval["preview"]["target_name"] == "Coastal town"
    assert approval["preview"]["characters"] == ["Harbor explorer"]
    created = await api.assistant_agent_confirm("alice", sid, approval["approval_id"], approval["plan_digest"], True)
    assert created["ok"], created
    key = created["result"]["game_key"]
    inst = api.get_game_instance(key)
    assert inst is not None and inst.gm_uid == "alice"
    assert inst.world_id == saved_world and "alice" in inst.players
    assert created["navigation"] == {"route": "play", "query": {"game": key}}
    assert await api.assistant_agent_confirm("alice", sid, approval["approval_id"], approval["plan_digest"], True) == created
    assert len(registry.list_all()) == 1
    with pytest.raises(PermissionError):
        api.assistant_agent_session("bob", sid)


@pytest.mark.asyncio
async def test_agent_adventure_markers_reach_actual_private_projection(content_api):
    api, store, llm = content_api
    before_adventures = api.list_adventures()["adventures"]
    api._assistant_agent.deps = replace(api._assistant_agent.deps, knowledge=None)
    step_index = [0]
    draft_id_for_save = [None]
    original_call = llm.call
    async def prose(system_prompt, user_message, **kwargs):
        result = await original_call(system_prompt, user_message, **kwargs)
        result.content = "# Harbor mystery\n## Arrival\n### Lighthouse {#lighthouse}\nYou see a lighthouse.\nGM: The keeper hid the bell. password=fictional-lock"
        result.narration = result.content
        return result
    llm.call = prose
    async def plan(system, user, **kwargs):
        if step_index[0] == 0:
            step = {"tool": "draft_content", "arguments": {"kind": "adventure", "prompt": "Write a harbor mystery", "language": "en"}}
        elif draft_id_for_save[0] is None:
            step = {"tool": "respond", "answer": "Draft is ready for review."}
        else:
            step = {"tool": "save_content", "arguments": {"draft_id": draft_id_for_save[0]}}
        step_index[0] += 1
        return native_response(step)
    llm.call_tools = plan
    events = []
    async def emit(event, value):
        events.append((event, deepcopy(value)))
    await api.assistant_agent_run("alice", [{"role": "user", "content": "Write an adventure"}], "en", {}, "", emit)
    draft = next(v for e, v in events if e == "draft")
    draft_id_for_save[0] = draft["draft_id"]
    assert not draft["review"]["blockers"]
    assert api.list_adventures()["adventures"] == before_adventures
    sid = next(v["session_id"] for e, v in events if e == "session")
    events.clear()
    await api.assistant_agent_run("alice", [{"role": "user", "content": "Save the reviewed adventure"}], "en", {}, sid, emit)
    approval = next(v for e, v in events if e == "approval")
    saved = await api.assistant_agent_confirm("alice", sid, approval["approval_id"], approval["plan_digest"], True)
    assert saved["ok"], saved
    detail = api.adventure_detail(saved["result"]["results"][0]["result"]["adventure_id"])
    serialized = json.dumps(detail, ensure_ascii=False)
    assert "The keeper hid the bell" in serialized
    nodes = detail["adventure"]["files"]["adventure.json"]["nodes"]
    note = next(node for node in nodes if "The keeper hid the bell" in node["description"])
    assert note["visibility"] == "gm" and note["type"] == "reference"
    assert "password=fictional-lock" in note["description"]
    assert all("The keeper hid the bell" not in node["description"] for node in nodes if node["type"] == "scene")
    assert not store.list_lorebooks()  # GM prose was never imported as a public book.
