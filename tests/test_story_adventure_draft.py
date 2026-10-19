"""A plan is copied to reviewed content, never exported with live authority."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from src.engine.modules import run_story
from src.webui.services import adventure_script_import
from src.webui.services.run_story import RunStoryService
from src.adventures import AdventureResolver
from src.adventures.script_import import parse_script
from tests.test_adventure_management import _api
from tests.test_run_story import adopt
from tests.test_run_story_service import GM, PLAYER, setup


def service(tmp_path):
    original, instance, save, _ = setup()
    adopt(instance)
    instance.log.append({'gm_response': 'PRIVATE LOG', 'token': 'DO NOT EXPORT'})
    instance.npcs['guide']['private_runtime_value'] = 'PRIVATE NPC'
    api = _api(tmp_path)
    svc = RunStoryService(replace(original.deps, prepare_adventure_draft=lambda draft: adventure_script_import.review(api.dependencies, draft)))
    body = {'run_id': instance.run_id, 'revision': run_story.snapshot(instance)['revision'], 'directory_id': 'my_story'}
    return svc, instance, save, api, body


def _script_draft(api):
    return parse_script(
        b"# New story\n\n## Opening\nA quiet harbor.",
        "new_story.md",
        api.dependencies.default_runtime_requirement(),
        "en",
    )


@pytest.mark.asyncio
async def test_plan_copy_is_reviewed_gm_only_content_without_live_state(tmp_path):
    svc, instance, save, api, body = service(tmp_path)
    before = deepcopy(instance.to_dict())
    preview = await svc.prepare_adventure('key', GM, body)
    assert preview['ok'] and not preview['blockers']
    draft = preview['draft']
    assert draft['files']['manifest.json']['required_runtime']['id'] == 'core:adventure'
    graph = draft['files']['adventure.json']
    assert graph['start_node_ids'] == ['scene_1']
    assert all(node['visibility'] == 'gm' for node in graph['nodes'])
    assert 'The party agrees to leave' in str(graph)
    assert 'The guide points to the street' in str(graph)
    assert 'PRIVATE LOG' not in str(preview) and 'PRIVATE NPC' not in str(preview)
    assert 'DO NOT EXPORT' not in str(preview) and instance.run_id not in str(preview)
    assert instance.to_dict() == before
    save.assert_not_awaited()
    assert not (api._adventure_loader.adventures_dir / 'my_story').exists()
    with pytest.raises(ValueError, match='reviewed'):
        adventure_script_import.commit(api.dependencies, {**draft, 'plan_digest': preview['plan_digest']})
    published = adventure_script_import.commit(api.dependencies, {**draft, 'plan_digest': preview['plan_digest'], 'reviewed': True})
    assert published['adventure_id'] == 'user:my_story'
    assert not instance.adventure_binding


@pytest.mark.asyncio
async def test_copy_rejects_player_stale_plan_and_bound_adventure(tmp_path):
    svc, instance, save, _api_obj, body = service(tmp_path)
    with pytest.raises(PermissionError):
        await svc.prepare_adventure('key', PLAYER, body)
    for change in ({'run_id': 'old'}, {'revision': 0}, {'revision': True}):
        with pytest.raises(ValueError, match='stale'):
            await svc.prepare_adventure('key', GM, {**body, **change})
    instance.adventure_binding = {'adventure_id': 'existing'}
    with pytest.raises(ValueError, match='bound'):
        await svc.prepare_adventure('key', GM, body)
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_plan_branch_copy_keeps_exclusive_choice_and_fresh_progress(tmp_path):
    svc, instance, _, _, body = service(tmp_path)
    state = run_story.snapshot(instance)
    plan = state['plan']
    third = deepcopy(plan['scenes'][1]); third.update(id='House', title='Alternative')
    plan['scenes'].append(third)
    plan['scenes'][0]['next_ids'].append('House')
    instance.modules['run_story']['plan'] = plan
    instance.modules['run_story']['completed'] = ['station']
    result = await svc.prepare_adventure('key', GM, body)
    graph = result['draft']['files']['adventure.json']
    assert graph['nodes'][0]['choice_mode'] == 'exclusive'
    assert len({t['choice_id'] for t in graph['nodes'][0]['transitions']}) == 2
    assert graph['start_node_ids'] == ['scene_1']
    assert 'completed' not in graph


@pytest.mark.asyncio
async def test_http_plan_copy_requires_owner_and_does_not_broadcast_or_write(tmp_path):
    from tests.test_run_story_routes import client_for
    svc, instance, save, _, body = service(tmp_path)
    client = await client_for(svc, instance)
    try:
        path = '/api/games/key/run-story/adventure-draft'
        assert (await client.post(path, json=body)).status == 403
        assert (await client.post(path, json=body, headers={'X-Test-User': 'alice'})).status == 403
        response = await client.post(path, json=body, headers={'X-Test-Owner': 'yes'})
        assert response.status == 200
        assert 'The party agrees to leave' in str(await response.json())
        client.server.app['connection_pool'].broadcast.assert_not_awaited()
        save.assert_not_awaited()
    finally:
        await client.close()


def test_review_rejects_builtin_only_source_without_writing(tmp_path):
    _svc, _instance, _save, api, _body = service(tmp_path)
    builtin_only = AdventureResolver.from_directories(
        Path(__file__).parents[1] / "templates" / "adventures", None,
    )
    deps = replace(
        api.dependencies,
        adventure_loader=builtin_only,
        adventure_resolver=builtin_only,
    )

    with pytest.raises(ValueError, match="registered user Adventure source"):
        adventure_script_import.review(deps, _script_draft(api))

    assert not (Path(__file__).parents[1] / "templates" / "adventures" / "text_*").exists()


def test_review_and_commit_support_registered_user_source_before_directory_exists(tmp_path):
    _svc, _instance, _save, api, _body = service(tmp_path)
    builtin = Path(__file__).parents[1] / "templates" / "adventures"
    user_root = tmp_path / "not-yet-created" / "adventures"
    resolver = AdventureResolver.from_directories(builtin, user_root)
    deps = replace(
        api.dependencies,
        adventure_loader=resolver,
        adventure_resolver=resolver,
    )
    preview = adventure_script_import.prepare_text_adventure(
        deps, "# New story\n\n## Opening\nA quiet harbor.", "reviewed_story", "en",
    )

    assert preview["blockers"] == []
    assert not user_root.exists()
    published = adventure_script_import.commit(deps, {
        **preview["draft"], "reviewed": True, "plan_digest": preview["plan_digest"],
    })
    assert published["adventure_id"] == "user:reviewed_story"
    assert (user_root / "reviewed_story" / "manifest.json").is_file()
