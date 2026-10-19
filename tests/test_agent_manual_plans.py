import pytest

from src.webui.services.assistant_agent import AgentDependencies, AgentRuntime, AgentTool


@pytest.mark.asyncio
async def test_manual_recovery_plan_needs_no_model_and_still_requires_confirmation(tmp_path):
    calls = []
    tool = AgentTool('undo_content_operation', 'Undo content',
        {'type': 'object', 'properties': {'operation_id': {'type': 'string'}}, 'required': ['operation_id'], 'additionalProperties': False},
        lambda args, owner: calls.append((args, owner)) or {'ok': True}, mutation=True)
    runtime = AgentRuntime(AgentDependencies(lambda: None, lambda _: {'ok': False}, (tool,), tmp_path))
    planned = await runtime.plan('owner', 'undo_content_operation', {'operation_id': 'x'}, '')
    assert calls == []
    with pytest.raises(PermissionError):
        await runtime.confirm('other', planned['session_id'], planned['approval']['approval_id'], planned['approval']['plan_digest'], True)
    approval = planned['approval']
    await runtime.confirm('owner', planned['session_id'], approval['approval_id'], approval['plan_digest'], True)
    await runtime.confirm('owner', planned['session_id'], approval['approval_id'], approval['plan_digest'], True)
    assert calls == [({'operation_id': 'x'}, 'owner')]


@pytest.mark.asyncio
async def test_manual_plan_rejects_non_recovery_tools_and_parameter_tampering(tmp_path):
    runtime = AgentRuntime(AgentDependencies(lambda: None, lambda _: None, (), tmp_path))
    with pytest.raises(ValueError): await runtime.plan('owner', 'create_game', {}, '')


@pytest.mark.asyncio
async def test_recovery_required_result_survives_runtime_restart_without_replay(tmp_path):
    calls = []
    tool = AgentTool('undo_content_operation', 'Undo content',
        {'type': 'object', 'properties': {'operation_id': {'type': 'string'}}, 'required': ['operation_id'], 'additionalProperties': False},
        lambda args, owner: calls.append((args, owner)) or {'ok': False, 'recovery_required': True}, mutation=True)
    first = AgentRuntime(AgentDependencies(lambda: None, lambda _: {'ok': False}, (tool,), tmp_path))
    planned = await first.plan('owner', 'undo_content_operation', {'operation_id': 'x'}, '')
    approval = planned['approval']
    result = await first.confirm('owner', planned['session_id'], approval['approval_id'], approval['plan_digest'], True)
    assert result['recovery_required'] is True and len(calls) == 1
    restarted = AgentRuntime(AgentDependencies(lambda: None, lambda _: {'ok': False}, (tool,), tmp_path))
    with pytest.raises(ValueError, match='uncertain|不确定'):
        await restarted.confirm('owner', planned['session_id'], approval['approval_id'], approval['plan_digest'], True)
    assert len(calls) == 1
