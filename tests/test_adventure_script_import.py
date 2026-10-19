from src.engine.modules import adventure_runtime_state
from copy import deepcopy

import pytest
from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer

from src.adventures.graph_v2 import project_graph_v2, validate_graph_v2
from src.adventures.script_import import MAX_SCRIPT_BYTES, parse_script
from src.engine.game_instance import GameRegistry
from src.webui.routes.adventure_script_import import register
from src.webui.routes.auth import ACCESS_PASSWORD_CONFIGURED_KEY
from tests.test_module_install_hardening import _make_api


SCRIPT = '# 雾港\n## 第一章\n### 抵达 {#arrival}\n港口浓雾。\nGM: 凶手在仓库。\n@choice 调查 -> warehouse\n### 仓库 {#warehouse}\n调查仓库。\n'


def test_script_parser_is_deterministic_and_preserves_branches_and_secrets():
    parsed = parse_script(SCRIPT.encode(), 'story.md', {'id': 'core:dnd2024', 'minimum_version': 1}, 'zh-CN')
    assert parsed == parse_script(SCRIPT.encode(), 'story.md', {'id': 'core:dnd2024', 'minimum_version': 1}, 'zh-CN')
    graph = parsed['files']['adventure.json']
    assert graph['nodes'][0]['id'] == 'arrival'
    assert graph['schema_version'] == 2 and graph['nodes'][0]['choice_mode'] == 'exclusive'
    assert graph['nodes'][0]['transitions'][0]['to'] == 'warehouse'
    assert graph['nodes'][0]['transitions'][0]['choice_label'] == '调查'
    assert '凶手' not in graph['nodes'][0]['description']
    assert any('凶手' in node['description'] and node['visibility'] == 'gm' for node in graph['nodes'])
    graph['nodes'][0]['visibility'] = 'public'
    public = project_graph_v2(validate_graph_v2(graph))
    assert '凶手' not in str(public)


def test_plain_text_and_fenced_code_are_prose_and_never_execute():
    draft = parse_script(b'Hello\n```js\n@npc evil\n```', 'story.txt', {'id': 'core:dnd2024', 'minimum_version': 1}, 'en')
    assert len(draft['files']['adventure.json']['nodes']) == 1
    assert draft['references'] == []
    assert '@npc evil' in draft['files']['adventure.json']['nodes'][0]['description']


@pytest.mark.parametrize('payload,filename', [(b'abc', 'x.pdf'), (b'\xff', 'x.md'), (b'', 'x.txt')])
def test_unsupported_or_invalid_source_fails_closed(payload, filename):
    with pytest.raises(ValueError):
        parse_script(payload, filename, {'id': 'core:dnd2024', 'minimum_version': 1}, 'en')


def test_preview_review_commit_uses_native_validator_and_creates_only_after_review(tmp_path):
    api, _host, store = _make_api(tmp_path / 'data')
    try:
        preview = api.preview_adventure_script(SCRIPT.encode(), 'story.md', 'zh-CN')
        assert preview['ok'] and not preview['blockers']
        assert preview['commit_plan']['operations'][0]['action'] == 'create'
        assert not list((tmp_path / 'data/templates/adventures').iterdir())
        body = {**preview['draft'], 'reviewed': True, 'plan_digest': preview['plan_digest']}
        result = api.commit_adventure_script(body)
        assert result['ok']
        detail = api.adventure_detail(result['adventure_id'])['adventure']
        assert detail['format'] == 'diceframe:adventure-graph-v2'
        assert detail['files']['manifest.json']['import_source'] == preview['draft']['provenance']
        assert detail['files']['adventure.json']['nodes'][0]['description'].startswith('港口浓雾。')
        assert api.preview_adventure_script(SCRIPT.encode(), 'story.md', 'zh-CN')['blockers']
        with pytest.raises(ValueError, match='block'):
            api.commit_adventure_script(body)
    finally:
        store.close()


@pytest.mark.parametrize('filename', ['../outside.json', '/outside.json', 'C:/outside.json', r'C:\outside.json', '.hidden/data.json'])
def test_review_rejects_unsafe_file_paths_without_writing(tmp_path, filename):
    api, _host, store = _make_api(tmp_path / 'data')
    try:
        preview = api.preview_adventure_script(SCRIPT.encode(), 'story.md', 'zh-CN')
        draft = deepcopy(preview['draft'])
        draft['files'][filename] = {'danger': True}
        try:
            result = api.review_adventure_script(draft)
        except ValueError:
            pass
        else:
            assert result['blockers']
        assert not list((tmp_path / 'data/templates/adventures').iterdir())
        assert not (tmp_path / 'outside.json').exists()
    finally:
        store.close()


def _script_app(api, *, password=True, owner=True):
    @web.middleware
    async def auth(request, handler):
        request[ACCESS_PASSWORD_CONFIGURED_KEY] = password
        request['owner_authenticated'] = owner
        return await handler(request)

    app = web.Application(middlewares=[auth])
    app['api'] = api
    register(app)
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize('password,query,headers', [(True, '', {}), (False, '?user=guest', {}), (False, '', {'X-Bot-Token': 'bot'})])
async def test_script_routes_require_owner_before_reading_or_writing(tmp_path, password, query, headers):
    api, _host, store = _make_api(tmp_path / 'data')
    try:
        async with TestClient(TestServer(_script_app(api, password=password, owner=False))) as client:
            for route in ('preview', 'review', 'commit'):
                response = await client.post(f'/api/adventures/script/{route}{query}', json={}, headers=headers)
                assert response.status == 403
                assert (await response.json())['error_code'] == 'OWNER_REQUIRED'
        assert not list((tmp_path / 'data/templates/adventures').iterdir())
    finally:
        store.close()


