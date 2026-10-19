from src.engine.modules import adventure_runtime_state
from copy import deepcopy

import pytest

from src.adventures.graph_v2 import AdventureGraphV2Error, project_graph_v2, validate_graph_v2
from src.adventures.progress import ProgressError, complete_node, new_progress
from src.adventures.script_import import parse_script


def choice_graph():
    return {'id': 'paths', 'schema_version': 2, 'nodes': [
        {'id': 'gate', 'type': 'decision', 'choice_mode': 'exclusive', 'transitions': [
            {'to': 'bridge', 'choice_id': 'bridge_route', 'choice_label': 'Cross the bridge'},
            {'to': 'tunnel', 'choice_id': 'tunnel_route', 'choice_label': 'Secret tunnel', 'conditions': [{'type': 'world.fact_equals', 'key': 'key', 'value': True}]},
        ]}, {'id': 'bridge', 'type': 'scene', 'transitions': []},
        {'id': 'tunnel', 'type': 'scene', 'visibility': 'gm', 'transitions': []},
    ], 'chapters': [], 'objectives': [], 'milestones': [], 'start_node_ids': ['gate']}


def test_explicit_choice_opens_only_selected_branch_and_records_identity():
    graph = validate_graph_v2(choice_graph())
    progress = new_progress(graph)
    assert complete_node(progress, graph, 'gate', choice_id='bridge_route') == ['bridge']
    assert progress['selected_choices'] == {'gate': 'bridge_route'}
    assert progress['active_nodes'] == ['bridge']
    with pytest.raises(ProgressError):
        complete_node(progress, graph, 'gate', choice_id='tunnel_route')


@pytest.mark.parametrize('choice', ['', 'unknown', 'tunnel_route'])
def test_missing_unknown_or_closed_choice_leaves_progress_unchanged(choice):
    graph = validate_graph_v2(choice_graph())
    progress = new_progress(graph); before = deepcopy(progress)
    with pytest.raises(ProgressError):
        complete_node(progress, graph, 'gate', choice_id=choice)
    assert progress == before


def test_old_parallel_graph_stays_parallel_and_rejects_choice_payload():
    source = choice_graph(); source['schema_version'] = 1
    node = source['nodes'][0]; node.pop('choice_mode')
    for transition in node['transitions']:
        transition.pop('choice_id'); transition.pop('choice_label'); transition.pop('conditions', None)
    graph = validate_graph_v2(source)
    progress = new_progress(graph)
    with pytest.raises(ProgressError):
        complete_node(progress, graph, 'gate', choice_id='bridge_route')
    assert complete_node(progress, graph, 'gate') == ['bridge', 'tunnel']


def test_choice_projection_keeps_public_labels_and_hides_secret_options_and_conditions():
    graph = validate_graph_v2(choice_graph())
    projection = project_graph_v2(graph)
    assert projection['nodes'][0]['transitions'] == [{'to': 'bridge', 'choice_id': 'bridge_route', 'choice_label': 'Cross the bridge'}]
    assert 'Secret tunnel' not in str(projection) and 'world.fact_equals' not in str(projection)


@pytest.mark.parametrize('mutation', ['old_schema', 'duplicate', 'missing_label', 'unknown_schema'])
def test_choice_contract_rejects_ambiguous_or_unknown_versions(mutation):
    graph = choice_graph()
    if mutation == 'old_schema': graph['schema_version'] = 1
    if mutation == 'duplicate': graph['nodes'][0]['transitions'][1]['choice_id'] = 'bridge_route'
    if mutation == 'missing_label': graph['nodes'][0]['transitions'][0]['choice_label'] = ''
    if mutation == 'unknown_schema': graph['schema_version'] = 99
    with pytest.raises(AdventureGraphV2Error): validate_graph_v2(graph)


def test_new_text_choices_have_explicit_exclusive_semantics():
    draft = parse_script(b'### Gate {#gate}\n@choice Bridge -> bridge\n@choice Tunnel -> tunnel\n### Bridge {#bridge}\n### Tunnel {#tunnel}', 'paths.md', {'id': 'core:dnd2024', 'minimum_version': 1}, 'en')
    graph = validate_graph_v2(draft['files']['adventure.json'])
    assert graph['nodes'][0]['choice_mode'] == 'exclusive'
    assert len({transition['choice_id'] for transition in graph['nodes'][0]['transitions']}) == 2


