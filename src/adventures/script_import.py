"""Side-effect-free Markdown/TXT adapter. Source prose never becomes mechanics."""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from typing import Any

from src.adventures.graph_v2 import ADVENTURE_GRAPH_FORMAT_V2, MAX_CHAPTERS, MAX_NODES
from src.content_modules.refs import parse_content_ref

MAX_SCRIPT_BYTES = 512 * 1024
_HEADING = re.compile(r'^(#{1,3})\s+(.+?)\s*$')
_EXPLICIT_ID = re.compile(r'\s*\{#([a-z0-9][a-z0-9_.-]*)\}\s*$')
_REF = re.compile(r'^@(npc|location|encounter)\s+([^\s]+)\s*$')
_CHOICE = re.compile(r'^@choice\s+(.+?)\s*->\s*([a-z0-9][a-z0-9_.-]*)\s*$')


def parse_script(payload: bytes, filename: str, runtime: dict, language: str) -> dict[str, Any]:
    """Produce an editable native v2 draft; no files, rules or saves are written."""
    extension = PurePosixPath(filename.replace('\\', '/')).suffix.lower()
    if extension not in {'.md', '.txt'}:
        raise ValueError('script import accepts only Markdown/TXT')
    if not payload or len(payload) > MAX_SCRIPT_BYTES:
        raise ValueError('script must contain 1–524288 bytes')
    try:
        source = payload.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('script must be UTF-8 text') from exc
    if not source.strip() or '\x00' in source:
        raise ValueError('script is empty or contains binary data')
    digest = hashlib.sha256(payload).hexdigest()
    stem = f'text_{digest[:16]}'
    locale = language if language in {'zh-CN', 'en', 'ja', 'de'} else 'en'
    graph: dict[str, Any] = {
        'schema_version': 1, 'kind': 'adventure', 'id': stem,
        'source_ref': f'user:{stem}', 'automation_level': 'reference',
        'format': ADVENTURE_GRAPH_FORMAT_V2, 'visibility': 'public',
        'chapters': [], 'nodes': [], 'objectives': [], 'milestones': [], 'start_node_ids': [],
    }
    title = PurePosixPath(filename.replace('\\', '/')).stem
    current: dict[str, Any] | None = None
    chapter_id = ''
    references: list[dict] = []
    warnings: list[str] = ['scriptDefaultGm', 'scriptMechanicsReference']
    ordinary_nodes: list[dict] = []
    declared_choices: set[str] = set()
    seen_ids: set[str] = set()
    fence: str | None = None

    def ensure_chapter(name: str = '') -> None:
        nonlocal chapter_id
        if len(graph['chapters']) >= MAX_CHAPTERS:
            raise ValueError('too many script chapters')
        chapter_id = f'ch_{len(graph["chapters"]) + 1}'
        graph['chapters'].append({'id': chapter_id, 'name': name or title, 'visibility': 'public'})

    def add_node(name: str, node_id: str = '', *, notes: bool = False) -> dict:
        if len(graph['nodes']) >= MAX_NODES:
            raise ValueError('too many script scenes')
        wanted = node_id or f'n_{len(graph["nodes"]) + 1}'
        if wanted in seen_ids:
            raise ValueError(f'duplicate script scene id: {wanted}')
        seen_ids.add(wanted)
        if not chapter_id:
            ensure_chapter()
        node = {'id': wanted, 'name': name, 'type': 'reference' if notes else 'scene',
                'chapter_id': chapter_id, 'description': '', 'visibility': 'gm',
                'optional': notes, 'transitions': []}
        graph['nodes'].append(node)
        if not notes:
            ordinary_nodes.append(node)
        return node

    def prose(line: str) -> None:
        nonlocal current
        if current is None:
            current = add_node(title)
        current['description'] += line + '\n'

    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(('```', '~~~')):
            marker = stripped[:3]
            if fence == marker:
                fence = None
            elif fence is None:
                fence = marker
            prose(line)
            continue
        if fence:
            prose(line)
            continue
        heading = _HEADING.fullmatch(stripped)
        if heading:
            level, name = len(heading[1]), heading[2]
            if level == 1 and not graph['nodes'] and not graph['chapters']:
                title = name
                continue
            if level == 2:
                ensure_chapter(name)
                current = None
                continue
            explicit = _EXPLICIT_ID.search(name)
            node_id = explicit[1] if explicit else ''
            if explicit:
                name = name[:explicit.start()].strip()
            current = add_node(name, node_id)
            continue
        if stripped.startswith('GM:'):
            if current is None:
                current = add_node(title)
            note = add_node(current['name'] + ' · GM', notes=True)
            note['description'] = stripped[3:].strip()
            continue
        ref = _REF.fullmatch(stripped)
        if ref:
            if current is None:
                current = add_node(title)
            kind = {'npc': 'npc', 'location': 'map_location', 'encounter': 'encounter_catalog'}[ref[1]]
            value = ref[2]
            if ':' not in value:
                value = f'{kind}:{value}'
            parsed = parse_content_ref(value, default_source=f'adventure:{stem}')
            if parsed.kind != kind:
                raise ValueError('script reference kind does not match its marker')
            references.append(parsed.to_portable_dict())
            # Pending refs stay out of runtime until review explicitly maps or
            # keeps them as prose; no imported HP/AC/effect is inferred.
            prose(line)
            continue
        choice = _CHOICE.fullmatch(stripped)
        if choice:
            if current is None:
                current = add_node(title)
            declared_choices.add(current['id'])
            graph['schema_version'] = 2
            current['choice_mode'] = 'exclusive'
            identity = 'choice_' + hashlib.sha256(f"{current['id']}:{len(current['transitions'])}:{choice[2]}".encode()).hexdigest()[:16]
            current['transitions'].append({'to': choice[2], 'choice_id': identity, 'choice_label': choice[1]})
            prose(choice[1])
            continue
        if stripped.startswith('@'):
            if 'scriptUnknownMarker' not in warnings:
                warnings.append('scriptUnknownMarker')
        if stripped or current is not None:
            prose(line)
    if not ordinary_nodes:
        add_node(title)
    for index, node in enumerate(ordinary_nodes[:-1]):
        if node['id'] not in declared_choices:
            node['transitions'] = [{'to': ordinary_nodes[index + 1]['id']}]
    for node in graph['nodes']:
        node['description'] = node['description'].strip()
    graph['start_node_ids'] = [ordinary_nodes[0]['id']]
    graph['name'] = title
    manifest = {
        'schema_version': 1, 'adventure_id': f'user:{stem}', 'version': '1.0.0',
        'format': ADVENTURE_GRAPH_FORMAT_V2, 'world_policy': 'portable',
        'recommended_world_id': '', 'required_runtime': dict(runtime),
        'default_locale': locale, 'supported_locales': [locale], 'custom': True,
    }
    files = {'manifest.json': manifest, 'adventure.json': graph,
             f'locales/{locale}/adventure.json': {'locale_schema_version': 1, 'locale': locale,
                                                 'target': {'kind': 'adventure', 'id': stem}, 'fields': {}}}
    return {'directory_id': stem, 'files': files,
            'references': references, 'warnings': warnings,
            'provenance': {'format': 'markdown' if extension == '.md' else 'text',
                           'filename': PurePosixPath(filename.replace('\\', '/')).name,
                           'source_digest': f'sha256:{digest}'}}
