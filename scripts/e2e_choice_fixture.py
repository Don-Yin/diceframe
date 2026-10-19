from src.engine.modules import adventure_runtime_state
"""Native exclusive-choice games for real owner/player browser acceptance."""
import json
from copy import deepcopy

from src.adventures import AdventureResolver
from src.adventures.graph_v2 import validate_graph_v2
from src.adventures.progress import new_progress
from src.engine.game_instance import GameInstance


E2E_CHOICE_GAME_KEYS = tuple(
    ('web', f'e2e_choice_{device}', 'web_bot')
    for device in ('desktop', 'mobile')
)


def write_choice_fixtures(data_dir, seed, write_save):
    for game_key in E2E_CHOICE_GAME_KEYS:
        identity = game_key[1]
        graph = {'schema_version': 2, 'kind': 'adventure', 'id': identity, 'format': 'diceframe:adventure-graph-v2',
                 'source_ref': f'diceframe-e2e:{identity}', 'automation_level': 'guided',
                 'chapters': [], 'objectives': [], 'milestones': [], 'start_node_ids': ['gate'],
                 'nodes': [
                     {'id': 'gate', 'type': 'decision', 'name': 'Choose a route', 'choice_mode': 'exclusive', 'transitions': [
                         {'to': 'bridge', 'choice_id': 'bridge_route', 'choice_label': 'Cross bridge'},
                         {'to': 'tunnel', 'choice_id': 'tunnel_route', 'choice_label': 'Use tunnel'},
                         {'to': 'secret', 'choice_id': 'secret_route', 'choice_label': 'Secret ritual route'},
                     ]}, {'id': 'bridge', 'type': 'scene', 'name': 'Bridge', 'transitions': []},
                     {'id': 'tunnel', 'type': 'scene', 'name': 'Tunnel', 'transitions': []},
                     {'id': 'secret', 'type': 'scene', 'visibility': 'gm', 'name': 'Secret ritual', 'transitions': []},
                 ]}
        manifest = {'schema_version': 1, 'adventure_id': f'user:{identity}', 'version': '1.0.0',
                    'format': graph['format'], 'world_policy': 'portable', 'required_runtime': {'id': 'core:dnd2024', 'minimum_version': 1},
                    'default_locale': 'zh-CN', 'supported_locales': ['zh-CN']}
        package = data_dir / 'templates' / 'adventures' / identity
        for path, value in {'manifest.json': manifest, 'adventure.json': graph,
                            'locales/zh-CN/adventure.json': {'locale_schema_version': 1, 'locale': 'zh-CN', 'target': {'kind': 'adventure', 'id': identity}, 'fields': {}}}.items():
            target = package / path; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        instance = GameInstance.from_dict(deepcopy(seed.to_dict()))
        instance.game_key = game_key
        player = deepcopy(instance.players['e2e-gm']); player['character_name'] = 'Route player'
        instance.put_player('e2e-player', player)
        resolver = AdventureResolver.single_directory(package.parent, source_kind='user')
        instance.adventure_binding = resolver.resolve_with_source(f'user:{identity}', 'zh-CN').binding(instance.world_id)
        adventure_runtime_state.replace_progress(instance, new_progress(validate_graph_v2(graph)))
        write_save(data_dir, instance)