def installed_choice(tmp_path):
    from tests.test_adventure_v2_runtime import _install, _deps, _instance, PACKAGE_ID
    from src.webui.services import adventure_runtime
    graph = choice_graph(); graph.update(id=PACKAGE_ID, format='diceframe:adventure-graph-v2')
    graph['nodes'][0]['on_complete'] = [{'type': 'world_op', 'op': {'op': 'set_fact', 'key': 'route.confirmed', 'value': True}}]
    resolver = _install(tmp_path, graph)
    instance = _instance(resolver); deps = _deps(resolver)
    instance.put_player('alice', {'character_name': 'Alice', 'character_sheet': {}})
    instance.put_player('bob', {'character_name': 'Bob', 'character_sheet': {}})
    adventure_runtime.initialize_adventure_run(deps, instance)
    return deps, instance


def test_choice_requests_are_advisory_private_and_restorable(tmp_path):
    from src.engine.game_instance import GameInstance
    from src.webui.services import adventure_runtime
    deps, instance = installed_choice(tmp_path)
    for _ in range(2):
        adventure_runtime.request_adventure_choice(deps, instance, 'gate', 'bridge_route', 'alice')
    assert len(adventure_runtime_state.progress(instance)['choice_requests']) == 1
    assert adventure_runtime_state.progress(instance)['active_nodes'] == ['gate']
    with pytest.raises(ValueError):
        adventure_runtime.request_adventure_choice(deps, instance, 'gate', 'tunnel_route', 'alice')
    with pytest.raises(ValueError):
        adventure_runtime.request_adventure_choice(deps, instance, 'gate', 'bridge_route', 'outsider')
    from src.engine.player_control import set_control
    set_control(instance, 'bob', 'ai')
    with pytest.raises(ValueError, match='PLAYER_AI_CONTROLLED'):
        adventure_runtime.request_adventure_choice(deps, instance, 'gate', 'bridge_route', 'bob')
    restored = GameInstance.from_dict(instance.to_dict())
    assert adventure_runtime_state.progress(restored) == adventure_runtime_state.progress(instance)
    adventure_runtime.complete_adventure_node(deps, restored, 'gate', choice_id='bridge_route')
    assert adventure_runtime_state.progress(restored)['choice_requests'] == []
    assert adventure_runtime_state.progress(restored)['active_nodes'] == ['bridge']
    # Opening the other gate later must never reconsider the unselected route.
    from src.engine.world_state import apply_world_ops
    apply_world_ops(restored, [{'op': 'set_fact', 'key': 'key', 'value': True}])
    adventure_runtime.advance_adventure_world(deps, restored)
    assert adventure_runtime_state.progress(restored)['active_nodes'] == ['bridge']


@pytest.mark.asyncio
async def test_authoritative_choice_commands_reject_spoofing_player_completion_and_restore_save_failure(tmp_path):
    import asyncio
    from src.webui.services import adventure_commands, adventure_runtime
    deps, instance = installed_choice(tmp_path)
    before = deepcopy(adventure_runtime_state.progress(instance))
    before_world = deepcopy(instance.world_state)
    async def save(_instance): raise RuntimeError('storage failure')
    async def binding(): return None
    commands = adventure_commands.AdventureCommandDependencies(
        save=save, admission=lambda: None, binding=binding,
        complete=lambda target, node, recipient, actor, choice_id='': adventure_runtime.complete_adventure_node(deps, target, node, choice_id=choice_id),
        request_choice=lambda target, node, choice, actor: adventure_runtime.request_adventure_choice(deps, target, node, choice, actor),
    )
    body = {'type': 'adventure.choice.request', 'node_id': 'gate', 'choice_id': 'bridge_route'}
    spoofed = await adventure_commands.execute(commands, instance, {**body, 'actor_uid': 'bob'}, 'alice', is_gm=False)
    assert not spoofed['ok'] and adventure_runtime_state.progress(instance) == before
    denied = await adventure_commands.execute(commands, instance, {**body, 'type': 'adventure.node.complete'}, 'alice', is_gm=False)
    assert denied['code'] == 'GM_ONLY'
    results = await asyncio.gather(*(adventure_commands.execute(commands, instance, body, 'alice', is_gm=False) for _ in range(2)))
    assert all(result['code'] == 'ADVENTURE_NODE_FAILED' for result in results)
    assert adventure_runtime_state.progress(instance) == before
    result = await adventure_commands.execute(commands, instance, {**body, 'type': 'adventure.node.complete'}, 'gm', is_gm=True)
    assert result['code'] == 'ADVENTURE_NODE_FAILED' and adventure_runtime_state.progress(instance) == before
    assert instance.world_state == before_world
