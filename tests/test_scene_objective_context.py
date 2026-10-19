"""#539-A: current Adventure facts reach models without future/GM disclosure."""
from copy import deepcopy
from pathlib import Path

import pytest


def test_v1_runtime_current_step_is_player_safe_and_read_only():
    from tests.rulesets.test_dnd2024_campaign import _instance, _agreement, _submit
    from src.adventures.scene_context import AdventureSceneContext
    runtime, instance = _instance(adventure=True)
    _agreement(runtime, instance)
    _submit(runtime, instance, 'tutorial.start', adventure_id='lanterns_of_greymoor')
    provider = AdventureSceneContext(lambda inst: runtime._adventure_loader.resolve_binding(inst.adventure_binding, inst.language),
                                    legacy_projection=runtime.scene_objective_context)
    before = deepcopy(instance.to_dict())
    view = provider(instance, viewer_is_gm=False)
    assert view['objectives'] and view['current_nodes']
    assert 'next_step_id' not in str(view) and 'encounter_preset_id' not in str(view)
    assert instance.to_dict() == before

from src.adventures.scene_context import AdventureSceneContext, project_scene_objectives
from src.adventures.graph_v2 import validate_graph_v2
from src.adventures.progress import new_progress
from src.commands.prompt_composer import PromptComposer
from src.commands.ai_player import _build_player_context
from src.engine.game_instance import GameInstance
from src.engine.modules import adventure_runtime_state
from src.llm.context_builder import build_context, build_player_safe_context
from tests.test_adventure_v2_runtime import _install, _instance, _graph


def graph():
    value = _graph()
    value['nodes'][0].update(name='Waiting room', description='Find the investigator at the station.')
    value['nodes'][1].update(name='Unvisited cellar', description='FUTURE_PUBLIC_CLUE')
    value['nodes'][2].update(name='SECRET_KILLER', visibility='gm')
    value['objectives'] = [
        {'id': 'find_investigator', 'name': 'Meet the investigator', 'node_ids': ['gate']},
        {'id': 'future_goal', 'name': 'FUTURE_OBJECTIVE', 'node_ids': ['vault']},
        {'id': 'hidden_goal', 'name': 'SECRET_GOAL', 'node_ids': ['aftermath'], 'visibility': 'gm'},
    ]
    return validate_graph_v2(value)


def installed(tmp_path):
    resolver = _install(tmp_path, graph())
    instance = _instance(resolver)
    adventure_runtime_state.replace_progress(instance, new_progress(graph()))
    instance.players = {'alice': {'user_id': 'alice', 'character_name': 'Alice', 'character_sheet': {}},
                        'bob': {'user_id': 'bob', 'character_name': 'Bob', 'character_sheet': {}}}
    return instance, AdventureSceneContext(lambda inst: resolver.resolve_binding(inst.adventure_binding, inst.language))


def test_player_projection_contains_only_current_public_facts_and_no_internal_ids():
    g = graph(); progress = new_progress(g); before = deepcopy((g, progress))
    view = project_scene_objectives(g, progress, viewer_is_gm=False)
    assert view['current_nodes'] == [{'name': 'Waiting room', 'description': 'Find the investigator at the station.'}]
    assert view['objectives'] == [{'name': 'Meet the investigator', 'status': 'active'}]
    for secret in ('FUTURE_PUBLIC_CLUE', 'FUTURE_OBJECTIVE', 'SECRET', 'find_investigator', 'gate', 'npc_refs', 'transitions'):
        assert secret not in str(view)
    assert (g, progress) == before


def test_gm_receives_current_goals_and_candidate_successors_without_the_whole_plot():
    g = graph(); progress = new_progress(g)
    view = project_scene_objectives(g, progress, viewer_is_gm=True)
    assert view['current_nodes'][0]['id'] == 'gate'
    assert view['objectives'][0]['id'] == 'find_investigator'
    assert view['possible_next_nodes'][0]['id'] == 'vault'
    assert 'SECRET_KILLER' not in str(view)


def test_hidden_current_node_and_gm_only_package_have_no_player_projection():
    g = graph(); progress = new_progress(g); progress['active_nodes'] = ['aftermath']
    assert project_scene_objectives(g, progress, viewer_is_gm=False) == {}
    assert project_scene_objectives(g, progress, viewer_is_gm=True)['current_nodes'][0]['name'] == 'SECRET_KILLER'
    g['visibility'] = 'gm'
    assert project_scene_objectives(g, new_progress(g), viewer_is_gm=False) == {}


