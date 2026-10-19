"""Owner-prepared commands share one approval, scope check and durable receipt."""
import asyncio
from copy import deepcopy
from dataclasses import replace

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


@pytest.mark.asyncio
@pytest.mark.parametrize('paused_seconds', [1800, 7200])
async def test_owner_can_reconfirm_expired_partial_plan_after_restart_without_replaying_success(tmp_path, paused_seconds):
    agent, sid, writes = runtime(tmp_path, visibility='public', interrupt=True)
    now = [agent.deps.clock()]
    agent.deps = replace(agent.deps, clock=lambda: now[0])
    events = await run(agent, sid)
    plan = next(value for name, value in events if name == 'approval')
    paused = await agent.confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    assert paused['pending']['resumable'] and writes == ['a']
    original_payload = deepcopy(paused['pending']['prepared'])
    now[0] += paused_seconds
    restarted = AgentRuntime(agent.deps)
    restored = restarted.snapshot('owner', sid)['pending']
    assert restored['plan_digest'] == plan['plan_digest']
    response = await restarted.resume('owner', sid, restored['approval_id'], restored['plan_digest'])
    assert response['ok'] and writes == ['a', 'b']
    assert restored['prepared'] == original_payload
    assert restored['expires_at'] == plan['expires_at']
    assert restarted.snapshot('owner', sid)['pending'] is None


@pytest.mark.asyncio
async def test_expired_unapproved_plan_cannot_use_resume_or_confirmation(tmp_path):
    agent, sid, writes = runtime(tmp_path, visibility='public')
    now = [agent.deps.clock()]
    agent.deps = replace(agent.deps, clock=lambda: now[0])
    events = await run(agent, sid)
    plan = next(value for name, value in events if name == 'approval')
    now[0] += 1800
    with pytest.raises(ValueError, match='No paused execution'):
        await agent.resume('owner', sid, plan['approval_id'], plan['plan_digest'])
    with pytest.raises(ValueError, match='Approval expired'):
        await agent.confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    assert writes == []


@pytest.mark.asyncio
async def test_first_confirmation_gets_execution_window_independent_of_proposal_expiry(tmp_path):
    agent, sid, writes = runtime(tmp_path, visibility='public')
    now = [agent.deps.clock()]
    agent.deps = replace(agent.deps, clock=lambda: now[0])
    action = agent.registry.get('apply_selection')
    original = action.execute
    async def advance_between_targets(payload, owner, context):
        persist = context.checkpoint
        def checkpoint(state):
            persist(state)
            now[0] += 2
        context.checkpoint = checkpoint
        return await original(payload, owner, context)
    agent.registry.unregister(action.name)
    agent.registry.register(replace(action, execute=advance_between_targets))
    plan = next(value for name, value in await run(agent, sid) if name == 'approval')
    now[0] = plan['expires_at'] - 1
    response = await agent.confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    assert response['ok'] and writes == ['a', 'b']


@pytest.mark.asyncio
async def test_execution_window_expiry_retains_checkpoint_and_requires_fresh_owner_resume(tmp_path):
    agent, sid, writes = runtime(tmp_path, visibility='public')
    now = [agent.deps.clock()]
    agent.deps = replace(agent.deps, clock=lambda: now[0])
    action = agent.registry.get('apply_selection')
    original = action.execute
    async def expire_after_first(payload, owner, context):
        persist = context.checkpoint
        def checkpoint(state):
            persist(state)
            if state['completed'] == ['a']:
                now[0] += agent.EXECUTION_TTL + 1
        context.checkpoint = checkpoint
        return await original(payload, owner, context)
    agent.registry.unregister(action.name)
    agent.registry.register(replace(action, execute=expire_after_first))
    plan = next(value for name, value in await run(agent, sid) if name == 'approval')
    paused = await agent.confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    assert not paused['ok'] and paused['pending']['resumable'] and writes == ['a']
    replay = await agent.confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    assert replay == paused and writes == ['a']
    response = await agent.resume('owner', sid, plan['approval_id'], plan['plan_digest'])
    assert response['ok'] and writes == ['a', 'b']


@pytest.mark.asyncio
async def test_expired_resume_keeps_owner_and_sealed_target_integrity_checks(tmp_path):
    agent, sid, writes = runtime(tmp_path, visibility='public', interrupt=True)
    now = [agent.deps.clock()]
    agent.deps = replace(agent.deps, clock=lambda: now[0])
    plan = next(value for name, value in await run(agent, sid) if name == 'approval')
    await agent.confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    now[0] += 1800
    with pytest.raises(PermissionError, match='another owner'):
        await agent.resume('someone-else', sid, plan['approval_id'], plan['plan_digest'])
    agent.sessions[sid].data['pending']['prepared']['targets'].append('outside')
    with pytest.raises(ValueError, match='integrity'):
        await agent.resume('owner', sid, plan['approval_id'], plan['plan_digest'])
    assert writes == ['a']
