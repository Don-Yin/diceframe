"""Capability availability reaches the planner before it chooses a tool."""
from copy import deepcopy
import json

import pytest

from src.application_actions import ActionRegistry, ApplicationAction
from src.llm.client import LLMToolResponse
from src.webui.services.assistant_agent import AgentDependencies, AgentRuntime

pytest_plugins = ['tests.webapi_harness']


def initial_payload(user):
    history = json.loads(user)['agent_history']
    return next(json.loads(part['content']) for message in history for part in message['parts']
                if part.get('part_kind') == 'user-prompt')


def response(name, arguments):
    return LLMToolResponse([{'name': name, 'arguments': arguments}], 0, 'test')


@pytest.mark.asyncio
@pytest.mark.parametrize('route', ['overview', 'library'])
async def test_chinese_visibility_discovery_uses_live_index_without_rewriting_text(web_api, route):
    api, store, *_ = web_api
    store.create_lorebook({'id': 'visibility-book', 'name': 'Notes', 'source_kind': 'user'})
    store.add_book_entry('visibility-book', {'id': 'clue', 'name': 'Harbor',
        'content': 'Keep this authored text', 'visible_to': ['*'], 'extensions': {'custom': 7}})

    class Planner:
        calls = 0

        async def call_tools(self, system, user, **kwargs):
            self.calls += 1
            catalog = initial_payload(user)['capability_catalog']
            names = {item['name'] for item in catalog['capabilities']}
            assert 'set_lorebook_entry_visibility' in names
            assert all('parameters' not in item and 'handler' not in item for item in catalog['capabilities'])
            tools = {item['function']['name'] for item in kwargs['tools']}
            if self.calls == 1:
                assert ('set_lorebook_entry_visibility' in tools) is (route == 'library')
                return response('search_capabilities', {'query': '资料册的GM可见性'})
            if self.calls == 2:
                assert 'discovery_hint' in user and 'lorebook' in user
                return response('describe_capability', {'name': 'set_lorebook_entry_visibility'})
            assert 'set_lorebook_entry_visibility' in tools
            return response('set_lorebook_entry_visibility', {
                'book_id': 'visibility-book', 'entry_ids': ['clue'], 'audience': 'gm'})

    planner = Planner()
    api._llm_client.call_tools = planner.call_tools
    events = []

    async def emit(name, value):
        events.append((name, deepcopy(value)))

    await api.assistant_agent_run('owner', [{'role': 'user', 'content': '把资料册条目改成仅 GM 可见'}],
                                  'zh-CN', {'route': route}, '', emit)
    pending = next(value for name, value in events if name == 'approval')
    sid = next(value['session_id'] for name, value in events if name == 'session')
    assert store.get_book_entry('visibility-book', 'clue')['visible_to'] == ['*']
    assert pending['tool'] == 'set_lorebook_entry_visibility'
    await api.assistant_agent_confirm('owner', sid, pending['approval_id'], pending['plan_digest'], True)
    entry = store.get_book_entry('visibility-book', 'clue')
    assert entry['visible_to'] == []
    assert entry['content'] == 'Keep this authored text' and entry['extensions'] == {'custom': 7}


@pytest.mark.asyncio
async def test_new_domains_beyond_first_index_page_are_discoverable_without_agent_feature_code(tmp_path):
    calls = []

    async def handler(args, owner):
        calls.append(owner)
        return {'ok': True}

    registry = ActionRegistry(ApplicationAction(f'extra_{index:03}', f'Feature {index}',
        {'type': 'object', 'properties': {}, 'additionalProperties': False}, handler, domain='extension',
        instructions='Use the owning feature contract for this action.')
        for index in range(180))

    class Planner:
        requests = 0

        async def call_tools(self, system, user, **kwargs):
            self.requests += 1
            catalog = initial_payload(user)['capability_catalog']
            assert len(catalog['capabilities']) == 160 and catalog['has_more']
            if self.requests == 1:
                assert catalog['total'] == 180
                return response('search_capabilities', {'domain': 'extension', 'offset': 160})
            if self.requests == 2:
                assert 'extra_179' in user
                return response('describe_capability', {'name': 'extra_179'})
            if self.requests == 3:
                definition = next(tool['function'] for tool in kwargs['tools']
                                  if tool['function']['name'] == 'extra_179')
                assert 'Use the owning feature contract' in definition['description']
                return response('extra_179', {})
            return response('final_result', {'answer': 'Done'})

    agent = AgentRuntime(AgentDependencies(lambda: Planner(), lambda _: None, (), tmp_path, registry=registry))
    events = []

    async def emit(name, value):
        events.append((name, deepcopy(value)))

    await agent.run('owner', [{'role': 'user', 'content': 'Use the last new feature'}], 'en', {}, '', emit)
    assert calls == ['owner'] and ('delta', {'delta': 'Done'}) in events


