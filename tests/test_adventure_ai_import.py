import asyncio
import json
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.webui.services.adventure_ai_import import AdventureAiImportDependencies, organize
from src.webui.routes.adventure_script_import import register
from src.webui.routes.auth import ACCESS_PASSWORD_CONFIGURED_KEY
from tests.test_module_install_hardening import _make_api


def model_reply(prompt):
    data = json.loads(prompt)
    if 'source_units' in data:
        ids = [unit['id'] for unit in data['source_units']]
        return {'scenes': [
            {'name': 'Gate', 'chapter': 'Arrival', 'description': 'A locked gate.', 'source_ids': ids, 'npc_names': ['Keeper']},
            {'name': 'Inside', 'chapter': 'Arrival', 'description': 'The keeper lets the party in.', 'source_ids': ids, 'npc_names': []},
        ], 'resources': [{'kind': 'npc', 'name': 'Keeper', 'description': 'Knows the secret password.', 'source_ids': ids}]}
    ids = [scene['id'] for scene in data['scenes']]
    return {'start_ids': ids[:1], 'links': [{'from': ids[0], 'to': ids[1], 'label': ''}]}


@pytest.mark.asyncio
async def test_ai_organizes_only_a_reviewed_draft_with_real_progress_and_preserves_source(tmp_path):
    api, _, store = _make_api(tmp_path / 'data')
    try:
        draft = api.preview_adventure_script(b'# Gate\n### Arrival\nA gate.\nGM: Secret password.\n### Inside\nA hall.', 'gate.md', 'en')['draft']
        original = json.dumps(draft, sort_keys=True)
        calls, progress = [], []

        async def generate(prompt, system_hint, language):
            calls.append((prompt, system_hint, language))
            return {'ok': True, 'text': json.dumps(model_reply(prompt))}

        async def emit(value):
            progress.append(value)

        result = await organize(AdventureAiImportDependencies(generate, api.review_adventure_script), draft, 'Keep the mystery', 'en', emit)
        assert result['ok'] and not result['blockers'], result
        graph = result['draft']['files']['adventure.json']
        assert len([n for n in graph['nodes'] if n['type'] == 'scene']) == 2
        assert len([n for n in graph['nodes'] if n['type'] == 'reference']) == 3
        assert all(n['visibility'] == 'gm' for n in graph['nodes'])
        assert graph['nodes'][0]['npc_refs']
        assert graph['nodes'][0]['transitions'][0]['to'] == graph['nodes'][1]['id']
        assert result['draft']['files']['manifest.json']['required_runtime'] == draft['files']['manifest.json']['required_runtime']
        assert json.dumps(draft, sort_keys=True) == original
        assert 'Secret password.' in str(result['draft'])
        assert len(calls) == 2
        assert progress[-1]['completed'] == progress[-1]['total']
        assert {p['stage'] for p in progress} >= {'organizing', 'linking', 'validating'}
        assert not list((tmp_path / 'data/templates/adventures').iterdir())
    finally:
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['mechanics', 'source', 'links'])
async def test_ai_rejects_invented_mechanics_sources_and_links(tmp_path, invalid):
    api, _, store = _make_api(tmp_path / 'data')
    try:
        draft = api.preview_adventure_script(b'# Gate\n### Arrival\nA gate.', 'gate.md', 'en')['draft']

        async def generate(prompt, system_hint, language):
            result = model_reply(prompt)
            if 'source_units' in json.loads(prompt):
                if invalid == 'mechanics':
                    result['resources'][0]['hp'] = 999
                if invalid == 'source':
                    result['scenes'][0]['source_ids'] = ['invented']
            elif invalid == 'links':
                result['links'][0]['to'] = 'invented'
            return {'ok': True, 'text': json.dumps(result)}

        with pytest.raises(ValueError):
            await organize(AdventureAiImportDependencies(generate, api.review_adventure_script), draft, '', 'en', _ignore)
    finally:
        store.close()


async def _ignore(value):
    pass


@pytest.mark.asyncio
async def test_ai_cancellation_stops_the_active_model_call_without_a_result(tmp_path):
    api, _, store = _make_api(tmp_path / 'data')
    started, cancelled = asyncio.Event(), asyncio.Event()
    try:
        draft = api.preview_adventure_script(b'# Gate\n### Arrival\nA gate.', 'gate.md', 'en')['draft']

        async def generate(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        task = asyncio.create_task(organize(AdventureAiImportDependencies(generate, api.review_adventure_script), draft, '', 'en', _ignore))
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
        assert not list((tmp_path / 'data/templates/adventures').iterdir())
    finally:
        store.close()


@pytest.mark.asyncio
async def test_ai_processes_every_chunk_and_fails_closed_if_the_model_is_unconfigured(tmp_path):
    api, _, store = _make_api(tmp_path / 'data')
    try:
        draft = api.preview_adventure_script(('# Gate\n### Arrival\n' + 'A' * 7000).encode(), 'gate.md', 'en')['draft']
        progress, calls = [], []

        async def generate(prompt, hint, language):
            calls.append(json.loads(prompt))
            return {'ok': True, 'text': json.dumps(model_reply(prompt))}

        async def emit(value):
            progress.append(value)

        result = await organize(AdventureAiImportDependencies(generate, api.review_adventure_script), draft, '', 'en', emit)
        assert len(calls) == 3
        assert ''.join(unit['text'] for call in calls if 'source_units' in call for unit in call['source_units']) == 'A' * 7000
        assert progress[-1]['completed'] == 4
        assert result['draft']['provenance']['ai_organization']['chunks'] == 2

        async def unavailable(*args):
            return {'ok': False, 'error': 'Main model is not configured'}

        with pytest.raises(ValueError, match='not configured'):
            await organize(AdventureAiImportDependencies(unavailable, api.review_adventure_script), draft, '', 'en', _ignore)
        assert not list((tmp_path / 'data/templates/adventures').iterdir())
    finally:
        store.close()


@pytest.mark.asyncio
async def test_ai_route_requires_owner_and_token_consent_before_calling_model():
    calls = []

    async def generate(*args):
        calls.append(args)
        return {'ok': True}

    configured = [True]

    @web.middleware
    async def authentication(request, handler):
        request[ACCESS_PASSWORD_CONFIGURED_KEY] = configured[0]
        return await handler(request)

    app = web.Application(middlewares=[authentication])
    app['api'] = SimpleNamespace(organize_adventure_script=generate)
    register(app)
    async with TestClient(TestServer(app)) as client:
        response = await client.post('/api/adventures/script/ai', json={'draft': {}, 'token_consent': True})
        assert response.status == 403
        configured[0] = False
        response = await client.post('/api/adventures/script/ai', json={'draft': {}})
        assert response.status == 400
        response = await client.post('/api/adventures/script/ai?share=1', json={'draft': {}, 'token_consent': True})
        assert response.status == 403
        assert calls == []


@pytest.mark.asyncio
async def test_ai_route_disconnect_cancels_inflight_generation():
    cancelled = asyncio.Event()

    async def generate(draft, instructions, language, emit):
        await emit({'stage': 'organizing', 'completed': 0, 'total': 3, 'current': 1, 'chunks': 1})
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    app = web.Application()
    app['api'] = SimpleNamespace(organize_adventure_script=generate)
    register(app)
    async with TestClient(TestServer(app)) as client:
        response = await client.post('/api/adventures/script/ai', json={'draft': {}, 'token_consent': True})
        assert response.status == 200
        assert json.loads(await response.content.readline())['type'] == 'progress'
        response.close()
        await asyncio.wait_for(cancelled.wait(), 3)
