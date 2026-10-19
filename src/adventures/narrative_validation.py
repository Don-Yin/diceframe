"""Closed narrative profile; mechanical content requires its specific runtime."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.adventures.compatibility import narrative_requirement_supported
from src.adventures.graph_v2 import ADVENTURE_GRAPH_FORMAT_V2, validate_graph_v2


def validate_narrative_profile(manifest: Any, entities: Mapping[str, Mapping[str, dict[str, Any]]]) -> None:
    if not narrative_requirement_supported(manifest.required_runtime_id, manifest.required_runtime_version):
        raise ValueError('unsupported core:adventure profile version')
    if manifest.format != ADVENTURE_GRAPH_FORMAT_V2:
        raise ValueError('core:adventure narrative profile requires graph v2')
    reference_fields = {'schema_version', 'kind', 'id', 'source_ref', 'automation_level',
                        'visibility', 'name', 'description', 'source_record'}
    for kind in ('encounter', 'encounter_catalog', 'item', 'reward'):
        for record in entities.get(kind, {}).values():
            # Foreign stat sheets may be retained as inert GM source evidence.
            # A label alone cannot hide executable mechanics in extra fields.
            if record.get('automation_level') != 'reference' or set(record) - reference_fields:
                raise ValueError(f'core:adventure narrative profile does not execute {kind} mechanics; select a specific ruleset runtime')
    for adventure in entities.get('adventure', {}).values():
        graph = validate_graph_v2(adventure)
        for node in graph['nodes']:
            if node['type'] == 'encounter' or node.get('encounter_ref'):
                raise ValueError('core:adventure narrative profile does not execute encounters')
            if any(outcome['type'] == 'item_reward' for outcome in node['on_complete']):
                raise ValueError('core:adventure narrative profile does not execute item_reward')
            if any(gate['type'].startswith('rules.') for transition in node['transitions'] for gate in transition['conditions']):
                raise ValueError('core:adventure narrative profile does not evaluate rules gates')
