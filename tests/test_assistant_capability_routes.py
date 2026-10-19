from types import SimpleNamespace

import pytest

from tests.test_assistant_agent_routes import client_for
from tests.test_assistant_autonomy import make_runtime
from tests.test_assistant_agent import Planner


@pytest.mark.asyncio
async def test_capability_authorization_and_cancel_require_owner():
    client = await client_for(False, SimpleNamespace())
    try:
        assert (await client.get('/api/assistant/agent/capabilities')).status == 401
        for path in ('authorization', 'cancel'):
            assert (await client.post('/api/assistant/agent/' + path, json={})).status == 401
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_real_runtime_authorization_routes_validate_restore_and_revoke(tmp_path):
    runtime = make_runtime(tmp_path, Planner(), [])
    api = SimpleNamespace(assistant_agent_capabilities=runtime.capabilities,
                          assistant_agent_authorize=runtime.authorize,
                          assistant_agent_cancel=runtime.cancel,
                          assistant_agent_session=runtime.snapshot)
    client = await client_for(True, api)
    try:
        response = await client.get('/api/assistant/agent/capabilities?domain=lorebook')
        assert response.status == 200
        assert (await response.json())['capabilities'][0]['name'] == 'edit'
        invalid = await client.post('/api/assistant/agent/authorization', json={
            'mode': 'task', 'scope': {'owner_authenticated': 'true'}})
        assert invalid.status == 400
        for invalid_fields in ({'scope': []}, {'scope': ''}, {'domains': ''}):
            invalid = await client.post('/api/assistant/agent/authorization', json={
                'mode': 'task', **invalid_fields})
            assert invalid.status == 400
        response = await client.post('/api/assistant/agent/authorization', json={
            'mode': 'task', 'scope': {'book_id': 'b'}, 'max_steps': 8})
        assert response.status == 200
        grant = await response.json()
        sid = grant['session_id']
        snapshot = await (await client.get('/api/assistant/agent/session/' + sid)).json()
        assert snapshot['authorization']['scope'] == {'book_id': 'b'}
        assert (await client.post('/api/assistant/agent/cancel', json={'session_id': sid})).status == 200
        snapshot = await (await client.get('/api/assistant/agent/session/' + sid)).json()
        assert snapshot['authorization'] is None
    finally:
        await client.close()
