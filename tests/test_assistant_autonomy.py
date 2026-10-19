from copy import deepcopy

import pytest

from src.application_actions import ActionRegistry
from src.webui.services.assistant_agent import AgentDependencies, AgentRuntime, AgentTool
from tests.test_assistant_agent import Planner


def make_runtime(tmp_path, planner, calls, clock=lambda: 100):
    schema = {'type': 'object', 'properties': {'book_id': {'type': 'string'}, 'value': {'type': 'string'}},
              'required': ['book_id', 'value'], 'additionalProperties': False}
    async def handler(args, owner):
        calls.append((owner, deepcopy(args)))
        return {'ok': True, 'value': args['value']}
    registry = ActionRegistry([AgentTool('edit', 'Edit book', schema, handler, mutation=True,
                                         domain='lorebook', automatic=True, guard=lambda args, owner: 'v1')])
    return AgentRuntime(AgentDependencies(llm_client=lambda: planner, configuration_error=lambda lang: None,
        tools=(), registry=registry, storage_dir=tmp_path, clock=clock))


async def run(agent, sid=''):
    events=[]
    async def emit(name, payload): events.append((name, deepcopy(payload)))
    await agent.run('owner', [{'role':'user','content':'edit the book'}], 'en', {}, sid, emit)
    return events


@pytest.mark.asyncio
async def test_task_authorization_executes_multiple_changes_and_keeps_receipts(tmp_path):
    calls=[]
    planner=Planner({'tool':'edit','arguments':{'book_id':'b','value':'one'}},
                    {'tool':'edit','arguments':{'book_id':'b','value':'two'}}, {'tool':'respond','answer':'done'})
    agent=make_runtime(tmp_path,planner,calls)
    grant=agent.authorize('owner', '', 'task', {'book_id':'b'}, ['lorebook'], 8)
    events=await run(agent, grant['session_id'])
    assert [row[1]['value'] for row in calls] == ['one','two']
    assert not any(name=='approval' for name,_ in events)
    snapshot=agent.snapshot('owner', grant['session_id'])
    assert len(snapshot['receipts']) == 2
    assert snapshot['authorization']['remaining_steps'] == 6
    assert any(name=='task' for name,_ in events)


@pytest.mark.asyncio
async def test_grant_cannot_cross_resource_scope_and_is_owner_private(tmp_path):
    calls=[]
    planner=Planner({'tool':'edit','arguments':{'book_id':'other','value':'bad'}})
    agent=make_runtime(tmp_path,planner,calls)
    grant=agent.authorize('owner','','task',{'book_id':'b'},['lorebook'],8)
    events=await run(agent,grant['session_id'])
    assert calls == []
    assert any(name=='approval' for name,_ in events)
    with pytest.raises(PermissionError):
        agent.authorize('other',grant['session_id'],'task',{},[],8)


@pytest.mark.asyncio
async def test_cancel_revokes_authorization_and_preserves_completed_results(tmp_path):
    calls=[]
    agent=make_runtime(tmp_path,Planner({'tool':'respond','answer':'ok'}),calls)
    grant=agent.authorize('owner','','routine',{},[],8)
    result=agent.cancel('owner',grant['session_id'])
    assert result['cancelled'] is True
    assert agent.snapshot('owner',grant['session_id'])['authorization'] is None
