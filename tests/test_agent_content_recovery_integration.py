"""Bounded WebAPI acceptance coverage for Agent authored-content recovery."""

from __future__ import annotations

from copy import deepcopy
import json

import pytest

from src.llm.client import LLMToolResponse
from src.engine.game_instance import GameRegistry
from src.engine.game_state import GameState
from src.lorebook.resolver import resolve_active_books
from src.lorebook.store import LorebookStore
from src.webui.services.assistant_agent import AgentRuntime
from src.webui.services.character_cards import authoring_recovery_snapshot

pytest_plugins = ["tests.webapi_harness"]


def native_response(tool: str, arguments: dict) -> LLMToolResponse:
    return LLMToolResponse(
        tool_calls=[{"name": tool, "arguments": arguments}],
        total_tokens=0,
        provider_used="test",
    )


async def approve_agent_tool(api, llm, tool: str, arguments: dict, session_id: str = "", owner: str = "alice"):
    async def call_tools(*args, **kwargs):
        return native_response(tool, arguments)
    llm.call_tools = call_tools
    events = []

    async def emit(event, value):
        events.append((event, deepcopy(value)))

    await api.assistant_agent_run(owner, [{"role": "user", "content": tool}], "en", {}, session_id, emit)
    approval = next(value for event, value in events if event == "approval")
    result = await api.assistant_agent_confirm(owner, approval["session_id"] if "session_id" in approval else next(value["session_id"] for event, value in events if event == "session"), approval["approval_id"], approval["plan_digest"], True)
    sid = next(value["session_id"] for event, value in events if event == "session")
    return result, sid, approval


async def undo_operation(api, operation_id: str, session_id: str, owner: str = "alice"):
    planned = await api.assistant_agent_plan(owner, "undo_content_operation", {"operation_id": operation_id}, session_id)
    approval = planned["approval"]
    return await api.assistant_agent_confirm(owner, session_id, approval["approval_id"], approval["plan_digest"], True)


@pytest.mark.asyncio
async def test_real_agent_world_card_and_lorebook_edits_are_recoverable(web_api):
    api, store, _registry, llm, _worlds_dir = web_api
    world = api.create_world("Agent World", "Original world", "en")
    world_id = world["world_id"]
    card = api.save_character_card({
        "character_name": "Ada", "background": "Original background",
        "attributes": {"str": 10}, "mechanics": {"hp": 9},
    })["card"]
    card_id = card["id"]
    original_mechanics = card.get("mechanics")
    store.create_lorebook({"id": "agent-book", "name": "Agent Book", "source_kind": "user"})
    store.add_book_entry("agent-book", {
        "id": "canonical-entry", "name": "Original entry", "content": "Original text", "visible_to": [],
    })
    session_id = ""

    result, session_id, write_approval = await approve_agent_tool(api, llm, "write_lorebook_entries", {
        "book_id": "agent-book", "entries": [{
            "id": "canonical-entry", "name": "Edited entry", "content": "Edited text", "visibility": "public",
        }],
    }, session_id)
    assert result["ok"] and result["result"]["operation_id"]
    assert await api.assistant_agent_confirm("alice", session_id, write_approval["approval_id"], write_approval["plan_digest"], True) == result
    operation_id = result["result"]["operation_id"]
    edited = store.get_book_entry("agent-book", "canonical-entry")
    assert edited["id"] == "canonical-entry" and edited["content"] == "Edited text" and edited["visible_to"] == ["*"]
    undone = await undo_operation(api, operation_id, session_id)
    assert undone["ok"]
    restored = store.get_book_entry("agent-book", "canonical-entry")
    assert restored["id"] == "canonical-entry" and restored["content"] == "Original text" and restored["visible_to"] == []

    result, session_id, _ = await approve_agent_tool(api, llm, "edit_world", {
        "world_id": world_id, "name": "Edited world", "description": "Edited description", "language": "en",
        "world_setting": "Edited full setting", "starter_scene": "Edited opening",
    }, session_id)
    operation_id = result["result"]["operation_id"]
    edited_world = api.get_world_definition(world_id)["world"]
    assert edited_world["world_name"] == "Edited world"
    assert edited_world["world_setting"] == "Edited full setting"
    assert edited_world["starter_scene"] == "Edited opening"
    await undo_operation(api, operation_id, session_id)
    restored_world = api.get_world_definition(world_id)["world"]
    assert restored_world["world_name"] == "Agent World"
    assert restored_world["description"] == "Original world"
    assert restored_world["world_setting"] == "Original world"
    assert restored_world["starter_scene"] == "Original world"[:120]

    result, session_id, _ = await approve_agent_tool(api, llm, "edit_character_card", {
        "card_id": card_id, "character_name": "Edited Ada", "background": "Edited background",
        "race": "elf", "class": "wizard",
    }, session_id)
    operation_id = result["result"]["operation_id"]
    edited_card = next(row for row in api.list_character_cards()["cards"] if row["id"] == card_id)
    assert edited_card["character_name"] == "Edited Ada" and edited_card.get("mechanics") == original_mechanics
    await undo_operation(api, operation_id, session_id)
    restored_card = next(row for row in api.list_character_cards()["cards"] if row["id"] == card_id)
    assert restored_card["character_name"] == "Ada" and restored_card["background"] == "Original background"
    assert restored_card.get("mechanics") == original_mechanics