@pytest.mark.asyncio
async def test_http_upload_review_publish_and_bounded_invalid_requests(tmp_path):
    api, _host, store = _make_api(tmp_path / 'data')
    try:
        async with TestClient(TestServer(_script_app(api))) as client:
            form = FormData()
            form.add_field('file', SCRIPT.encode(), filename='story.md')
            response = await client.post('/api/adventures/script/preview?language=zh-CN', data=form)
            assert response.status == 200
            preview = await response.json()
            response = await client.post('/api/adventures/script/review', json=preview['draft'])
            assert response.status == 200
            assert (await response.json())['plan_digest'] == preview['plan_digest']
            response = await client.post('/api/adventures/script/commit', json={**preview['draft'], 'reviewed': True, 'plan_digest': preview['plan_digest']})
            assert response.status == 201
            for route in ('review', 'commit'):
                response = await client.post(f'/api/adventures/script/{route}', data=b'{' + b' ' * MAX_SCRIPT_BYTES * 4)
                assert response.status == 400
                response = await client.post(f'/api/adventures/script/{route}', json=[])
                assert response.status == 400
            form = FormData()
            form.add_field('file', b'x' * (MAX_SCRIPT_BYTES + 1), filename='big.md')
            assert (await client.post('/api/adventures/script/preview', data=form)).status == 400
            form = FormData()
            form.add_field('file', b'a', filename='a.md')
            form.add_field('file', b'b', filename='b.md')
            assert (await client.post('/api/adventures/script/preview', data=form)).status == 400
    finally:
        store.close()


@pytest.mark.asyncio
async def test_imported_graph_can_create_progress_and_restore_its_exact_binding(tmp_path):
    from tests.test_adventure_resolver_sources import _make_api as make_playable_api, WORLD_ID

    data_dir = tmp_path / 'data'
    (data_dir / 'templates/adventures').mkdir(parents=True)
    api = make_playable_api(data_dir, runtime_dir=data_dir / 'templates/adventures')
    try:
        preview = api.preview_adventure_script(SCRIPT.encode(), 'story.md', 'zh-CN')
        result = api.commit_adventure_script({**preview['draft'], 'reviewed': True, 'plan_digest': preview['plan_digest']})
        preset = api.ruleset_builder_choices('dnd2024_srd', {'locale': 'zh-CN'}, 'zh-CN')['choices']['quick_presets'][0]
        character = api.ruleset_builder_finalize('dnd2024_srd', {**preset['draft'], 'name': '剧本验收者', 'locale': 'zh-CN'}, 'zh-CN')['character']
        created = await api.create_game(WORLD_ID, '雾港开局', rule_id='dnd2024_srd', play_mode='adventure',
                                        adventure_id=result['adventure_id'], adventure_source_kind='user', players=[character])
        assert created['ok'], created
        projection = api.game_adventure_projection(created['game_key'], viewer_is_gm=True)['adventure']
        assert projection['available']
        instance = api._reg.get(api._parse_key(created['game_key']))
        assert 'arrival' in adventure_runtime_state.progress(instance)['active_nodes']
        restored_registry = GameRegistry(data_dir / 'saves')
        restored = await restored_registry.load(api._parse_key(created['game_key']))
        assert restored.adventure_binding == instance.adventure_binding
        assert adventure_runtime_state.progress(restored) == adventure_runtime_state.progress(instance)
        assert restored.adventure_binding['source_kind'] == 'user'
    finally:
        api._lore.close()


def test_missing_registered_user_directory_is_initialized_for_publish(tmp_path):
    from tests.test_adventure_resolver_sources import _make_api as make_playable_api

    runtime_dir = tmp_path / 'missing-adventures'
    api = make_playable_api(tmp_path / 'data', runtime_dir=runtime_dir)
    try:
        preview = api.preview_adventure_script(SCRIPT.encode(), 'story.md', 'zh-CN')
        assert preview['ok'] and not preview['blockers']
        directory_id = preview['draft']['directory_id']
        result = api.commit_adventure_script({
            **preview['draft'], 'reviewed': True, 'plan_digest': preview['plan_digest'],
        })
        assert result['ok']
        assert (runtime_dir / directory_id).is_dir()
        assert (runtime_dir / directory_id / 'manifest.json').is_file()
    finally:
        api._lore.close()


def test_commit_rejects_unreviewed_stale_unsafe_or_unresolved_drafts(tmp_path):
    api, _host, store = _make_api(tmp_path / 'data')
    try:
        preview = api.preview_adventure_script(SCRIPT.encode(), 'story.md', 'zh-CN')
        body = {**preview['draft'], 'plan_digest': preview['plan_digest']}
        with pytest.raises(ValueError, match='review'):
            api.commit_adventure_script(body)
        changed = deepcopy(body)
        changed['reviewed'] = True
        changed['files']['adventure.json']['nodes'][0]['description'] = 'Changed'
        with pytest.raises(ValueError, match='preview'):
            api.commit_adventure_script(changed)
        unsafe = deepcopy(body)
        unsafe['files']['adventure.json']['nodes'][0]['script'] = 'execute()'
        assert api.review_adventure_script(unsafe)['blockers']
        unresolved = api.preview_adventure_script(b'# Quest\n### Start\n@npc guard', 'x.md', 'en')
        assert unresolved['commit_plan']['unresolved_references'][0]['kind'] == 'npc'
        with pytest.raises(ValueError, match='block'):
            api.commit_adventure_script({**unresolved['draft'], 'reviewed': True, 'plan_digest': unresolved['plan_digest']})
        assert not list((tmp_path / 'data/templates/adventures').iterdir())
    finally:
        store.close()
