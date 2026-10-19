import asyncio
from types import SimpleNamespace

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.engine.game_state import GameState
from src.webui.run_write_admission import run_write_admission
from tests.test_run_story_service import setup


async def client_for(instance, handlers):
    app = web.Application(middlewares=[run_write_admission])
    app['api'] = SimpleNamespace(get_game_instance=lambda key: instance)
    for method, path, handler in handlers:
        app.router.add_route(method, path, handler)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


def ok(calls, name):
    async def handler(request):
        calls.append(name)
        return web.json_response({'ok': True})
    return handler


@pytest.mark.asyncio
async def test_ended_run_still_restores_identity_and_deletes_owner_data():
    _, inst, _, _ = setup()
    inst.state = GameState.ENDED
    calls = []
    client = await client_for(inst, [
        ('POST', '/api/games/{game_key}/claim-gm', ok(calls, 'claim-gm')),
        ('POST', '/api/games/{game_key}/seat-token/claim', ok(calls, 'seat-claim')),
        ('POST', '/api/games/{game_key}/players/{uid}/seat-token', ok(calls, 'seat-issue')),
        ('DELETE', '/api/games/{game_key}/memories/{entry_id}', ok(calls, 'memory-delete')),
        ('PUT', '/api/games/{game_key}/memories/{entry_id}', ok(calls, 'memory-edit')),
        ('POST', '/api/games/{game_key}/action', ok(calls, 'action')),
    ])
    try:
        for method, path in (('POST', 'claim-gm'), ('POST', 'seat-token/claim'), ('POST', 'players/alice/seat-token'), ('DELETE', 'memories/3')):
            response = await client.request(method, f'/api/games/key/{path}')
            assert response.status == 200, path
        for method, path in (('PUT', 'memories/3'), ('POST', 'action')):
            response = await client.request(method, f'/api/games/key/{path}')
            assert response.status == 409, path
            assert (await response.json())['error_code'] == 'RUN_ENDED'
        assert calls == ['claim-gm', 'seat-claim', 'seat-issue', 'memory-delete']
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_slow_self_gated_calls_do_not_hold_the_run_authority():
    _, inst, _, _ = setup()
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def slow_image(request):
        started.set()
        await release.wait()
        return web.json_response({'ok': True})

    client = await client_for(inst, [
        ('POST', '/api/games/{game_key}/generated-images/current-round', slow_image),
        ('POST', '/api/games/{game_key}/action', ok(calls, 'action')),
    ])
    try:
        image = asyncio.create_task(client.post('/api/games/key/generated-images/current-round'))
        await asyncio.wait_for(started.wait(), 2)
        # Another player's action is not queued behind the image request.
        response = await asyncio.wait_for(client.post('/api/games/key/action'), 2)
        assert response.status == 200 and calls == ['action']
        release.set()
        assert (await image).status == 200
    finally:
        release.set()
        await client.close()


@pytest.mark.asyncio
async def test_slow_calls_are_refused_once_the_run_is_frozen():
    _, inst, _, _ = setup()
    inst.state = GameState.ENDED
    calls = []
    client = await client_for(inst, [('POST', '/api/games/{game_key}/kp-question', ok(calls, 'kp'))])
    try:
        response = await client.post('/api/games/key/kp-question')
        assert response.status == 409 and calls == []
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_a_run_frozen_during_the_model_call_keeps_its_archive():
    from unittest.mock import AsyncMock
    from src.commands.story_recap import StoryRecapGenerator

    _, inst, _, _ = setup()
    inst.log = [{'round': 1, 'gm_response': 'The harbour bell rings.', 'player_actions': {}}]

    async def answer(**_):
        inst.state = GameState.ENDED  # the finale is committed while the model is answering
        return SimpleNamespace(narration='A recap', total_tokens=1)

    generator = StoryRecapGenerator(SimpleNamespace(call=AsyncMock(side_effect=answer)))
    before = inst.to_dict()
    result = await generator.generate(inst)
    assert not result['ok']
    assert inst.to_dict()['log'] == before['log']