@pytest.mark.asyncio
async def test_pre_expansion_world_journal_can_still_undo_without_overwriting_full_setting(web_api):
    from src.webui.services.assistant_agent import _digest
    api, store, _registry, llm, _worlds = web_api
    identity = api.create_world('Legacy journal', 'Original description', 'en')['world_id']
    result, sid, _ = await approve_agent_tool(api, llm, 'edit_world', {
        'world_id': identity, 'name': 'Renamed', 'description': 'Edited description', 'language': 'en'})
    operation_id = result['result']['operation_id']
    operation = store.get_lorebook_operation(operation_id, _digest('alice'))
    payload = deepcopy(operation['payload'])
    for snapshot in ('before', 'after'):
        payload[snapshot]['fields'].pop('world_setting')
        payload[snapshot]['fields'].pop('starter_scene')
    store.update_lorebook_operation(operation_id, _digest('alice'), {'payload': payload})
    assert (await undo_operation(api, operation_id, sid))['ok']
    restored = api.get_world_definition(identity)['world']
    assert restored['world_name'] == 'Legacy journal'
    assert restored['world_setting'] == 'Original description'


@pytest.mark.asyncio
async def test_real_agent_recovery_is_owner_private_and_conflicts_after_manual_edit(web_api):
    api, store, _registry, llm, _worlds_dir = web_api
    api.create_world("Owner World", "Original", "en")
    result, session_id, _ = await approve_agent_tool(api, llm, "edit_world", {
        "world_id": next(row["id"] for row in api.list_worlds()["worlds"] if row["name"] == "Owner World"),
        "name": "Agent edit", "description": "Agent description", "language": "en",
    })
    operation_id = result["result"]["operation_id"]
    with pytest.raises(ValueError):
        await api.assistant_agent_plan("bob", "undo_content_operation", {"operation_id": operation_id}, "")
    world_id = next(row["id"] for row in api.list_worlds()["worlds"] if row["name"] == "Agent edit")
    api.update_world(world_id, "Human edit", "Human description", "en")
    with pytest.raises(ValueError, match="changed|不会覆盖"):
        await undo_operation(api, operation_id, session_id)


def test_card_recovery_fails_closed_on_duplicate_library_state(web_api):
    api, _store, _registry, _llm, _worlds_dir = web_api
    card = api.save_character_card({"character_name": "Duplicate", "background": "Same"})["card"]
    path = api._character_card_dependencies.cards_path
    cards = json.loads(path.read_text(encoding="utf-8"))
    cards.append({**card, "id": "duplicate-id"})
    path.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="重复"):
        authoring_recovery_snapshot(api._character_card_dependencies, card["id"])


@pytest.mark.asyncio
async def test_game_selection_and_confirmation_receipt_survive_real_disk_reload(web_api):
    api, store, registry, _llm, _worlds = web_api
    created = await api.create_game('template_world', players=[{
        'character_name': 'Tester', 'attributes': {'str': 10},
    }])
    assert created['ok'], created
    key = created['game_key']
    instance = api.get_game_instance(key)
    instance.state = GameState.ACTIVE_ACTION
    instance.round_number = 5
    await registry.save(instance)
    store.create_lorebook({'id': 'post-start-notes', 'name': 'Added later', 'source_kind': 'user', 'source_id': 'post-start-notes'})
    plan = await api.assistant_agent_plan('owner', 'set_game_lorebooks', {
        'game_key': key, 'book_ids': ['post-start-notes'],
    })
    approval = plan['approval']
    confirmed = await api.assistant_agent_confirm('owner', plan['session_id'], approval['approval_id'], approval['plan_digest'], True)
    assert confirmed['ok'], confirmed
    restarted_runtime = AgentRuntime(api._assistant_agent.deps)
    assert await restarted_runtime.confirm('owner', plan['session_id'], approval['approval_id'], approval['plan_digest'], True) == confirmed
    reloaded = await GameRegistry(registry.save_dir).load(instance.game_key)
    assert reloaded is not None
    reopened_store = LorebookStore(store.db_path)
    reopened_store.open()
    try:
        assert reloaded.world_id == instance.world_id and reloaded.round_number == 5
        assert reloaded.modules['content_binding']['book_selection'] == 'explicit'
        assert [ref['id'] for ref in reloaded.modules['content_binding']['book_refs']] == ['post-start-notes']
        assert {ref.book_id for ref in resolve_active_books(reloaded, store=reopened_store)} == {'post-start-notes'}
    finally:
        reopened_store.close()