def test_completed_public_goal_is_known_but_future_goal_is_not():
    g = graph(); progress = new_progress(g)
    progress.update(active_nodes=[], completed_nodes=['gate'], completed_objectives=['find_investigator'])
    view = project_scene_objectives(g, progress, viewer_is_gm=False)
    assert view['objectives'] == [{'name': 'Meet the investigator', 'status': 'completed'}]
    assert 'FUTURE' not in str(view)


def test_missing_progress_never_guesses_the_start_node():
    assert project_scene_objectives(graph(), {}, viewer_is_gm=False) == {}


def test_provider_uses_exact_bound_source_and_does_not_modify_saved_state(tmp_path):
    instance, source = installed(tmp_path); before = deepcopy(instance.to_dict())
    assert source(instance, viewer_is_gm=False)['current_nodes'][0]['name'] == 'Waiting room'
    assert instance.to_dict() == before
    instance.adventure_binding['content_digest'] = 'changed'
    assert source(instance, viewer_is_gm=False) == {}
    assert source(instance, viewer_is_gm=True)['status'] == 'unavailable'
    instance.adventure_binding = {}
    assert source(instance, viewer_is_gm=True) == {}


@pytest.mark.asyncio
async def test_composer_and_ai_player_share_public_goals_without_extra_lore(tmp_path):
    instance, source = installed(tmp_path)
    composer = PromptComposer(Path('prompts'), Path('templates/rules'))
    composer.set_scene_context_provider(source)
    gm = await composer.build_user_context(instance, 'GM', [], 'Wait')
    player = await composer.build_player_safe_context(instance, 'Player', [], 'Where next?', 'alice')
    party = await composer.build_player_safe_context(instance, 'Player', [], 'Where next?', 'alice', visibility='party')
    ai = await _build_player_context(instance, 'bob', 'Player', 'Act', prompt_composer=composer, provider_name='')
    for context in [gm, player, party, ai]:
        assert 'Meet the investigator' in context
    for context in [player, party, ai]:
        assert all(text not in context for text in ('SECRET', 'FUTURE', 'find_investigator'))
    assert 'Unvisited cellar' in gm


@pytest.mark.asyncio
async def test_scene_block_is_bounded_and_higher_priority_than_long_history(monkeypatch):
    monkeypatch.setenv('TRPG_MAX_CONTEXT_CHARS', '4000')
    instance = GameInstance(game_key=('web', 'bounded-scene', 'bot'), language='en')
    instance.players = {'alice': {'character_name': 'Alice', 'character_sheet': {}}}
    instance.log = [{'round': n, 'gm_response': 'old scene ' * 700, 'actions': []} for n in range(15)]
    view = {'current_nodes': [{'name': 'Station', 'description': 'D' * 40000}],
            'objectives': [{'name': 'Meet the investigator', 'status': 'active'}]}
    for builder, args in [(build_context, (instance, 'GM', [], 'Wait')),
                          (build_player_safe_context, (instance, 'Player', [], 'Wait', 'alice'))]:
        context = await builder(*args, scene_objective_view=view)
        assert len(context) <= 4000
        assert 'Meet the investigator' in context
        assert context.count('D') < 1000


def test_context_read_does_not_materialize_missing_progress_and_rejects_future_schema(tmp_path):
    instance, source = installed(tmp_path)
    instance.modules.pop('adventure_runtime')
    before = deepcopy(instance.modules)
    assert source(instance, viewer_is_gm=False) == {}
    assert instance.modules == before
    instance.modules['adventure_runtime'] = {'schema_version': 999, 'opaque': 'keep'}
    before = deepcopy(instance.modules)
    assert source(instance, viewer_is_gm=False) == {}
    assert source(instance, viewer_is_gm=True)['status'] == 'unavailable'
    assert instance.modules == before


def test_v1_keeps_its_ruleset_owned_campaign_path():
    from src.adventures import AdventureResolver
    resolver = AdventureResolver.from_directories(Path('templates/adventures'), None)
    resolution = resolver.resolve_with_source('core:lanterns_of_greymoor')
    instance = GameInstance(game_key=('web', 'v1', 'bot'), world_id='greymoor')
    assert instance.bind_adventure(resolution.binding('greymoor'))
    source = AdventureSceneContext(lambda inst: resolver.resolve_binding(inst.adventure_binding, inst.language))
    before = deepcopy(instance.to_dict())
    assert source(instance, viewer_is_gm=True) == {}
    assert source(instance, viewer_is_gm=False) == {}
    assert instance.to_dict() == before
