"""Copy authored story fields into a fresh, GM-only graph; no live game input."""
from __future__ import annotations

from typing import Any

from src.adventures.compatibility import default_runtime_requirement
from src.adventures.graph_v2 import ADVENTURE_GRAPH_FORMAT_V2


def from_plan(plan: dict[str, Any], directory_id: str, language: str) -> dict[str, Any]:
    locale = 'zh-CN' if language == 'zh-CN' else 'en'
    zh = locale == 'zh-CN'
    identities = {scene['id']: f'scene_{index + 1}' for index, scene in enumerate(plan['scenes'])}
    titles = {scene['id']: scene['title'] for scene in plan['scenes']}
    nodes = []
    objectives = []
    for scene in plan['scenes']:
        node_id = identities[scene['id']]
        notes = [scene['description'], ('转场条件（GM 确认）：' if zh else 'Exit condition (GM confirms): ') + scene['exit']]
        notes.extend(('GM 提示：' if zh else 'GM hint: ') + hint for hint in scene['hints'])
        transitions = [{'to': identities[target]} for target in scene['next_ids']]
        node = {'id': node_id, 'type': 'scene', 'visibility': 'gm', 'name': scene['title'],
                'description': '\n\n'.join(note for note in notes if note),
                'transitions': transitions, 'on_complete': []}
        # Plan successors are alternatives requiring a GM decision, not an
        # instruction to activate every branch in parallel.
        if len(transitions) > 1:
            node['choice_mode'] = 'exclusive'
            for transition, target in zip(transitions, scene['next_ids']):
                transition.update(choice_id=f'choose_{identities[target]}', choice_label=titles[target])
        nodes.append(node)
        objectives.append({'id': f'objective_{node_id}', 'name': scene['objective'],
                           'node_ids': [node_id], 'visibility': 'gm'})
    graph = {'schema_version': 2, 'kind': 'adventure', 'id': directory_id,
             'source_ref': f'diceframe-user:user:{directory_id}', 'automation_level': 'guided',
             'format': ADVENTURE_GRAPH_FORMAT_V2, 'name': plan['theme'], 'summary': plan['party_goal'],
             'chapters': [], 'nodes': nodes, 'objectives': objectives, 'milestones': [],
             'start_node_ids': [identities[plan['start']]]}
    manifest = {'schema_version': 1, 'adventure_id': f'user:{directory_id}', 'version': '1.0.0',
                'format': ADVENTURE_GRAPH_FORMAT_V2, 'world_policy': 'agnostic',
                'required_runtime': default_runtime_requirement(), 'reference_policy': 'adventure-local',
                'default_locale': locale, 'supported_locales': [locale], 'custom': True}
    warnings = ['storyDraftGmReview']
    if plan['core_npcs']:
        warnings.append('storyDraftNpcReferencesOmitted')
    files = {'manifest.json': manifest, 'adventure.json': graph,
             f'locales/{locale}/adventure.json': {'locale_schema_version': 1, 'locale': locale,
                                                'target': {'kind': 'adventure', 'id': directory_id}, 'fields': {}}}
    return {'directory_id': directory_id, 'files': files,
            'references': [], 'provenance': {'format': 'run-story-plan'}, 'warnings': warnings}
