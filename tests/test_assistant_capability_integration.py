"""Real application owners and disk; only the model planner is deterministic."""
from copy import deepcopy

import pytest

from tests.test_assistant_agent import Planner

pytest_plugins = ['tests.webapi_harness']


@pytest.mark.asyncio
async def test_real_visibility_only_task_discovers_new_action_and_keeps_content(web_api):
    api, store, registry, llm, _ = web_api
    store.create_lorebook({'id': 'task-book', 'name': 'Task Book', 'source_kind': 'user'})
    store.add_book_entry('task-book', {'id': 'entry-a', 'name': 'Harbor', 'content': 'Unchanged text',
                                      'visible_to': ['*']})
    planner = Planner(
        {'tool': 'search_capabilities', 'arguments': {'query': 'visibility'}},
        {'tool': 'describe_capability', 'arguments': {'name': 'set_lorebook_entry_visibility'}},
        {'tool': 'set_lorebook_entry_visibility', 'arguments': {
            'book_id': 'task-book', 'entry_ids': ['entry-a'], 'audience': 'public'}},
        {'tool': 'set_lorebook_entry_visibility', 'arguments': {
            'book_id': 'task-book', 'entry_ids': ['entry-a'], 'audience': 'gm'}},
        {'tool': 'respond', 'answer': 'Done'},
    )
    llm.call_tools = planner.call_tools
    grant = api.assistant_agent_authorize('owner', '', 'task', {'book_id': 'task-book'}, [], 8)
    events = []
    async def emit(name, value): events.append((name, deepcopy(value)))
    await api.assistant_agent_run('owner', [{'role': 'user', 'content': 'Change only this entry audience twice'}],
                                  'en', {}, grant['session_id'], emit)
    assert not any(name == 'approval' for name, _ in events)
    row = store.get_book_entry('task-book', 'entry-a')
    assert row['content'] == 'Unchanged text' and row['name'] == 'Harbor' and row['visible_to'] == []
    snapshot = api.assistant_agent_session('owner', grant['session_id'])
    assert len(snapshot['receipts']) == 2
    assert snapshot['authorization']['remaining_steps'] == 6
    from src.webui.services.assistant_agent import AgentRuntime
    restarted = AgentRuntime(api._assistant_agent.deps)
    assert restarted.snapshot('owner', grant['session_id'])['receipts'] == snapshot['receipts']


def test_runtime_catalog_includes_wired_business_actions_and_keeps_credentials_private(web_api):
    api, *_ = web_api
    result = api.assistant_agent_capabilities('owner')
    names = {item['name'] for item in result['capabilities']}
    assert {'set_lorebook_entry_visibility', 'get_world_state', 'set_world_fact_visibility',
            'get_ruleset_available_actions', 'submit_ruleset_intent', 'perform_ruleset_rest',
            'complete_adventure_node', 'mutate_resource_recovery', 'set_room_preferences',
            'clone_world_from_template', 'update_lorebook_metadata', 'commit_lorebook_import'} <= names
    assert 'handler' not in repr(result)
