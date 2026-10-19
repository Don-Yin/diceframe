from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.webui.routes.run_story import register
from src.webui.run_write_admission import run_write_admission
from tests.test_run_story_service import setup, GM


async def client_for(service, instance):
    @web.middleware
    async def identity(request, handler):
        request['user_id'] = request.headers.get('X-Test-User', '')
        request['owner_authenticated'] = request.headers.get('X-Test-Owner') == 'yes'
        return await handler(request)
    app = web.Application(middlewares=[identity, run_write_admission])
    app['api'] = SimpleNamespace(get_game_instance=lambda key: instance, run_story=service)
    app['connection_pool'] = SimpleNamespace(broadcast=AsyncMock())
    register(app)
    async def ticket(request):
        return web.json_response({'ticket': 'read-only-test-ticket'})
    app.router.add_post('/api/games/{game_key}/sse-ticket', ticket)
    async def writer(request):
        instance.npcs['written'] = {}; return web.json_response({'ok': True})
    app.router.add_post('/api/games/{game_key}/{tail:.*}', writer)
    client = TestClient(TestServer(app)); await client.start_server()
    return client


@pytest.mark.asyncio
async def test_routes_reject_players_and_all_frozen_writers_but_allow_safe_archive_reads():
    service, inst, _, _ = setup()
    client = await client_for(service, inst)
    try:
        root = '/api/games/key/run-story'
        player = {'X-Test-User': 'alice'}; owner = {'X-Test-Owner': 'yes'}
        assert (await client.get(root)).status == 403
        assert (await client.get(root, headers=player)).status == 200
        assert (await client.post(root + '/prepare', json={'run_id': inst.run_id}, headers=player)).status == 403
        response = await client.post(root + '/prepare', json={'run_id': inst.run_id}, headers=owner)
        assert response.status == 200
        broadcast = client.server.app['connection_pool'].broadcast
        broadcast.assert_awaited_once_with('key', {'type': 'run_story_changed'})
        assert (await client.post('/api/games/key/sse-ticket', headers=player)).status == 200
        job = (await response.json())['finale']['id']
        for path in ('action', 'advance', 'rollback', 'gm', 'characters/alice', 'ruleset/intent', 'rest', 'swipe', 'settings/story-mode'):
            response = await client.post('/api/games/key/' + path, json={}, headers=owner)
            assert response.status == 409, path
        assert 'written' not in inst.npcs
        assert broadcast.await_count == 1
        response = await client.post(root + '/materials', json={'run_id': inst.run_id, 'job_id': job, 'job_revision': 0,
            'epilogue': 'Public ending', 'recap': 'Public recap', 'gm_notes': 'GM SECRET'}, headers=owner)
        assert response.status == 200
        assert (await client.post(root + '/commit', json={'run_id': inst.run_id, 'job_id': job, 'job_revision': 1, 'confirmed': True}, headers=owner)).status == 200
        assert broadcast.await_count == 3
        assert (await client.post('/api/games/key/sse-ticket', headers=player)).status == 200
        assert all(call.args[1] == {'type': 'run_story_changed'} for call in broadcast.await_args_list)
        archive = await (await client.get(root + '/export', headers=player)).json()
        assert 'GM SECRET' not in str(archive)
        char = await (await client.get(root + '/export?kind=character&uid=somebody-else', headers=player)).json()
        assert char['character_name'] == 'Alice'
    finally:
        await client.close()