@pytest.mark.asyncio
@pytest.mark.parametrize('source_kind', ['user', 'plugin'])
async def test_wired_whole_book_approval_preserves_text_and_replays_receipt_once(web_api, source_kind):
    api, store, *_ = web_api
    store.create_lorebook({'id': 'whole-book', 'name': 'Complete book', 'source_kind': source_kind})
    store.bind_lorebook({'id': 'whole-game', 'book_id': 'whole-book', 'scope_kind': 'game',
                        'scope_id': 'web|visibility-room|owner'})
    for index in range(35):
        store.add_book_entry('whole-book', {'id': f'whole-{index:02}', 'name': f'Note {index}',
            'content': f'Original {index}', 'visible_to': ['*'], 'extensions': {'custom': index}})
    before = store.list_book_entries('whole-book')

    class Planner:
        async def call_tools(self, system, user, **kwargs):
            definition = next(tool['function'] for tool in kwargs['tools']
                              if tool['function']['name'] == 'set_lorebook_visibility')
            assert 'content' not in definition['parameters']['properties']
            return response('set_lorebook_visibility', {'book_id': 'whole-book', 'audience': 'gm'})

    api._llm_client.call_tools = Planner().call_tools
    events = []

    async def emit(name, value):
        events.append((name, deepcopy(value)))

    await api.assistant_agent_run('owner', [{'role': 'user', 'content': '把这整本资料册设成仅 GM 可见'}],
                                  'zh-CN', {'route': 'library'}, '', emit)
    plan = next(value for name, value in events if name == 'approval')
    sid = next(value['session_id'] for name, value in events if name == 'session')
    assert plan['preview']['changed_count'] == 35 and plan['preview']['batch_count'] == 3
    assert plan['preview']['affected_games'] == ['web|visibility-room|owner']
    assert store.list_book_entries('whole-book') == before
    result = await api.assistant_agent_confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    replay = await api.assistant_agent_confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    assert result == replay and result['result']['changed_count'] == 35
    assert len(api.assistant_content_operations('owner')['operations']) == 3
    for original, current in zip(before, store.list_book_entries('whole-book')):
        assert current['visible_to'] == []
        assert {key: value for key, value in current.items() if key not in {'visible_to', 'updated_at'}} == {
            key: value for key, value in original.items() if key not in {'visible_to', 'updated_at'}}


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['new_entry', 'new_binding'])
async def test_whole_book_pending_plan_rejects_changed_scope_before_any_write(web_api, change):
    api, store, *_ = web_api
    store.create_lorebook({'id': 'stale-book', 'name': 'Stale', 'source_kind': 'user'})
    store.add_book_entry('stale-book', {'id': 'earlier', 'name': 'Earlier', 'content': 'Keep', 'visible_to': ['*']})

    class Planner:
        async def call_tools(self, *args, **kwargs):
            return response('set_lorebook_visibility', {'book_id': 'stale-book', 'audience': 'gm'})

    api._llm_client.call_tools = Planner().call_tools
    events = []

    async def emit(name, value):
        events.append((name, deepcopy(value)))

    await api.assistant_agent_run('owner', [{'role': 'user', 'content': 'Set the entire book GM-only'}],
                                  'en', {'route': 'library'}, '', emit)
    plan = next(value for name, value in events if name == 'approval')
    sid = next(value['session_id'] for name, value in events if name == 'session')
    if change == 'new_entry':
        store.add_book_entry('stale-book', {'id': 'newer', 'name': 'Newer', 'content': 'New', 'visible_to': ['*']})
    else:
        store.bind_lorebook({'id': 'later-binding', 'book_id': 'stale-book', 'scope_kind': 'game',
                            'scope_id': 'web|newly-affected-room|owner'})
    with pytest.raises(ValueError):
        await api.assistant_agent_confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    assert all(row['visible_to'] == ['*'] for row in store.list_book_entries('stale-book'))
    assert api.assistant_content_operations('owner')['operations'] == []
