"""Rule-neutral Adventures reuse graph authority without weakening ruleset admission."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.adventures import AdventureBundleError
from src.rulesets.dnd2024 import Dnd2024Runtime
from src.rulesets.legacy_adapter import LegacyRulesetAdapter
from src.webui.services import adventures
from tests.test_adventure_management import _api
from tests.test_adventure_v2_runtime import PACKAGE_ID, _graph, _install


def neutral_package(tmp_path: Path, graph=None, *, version=1):
    resolver = _install(tmp_path, graph or _graph())
    path = tmp_path / 'adventures' / PACKAGE_ID / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    manifest['required_runtime'] = {'id': 'core:adventure', 'minimum_version': version}
    path.write_text(json.dumps(manifest), encoding='utf-8')
    return resolver


@pytest.mark.parametrize('runtime', [LegacyRulesetAdapter(), Dnd2024Runtime()])
def test_same_narrative_package_is_compatible_with_legacy_and_professional_rules(tmp_path, runtime):
    resolver = neutral_package(tmp_path)
    bundle = resolver.resolve('user:v2_quest')
    assert adventures._compatibility(bundle, runtime, 'greymoor') == ('compatible', [])


def test_default_authoring_produces_neutral_graph_v2(tmp_path):
    api = _api(tmp_path)
    adventures.create_adventure(api.dependencies, {'directory_id': 'portable_story', 'name': 'A story'})
    bundle = api._adventure_loader.resolve('user:portable_story')
    assert bundle.manifest.required_runtime_id == 'core:adventure'
    assert bundle.manifest.format == 'diceframe:adventure-graph-v2'
    assert bundle.adventure['start_node_ids'] == ['opening']
    assert bundle.adventure['nodes'][0]['scene_ref'] == 'scene:portable_story_opening'


def test_specific_packages_keep_their_mechanics_and_world_constraints(tmp_path):
    resolver = _install(tmp_path, _graph())
    bundle = resolver.resolve('user:v2_quest')
    assert adventures._compatibility(bundle, LegacyRulesetAdapter(), 'greymoor')[0] == 'incompatible'
    assert adventures._compatibility(bundle, Dnd2024Runtime(), 'greymoor') == ('compatible', [])
    neutral = neutral_package(tmp_path / 'neutral').resolve('user:v2_quest')
    fixed = deepcopy(neutral.manifest)
    from dataclasses import replace
    neutral = replace(neutral, manifest=replace(fixed, world_policy='fixed'))
    assert 'world_mismatch' in adventures._compatibility(neutral, LegacyRulesetAdapter(), 'other')[1]


@pytest.mark.parametrize('mechanic', ['rules_gate', 'item_reward', 'encounter'])
def test_neutral_profile_rejects_mechanics_it_cannot_execute(tmp_path, mechanic):
    graph = _graph()
    if mechanic == 'rules_gate':
        graph['nodes'][0]['transitions'][0]['conditions'] = [
            {'type': 'rules.outcome', 'id': 'check', 'value': True}]
    elif mechanic == 'item_reward':
        graph['nodes'][0]['on_complete'] = [{'type': 'item_reward', 'ref': 'item:missing'}]
    else:
        graph['nodes'][0]['type'] = 'encounter'
    resolver = neutral_package(tmp_path, graph)
    with pytest.raises(AdventureBundleError, match='neutral|narrative|core:adventure'):
        resolver.load(PACKAGE_ID)


def test_future_neutral_profile_is_rejected_instead_of_downgraded(tmp_path):
    resolver = neutral_package(tmp_path, version=2)
    with pytest.raises(AdventureBundleError, match='version|core:adventure'):
        resolver.load(PACKAGE_ID)


def test_market_module_accepts_neutral_adventures_without_registering_a_fake_ruleset(tmp_path):
    from scripts.validate_content_module import validate_module
    package = tmp_path / 'story-module'
    neutral_package(package)
    manifest = {'schema_version': 1, 'id': 'story-module', 'name': 'Story module', 'version': '1.0.0',
                'plugin_type': 'content-pack', 'content_profile': 'adventure-module',
                'content_delivery_mode': 'catalog', 'contributes': {},
                'adventure_packages': [f'adventures/{PACKAGE_ID}']}
    path = package / 'plugin.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    (package / 'config.schema.json').write_text('{"type":"object","properties":{}}', encoding='utf-8')
    report = validate_module(package)
    assert report['ok'], report
    manifest['requires'] = [{'id': 'core:adventure', 'minimum_version': 1}]
    path.write_text(json.dumps(manifest), encoding='utf-8')
    assert not validate_module(package)['ok']


def test_neutral_import_keeps_inert_source_material_but_not_hidden_mechanics(tmp_path):
    resolver = neutral_package(tmp_path)
    path = tmp_path / 'adventures' / PACKAGE_ID / 'content' / 'items' / 'key.json'
    path.parent.mkdir(parents=True)
    item = {'schema_version': 1, 'kind': 'item', 'id': 'key', 'source_ref': 'test:key',
            'automation_level': 'reference', 'visibility': 'gm', 'name': 'Key',
            'description': 'Brass key', 'source_record': '{"damage":"1d6"}'}
    path.write_text(json.dumps(item), encoding='utf-8')
    assert resolver.load(PACKAGE_ID).entities['item']['key']['description'] == 'Brass key'
    item['damage'] = '1d6'
    path.write_text(json.dumps(item), encoding='utf-8')
    with pytest.raises(AdventureBundleError, match='core:adventure'):
        resolver.load(PACKAGE_ID)


def test_dnd_runtime_loads_the_same_neutral_binding_and_rejects_digest_changes(tmp_path):
    from tests.test_adventure_v2_runtime import _instance
    resolver = neutral_package(tmp_path)
    instance = _instance(resolver)
    runtime = Dnd2024Runtime()
    runtime.set_adventure_resolver(resolver)
    assert runtime.load_adventure(instance).manifest.required_runtime_id == 'core:adventure'
    instance.adventure_binding['content_digest'] = 'sha256:changed'
    with pytest.raises(ValueError, match='changed'):
        runtime.load_adventure(instance)


def gameplay(tmp_path, *, save=None):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from src.engine.game_state import GameState
    from src.rulesets.builtin import build_default_ruleset_registry, default_adventure_runtime_requirement
    from src.webui.services import adventure_runtime, ruleset_gameplay
    from tests.test_adventure_v2_runtime import _instance, _deps
    from tests.test_adventure_choices import choice_graph
    graph = choice_graph()
    graph['id'] = PACKAGE_ID
    graph['format'] = 'diceframe:adventure-graph-v2'
    resolver = neutral_package(tmp_path, graph)
    instance = _instance(resolver)
    instance.rule_id = 'coc'
    instance.state = GameState.ACTIVE_ACTION
    instance.put_player('alice', {'character_name': 'Alice', 'character_sheet': {}})
    runtime_deps = _deps(resolver)
    adventure_runtime.initialize_adventure_run(runtime_deps, instance)
    rulesets = build_default_ruleset_registry()
    catalogue = adventures.AdventureDependencies(
        resolver, lambda: [instance], lambda *_: None, rulesets, default_adventure_runtime_requirement)
    def binding(identity, runtime, world, language, source_kind='', source_id=''):
        return adventures.resolve_binding_for_runtime(catalogue, identity, runtime, world, language,
                                                      source_kind=source_kind, source_id=source_id)
    dependencies = ruleset_gameplay.RulesetGameplayDependencies(
        get_instance=lambda key: instance if tuple(key) == instance.game_key else None,
        parse_game_key=lambda key: tuple(key.split('|')),
        load_rule_for_game=lambda _: SimpleNamespace(rule_id='coc', template={}),
        ruleset_registry=rulesets, resolve_adventure_binding=binding,
        save_instance=save or AsyncMock(), apply_memory_delta=None,
        complete_adventure_node=lambda target, node, recipient, actor, choice_id='':
            adventure_runtime.complete_adventure_node(runtime_deps, target, node, choice_id=choice_id),
        request_adventure_choice=lambda target, node, choice, actor:
            adventure_runtime.request_adventure_choice(runtime_deps, target, node, choice, actor))
    return dependencies, instance


@pytest.mark.asyncio
async def test_legacy_adventure_commands_retain_gm_seat_binding_and_phase_authority(tmp_path):
    from src.engine.modules import adventure_runtime_state
    from src.webui.services.ruleset_gameplay import submit_intent
    deps, instance = gameplay(tmp_path)
    key = '|'.join(instance.game_key)
    choice = {'type': 'adventure.choice.request', 'node_id': 'gate', 'choice_id': 'bridge_route'}
    assert not (await submit_intent(deps, key, 'outsider', False, choice))['ok']
    assert (await submit_intent(deps, key, 'alice', False, choice))['ok']
    complete = {**choice, 'type': 'adventure.node.complete'}
    assert (await submit_intent(deps, key, 'alice', False, complete))['code'] == 'GM_ONLY'
    assert (await submit_intent(deps, key, 'gm', True, complete))['ok']
    assert adventure_runtime_state.progress(instance)['active_nodes'] == ['bridge']
    assert (await submit_intent(deps, key, 'alice', False, {'type': 'combat.start'}))['code'] == 'RULESET_INTENTS_UNAVAILABLE'
    instance.adventure_binding['content_digest'] = 'sha256:wrong'
    assert (await submit_intent(deps, key, 'gm', True, complete))['code'] == 'INCOMPATIBLE_ADVENTURE'


@pytest.mark.asyncio
async def test_legacy_adventure_command_save_failure_restores_authority(tmp_path):
    from unittest.mock import AsyncMock
    from src.engine.modules import adventure_runtime_state
    from src.webui.services.ruleset_gameplay import submit_intent
    deps, instance = gameplay(tmp_path, save=AsyncMock(side_effect=RuntimeError('disk full')))
    before = deepcopy(adventure_runtime_state.progress(instance))
    result = await submit_intent(deps, '|'.join(instance.game_key), 'gm', True,
                                {'type': 'adventure.node.complete', 'node_id': 'gate', 'choice_id': 'bridge_route'})
    assert result['code'] == 'ADVENTURE_NODE_FAILED'
    assert adventure_runtime_state.progress(instance) == before


@pytest.mark.asyncio
async def test_cancelled_save_restores_adventure_command_before_propagating(tmp_path):
    import asyncio
    from unittest.mock import AsyncMock
    from src.engine.modules import adventure_runtime_state
    from src.webui.services.ruleset_gameplay import submit_intent
    deps, instance = gameplay(tmp_path, save=AsyncMock(side_effect=asyncio.CancelledError()))
    before = deepcopy(adventure_runtime_state.progress(instance))
    with pytest.raises(asyncio.CancelledError):
        await submit_intent(deps, '|'.join(instance.game_key), 'gm', True,
                            {'type': 'adventure.node.complete', 'node_id': 'gate', 'choice_id': 'bridge_route'})
    assert adventure_runtime_state.progress(instance) == before
