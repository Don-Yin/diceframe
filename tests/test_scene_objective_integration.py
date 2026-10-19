"""Real composition, opening, round and historical rewrite for #539-A."""
from copy import deepcopy

import pytest

from src.engine.game_instance import GameState
from src.engine.modules import adventure_runtime_state
from src.webui.api import WebAPI
from tests.test_scene_objective_context import installed

pytest_plugins = ["tests.webapi_harness"]


def composed(web_api, tmp_path):
    old_api, lore, registry, model, worlds = web_api
    instance, _ = installed(tmp_path)
    for player in instance.players.values():
        player['character_sheet'] = {'hp': 10, 'max_hp': 10, 'attributes': {'str': 10}}
    # The production WebAPI must inject its exact resolver into the actual
    # handler; no test setter supplies the missing wiring.
    api = WebAPI(registry=registry, lorebook=lore, memory=None,
                 rules_dir=tmp_path / 'rules', handler=old_api._handler,
                 llm_client=model, worlds_dir=worlds, adventures_dir=tmp_path / 'adventures')
    registry.register(instance)
    return api, instance, model


@pytest.mark.asyncio
async def test_production_composition_connects_opening_round_and_player_context(web_api, tmp_path):
    api, instance, model = composed(web_api, tmp_path)
    await api._handler.start_game(instance)
    assert 'Meet the investigator' in model.calls[0]['user_message']
    instance.state = GameState.ACTIVE_JUDGMENT
    instance.action_queue = [{'user_id': 'alice', 'text': 'Wait for the investigator'}]
    start = len(model.calls)
    await api._handler.process_round(instance)
    assert any('Meet the investigator' in call['user_message'] for call in model.calls[start:])
    before = deepcopy(instance.to_dict())
    await api._handler.answer_kp_question(instance, 'alice', 'What is our current goal?')
    context = model.calls[-1]['user_message']
    assert 'Meet the investigator' in context
    assert 'FUTURE' not in context and 'SECRET' not in context
    assert instance.to_dict() == before


@pytest.mark.asyncio
async def test_swipe_uses_target_round_progress_instead_of_the_current_branch(web_api, tmp_path):
    api, instance, model = composed(web_api, tmp_path)
    await api._handler.start_game(instance)
    instance.state = GameState.ACTIVE_JUDGMENT
    instance.action_queue = [{'user_id': 'alice', 'text': 'Wait for the investigator'}]
    await api._handler.process_round(instance)
    entry = instance.log[-1]
    assert entry['pre_adventure_progress']['active_nodes'] == ['gate']
    later = deepcopy(adventure_runtime_state.progress(instance))
    later.update(active_nodes=['vault'], completed_nodes=['gate'], completed_objectives=['find_investigator'])
    adventure_runtime_state.replace_progress(instance, later)
    start = len(model.calls)
    assert await api._handler.generate_swipe(instance, entry['round'])
    contexts = [call['user_message'] for call in model.calls[start:]]
    assert any('Meet the investigator' in context for context in contexts)
    assert all('FUTURE_OBJECTIVE' not in context for context in contexts)
    assert adventure_runtime_state.progress(instance)['active_nodes'] == ['gate']


@pytest.mark.parametrize('missing', ['pre_adventure_progress', 'pre_state_snapshot'])
@pytest.mark.asyncio
async def test_v2_history_without_progress_snapshot_cannot_rewrite_using_future_state(web_api, tmp_path, missing):
    api, instance, model = composed(web_api, tmp_path)
    await api._handler.start_game(instance)
    instance.state = GameState.ACTIVE_JUDGMENT
    instance.action_queue = [{'user_id': 'alice', 'text': 'Wait'}]
    await api._handler.process_round(instance)
    instance.log[-1].pop(missing)
    before = deepcopy(instance.to_dict()); calls = len(model.calls)
    assert await api._handler.generate_swipe(instance, instance.log[-1]['round']) is None
    assert len(model.calls) == calls
    assert instance.to_dict() == before


def test_player_api_exposes_the_same_current_goal_projection(web_api, tmp_path):
    api, instance, _ = composed(web_api, tmp_path)
    view = api.game_adventure_projection('|'.join(instance.game_key), viewer_is_gm=False, viewer_uid='alice')
    scene = view['adventure']['scene_objectives']
    assert scene['objectives'] == [{'name': 'Meet the investigator', 'status': 'active'}]
    assert 'FUTURE' not in str(scene) and 'SECRET' not in str(scene)
