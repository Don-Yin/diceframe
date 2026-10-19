"""Owner-prepared commands share one approval, scope check and durable receipt."""
import asyncio
from copy import deepcopy

import pytest

from src.application_actions import ActionAssessment, ApplicationAction, PreparedAction
from src.webui.services.assistant_agent import AgentDependencies, AgentRuntime, _digest
from tests.test_assistant_agent import Planner


def runtime(tmp_path, visibility='gm', scope=None, interrupt=False):
    writes = []
    interrupted = False
    arguments = {'targets': ['a', 'b'], 'audience': visibility}
    def prepare(args, owner):
        payload = deepcopy(args)
        return PreparedAction(_digest(payload), {'targets': [{'id': item, 'label': item} for item in args['targets']]},
            payload, ActionAssessment('disclosure' if args['audience'] == 'public' else 'write',
                                      args['audience'] == 'public', tuple({'book_id': item} for item in args['targets'])))
    async def execute(payload, owner, context):
        nonlocal interrupted
        completed = list(context.state.get('completed', []))
        for identity in payload['targets']:
            if identity in completed:
                continue
            context.check()
            writes.append(identity)
            completed.append(identity)
            context.checkpoint({'completed': completed})
            if interrupt and not interrupted:
                interrupted = True
                raise RuntimeError('Simulated process interruption after a committed target')
            await asyncio.sleep(0)
        return {'ok': True, 'status': 'completed', 'changed_count': len(completed)}
    tool = ApplicationAction('apply_selection', 'Apply selected targets', {
        'type': 'object', 'properties': {'targets': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 10},
                                       'audience': {'type': 'string'}}, 'required': ['targets', 'audience'],
        'additionalProperties': False}, lambda args, owner: {'ok': True, 'wrong_handler': True},
        mutation=True, domain='lorebook', effect='disclosure', prepare=prepare, execute=execute, resumable=True)
    planner = Planner({'tool': 'apply_selection', 'arguments': arguments}, {'tool': 'respond', 'answer': 'done'})
    agent = AgentRuntime(AgentDependencies(lambda: planner, lambda _: None, (tool,), tmp_path))
    grant = agent.authorize('owner', '', 'task', scope or {}, ['lorebook'], 8)
    return agent, grant['session_id'], writes


async def run(agent, sid):
    events = []
    async def emit(name, value):
        events.append((name, deepcopy(value)))
    await agent.run('owner', [{'role': 'user', 'content': 'Change all selected targets'}], 'en', {}, sid, emit)
    return events


@pytest.mark.asyncio
async def test_prepared_narrowing_runs_all_targets_under_one_task_grant(tmp_path):
    agent, sid, writes = runtime(tmp_path)
    events = await run(agent, sid)
    assert writes == ['a', 'b']
    assert not any(name == 'approval' for name, _ in events)
    assert len(agent.snapshot('owner', sid)['receipts']) == 1


@pytest.mark.asyncio
async def test_semantic_expansion_needs_one_approval_not_one_per_target(tmp_path):
    agent, sid, writes = runtime(tmp_path, 'public')
    events = await run(agent, sid)
    assert writes == []
    approvals = [value for name, value in events if name == 'approval']
    assert len(approvals) == 1
    plan = approvals[0]
    assert plan['prepared']['targets'] == ['a', 'b']
    response = await agent.confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    assert response['ok'] and writes == ['a', 'b']
    assert await agent.confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True) == response
    assert writes == ['a', 'b']


@pytest.mark.asyncio
async def test_prepared_command_cannot_expand_task_resource_scope(tmp_path):
    agent, sid, writes = runtime(tmp_path, scope={'book_id': 'a'})
    events = await run(agent, sid)
    assert writes == []
    plan = next(value for name, value in events if name == 'approval')
    await agent.confirm('owner', sid, plan['approval_id'], plan['plan_digest'], False)
    assert writes == []


@pytest.mark.asyncio
async def test_reviewed_execution_payload_cannot_be_changed_after_approval(tmp_path):
    agent, sid, writes = runtime(tmp_path, 'public')
    events = await run(agent, sid)
    plan = next(value for name, value in events if name == 'approval')
    agent.sessions[sid].data['pending']['prepared']['targets'].append('outside')
    with pytest.raises(ValueError, match='integrity'):
        await agent.confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    assert writes == []


@pytest.mark.asyncio
async def test_interrupted_prepared_execution_requires_explicit_resume_not_confirmation_replay(tmp_path):
    agent, sid, writes = runtime(tmp_path, interrupt=True)
    await run(agent, sid)
    snapshot = agent.snapshot('owner', sid)
    plan = snapshot['pending']
    assert writes == ['a'] and plan['resumable']
    assert len(snapshot['receipts']) == 1
    assert snapshot['task']['completed_steps'] == 0
    replay = await agent.confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    assert replay['pending']['resumable'] and writes == ['a']
    restarted = AgentRuntime(agent.deps)
    response = await restarted.resume('owner', sid, plan['approval_id'], plan['plan_digest'])
    assert response['ok'] and writes == ['a', 'b']
    assert restarted.snapshot('owner', sid)['pending'] is None
    assert restarted.snapshot('owner', sid)['task']['status'] == 'completed'
    assert restarted.snapshot('owner', sid)['task']['completed_steps'] == 1


@pytest.mark.asyncio
async def test_restarted_executing_plan_is_paused_until_owner_resumes(tmp_path):
    agent, sid, writes = runtime(tmp_path, interrupt=True)
    await run(agent, sid)
    session = agent.sessions[sid]
    session.data['status'] = 'executing'
    session.data['task']['status'] = 'running'
    session.data['pending'].pop('resumable', None)
    agent._write(session)
    restarted = AgentRuntime(agent.deps)
    snapshot = restarted.snapshot('owner', sid)
    assert snapshot['status'] == 'paused' and writes == ['a']
    assert snapshot['task']['status'] == 'paused'
    plan = snapshot['pending']
    assert plan['resumable'] and plan['execution_status'] == 'interrupted'
    await restarted.resume('owner', sid, plan['approval_id'], plan['plan_digest'])
    assert writes == ['a', 'b']


@pytest.mark.asyncio
async def test_automatic_plan_rechecks_live_grant_before_each_target(tmp_path):
    from dataclasses import replace
    agent, sid, writes = runtime(tmp_path)
    tool = agent.registry.get('apply_selection')
    original = tool.execute
    async def revoke_after_first(payload, owner, context):
        persist = context.checkpoint
        def checkpoint(state):
            persist(state)
            agent.sessions[sid].data['authorization'] = None
        context.checkpoint = checkpoint
        return await original(payload, owner, context)
    agent.registry.unregister(tool.name)
    agent.registry.register(replace(tool, execute=revoke_after_first))
    await run(agent, sid)
    assert writes == ['a']
    assert agent.snapshot('owner', sid)['pending']['resumable']
