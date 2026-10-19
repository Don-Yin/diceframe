"""Optional, GM-adopted free-game plan. Quest notes never own scene progress.

All public information is projected from the current/revealed scene; an authored
public flag alone does not reveal future scenes. Transitions require a GM's
confirmation and references to committed rounds, not an LLM assertion.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from src.engine import module_hooks
from src.engine.module_state import ModuleStateError, ModuleStateSpec, get_module_state, register_module_state

MODULE_NAME = 'run_story'
SCHEMA_VERSION = 1


def fresh() -> dict[str, Any]:
    return {'schema_version': 1, 'revision': 0, 'plan': None, 'current_id': '',
            'revealed': [], 'completed': [], 'events': [], 'warnings': [], 'stalled_rounds': 0}


def ensure(raw: Any) -> dict[str, Any]:
    return raw if isinstance(raw, dict) else fresh()


def require_writable(instance: Any) -> None:
    raw = instance.modules.get(MODULE_NAME)
    if raw is not None and (not isinstance(raw, dict) or type(raw.get('schema_version')) is not int or raw['schema_version'] != 1):
        raise ModuleStateError('unsupported run_story schema')


def snapshot(instance: Any) -> dict[str, Any]:
    require_writable(instance)
    return deepcopy(instance.modules.get(MODULE_NAME) or fresh())


def _text(raw: Any, field: str, limit: int = 800, *, empty: bool = False) -> str:
    value = raw.get(field, '')
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError(f'invalid story {field}')
    return value.strip()


def validate_plan(raw: Any, npc_ids: set[str]) -> dict[str, Any]:
    if not isinstance(raw, dict) or type(raw.get('format_version')) is not int or raw.get('format_version') != 1:
        raise ValueError('unsupported story plan format')
    if raw.get('mode') not in {'guided', 'sandbox'} or raw.get('npc_policy') not in {'strict', 'open'}:
        raise ValueError('invalid story policy')
    core = raw.get('core_npcs', [])
    if not isinstance(core, list) or len(core) > 20 or any(not isinstance(i, str) or i not in npc_ids for i in core):
        raise ValueError('core_npcs must reference existing NPC identities; create/adopt NPCs explicitly first')
    scenes = raw.get('scenes')
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 24:
        raise ValueError('a plan requires 1–24 scenes')
    ids: set[str] = set()
    normalized = []
    for scene in scenes:
        if not isinstance(scene, dict):
            raise ValueError('invalid story scene')
        sid = _text(scene, 'id', 64)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', sid) or sid in ids:
            raise ValueError('scene IDs must be unique canonical identifiers')
        ids.add(sid)
        if scene.get('kind') not in {'transition', 'investigation', 'social', 'combat', 'finale', 'exploration'}:
            raise ValueError('invalid story scene kind')
        if type(scene.get('public')) is not bool:
            raise ValueError('scene public must be boolean')
        nxt = scene.get('next_ids', [])
        hints = scene.get('hints', [])
        if not isinstance(nxt, list) or len(nxt) > 8 or any(not isinstance(i, str) for i in nxt):
            raise ValueError('invalid next scene IDs')
        if not isinstance(hints, list) or len(hints) > 3 or any(not isinstance(i, str) or len(i) > 500 for i in hints):
            raise ValueError('invalid story hints')
        normalized.append({'id': sid, 'title': _text(scene, 'title', 160), 'kind': scene['kind'],
                           'objective': _text(scene, 'objective', 240),
                           'description': _text(scene, 'description', empty=True), 'public': scene['public'],
                           'exit': _text(scene, 'exit', 500), 'next_ids': list(dict.fromkeys(nxt)), 'hints': hints[:]})
    if raw.get('start') not in ids or any(i not in ids for s in normalized for i in s['next_ids']):
        raise ValueError('unresolved story scene reference')
    reachable = {raw['start']}
    for _ in normalized:
        reachable.update(i for scene in normalized if scene['id'] in reachable for i in scene['next_ids'])
    if reachable != ids:
        raise ValueError('the plan contains scenes unreachable from its start')
    return {'format_version': 1, 'theme': _text(raw, 'theme', 240), 'party_goal': _text(raw, 'party_goal', 400),
            'mode': raw['mode'], 'npc_policy': raw['npc_policy'], 'core_npcs': list(dict.fromkeys(core)),
            'start': raw['start'], 'scenes': normalized}


def adopt(instance: Any, raw: Any, *, expected_run: str, expected_revision: int, source: str) -> None:
    state = snapshot(instance)
    if instance.adventure_binding:
        raise ValueError('bound adventures use their existing runtime authority')
    if type(expected_revision) is not int or instance.run_id != expected_run or state['revision'] != expected_revision:
        raise ValueError('stale story plan; refresh the current run/revision')
    if source not in {'gm', 'ai_original'}:
        raise ValueError('invalid story provenance')
    plan = validate_plan(raw, set(instance.npcs))
    state.update(plan=plan, current_id=plan['start'], revealed=[plan['start']], completed=[],
                 revision=state['revision'] + 1, source=source, run_id=instance.run_id, stalled_rounds=0)
    state['events'].append({'kind': 'adopted', 'revision': state['revision'], 'source': source})
    instance.modules[MODULE_NAME] = state


def advance(instance: Any, candidate: Any, *, confirmed: bool) -> None:
    if not confirmed:
        raise PermissionError('GM confirmation is required; model candidates are advisory')
    state = snapshot(instance)
    if not isinstance(candidate, dict) or type(candidate.get('format_version')) is not int or candidate.get('format_version') != 1 or not state.get('plan'):
        raise ValueError('invalid story transition')
    if type(candidate.get('revision')) is not int or candidate.get('run_id') != instance.run_id or candidate.get('revision') != state['revision']:
        raise ValueError('stale story transition')
    current = next(s for s in state['plan']['scenes'] if s['id'] == state['current_id'])
    if candidate.get('from_id') != current['id'] or candidate.get('to_id') not in current['next_ids']:
        raise ValueError('transition is not adjacent to the current scene')
    evidence = candidate.get('evidence_rounds')
    rounds = {entry.get('round') for entry in instance.log if entry.get('gm_response')}
    if (not isinstance(evidence, list) or not evidence or len(evidence) > 20
            or any(type(r) is not int or r not in rounds for r in evidence)):
        raise ValueError('reference committed source rounds and confirm the exit condition')
    state['completed'] = list(dict.fromkeys([*state['completed'], current['id']]))
    state['current_id'] = candidate['to_id']
    state['revealed'] = list(dict.fromkeys([*state['revealed'], candidate['to_id']]))
    state['revision'] += 1
    state['stalled_rounds'] = 0
    state.pop('candidate', None)
    state['events'].append({'kind': 'transition', **deepcopy(candidate), 'committed_revision': state['revision']})
    instance.modules[MODULE_NAME] = state


def project(instance: Any, *, viewer_is_gm: bool) -> dict[str, Any]:
    state = snapshot(instance)
    plan = state.get('plan')
    if not plan or state.get('run_id') != instance.run_id:
        return {}
    scene = next(s for s in plan['scenes'] if s['id'] == state['current_id'])
    result: dict[str, Any] = {'current_nodes': [], 'objectives': []}
    if viewer_is_gm or (scene['public'] and scene['id'] in state['revealed']):
        result['current_nodes'] = [{'name': scene['title'], 'description': scene['description']}]
        result['objectives'] = [{'name': scene['objective'], 'status': 'active'}]
    if viewer_is_gm:
        count = state['stalled_rounds']
        hints = scene['hints']
        result.update(revision=state['revision'], run_id=instance.run_id, source=state['source'],
                      current_id=scene['id'], plan=deepcopy(plan), exit=scene['exit'],
                      stalled_rounds=count, stall_hint=hints[min(len(hints) - 1, count // 2 - 1)] if hints and count >= 2 else '',
                      warnings=deepcopy(state['warnings']), candidate=deepcopy(state.get('candidate')),
                      possible_next_nodes=[{'id': sid, 'name': next(s['title'] for s in plan['scenes'] if s['id'] == sid)}
                                           for sid in scene['next_ids']])
    return result


def allow_npc(instance: Any, npc_id: str) -> bool:
    state = snapshot(instance)
    plan = state.get('plan')
    if not plan or plan['npc_policy'] == 'open' or npc_id in instance.npcs or npc_id in plan['core_npcs']:
        return True
    slot = get_module_state(instance, MODULE_NAME)
    slot['warnings'] = [*slot['warnings'][-19:], f'Unadopted NPC state rejected: {npc_id[:160]}']
    return False


def _begin(instance: Any) -> None:
    before = snapshot(instance)
    before.pop('_before_round', None)
    get_module_state(instance, MODULE_NAME)['_before_round'] = before


def _commit(instance: Any, entry: Any, _pre: Any) -> None:
    state = get_module_state(instance, MODULE_NAME)
    if '_before_round' not in state and not state.get('plan'):
        return
    entry['pre_run_story'] = state.pop('_before_round', snapshot(instance))
    if state.get('plan'):
        state['stalled_rounds'] += 1


def _abort(instance: Any) -> bool:
    state = snapshot(instance)
    before = state.get('_before_round')
    if isinstance(before, dict):
        instance.modules[MODULE_NAME] = deepcopy(before)
        return True
    return False


def _rewind(instance: Any, entry: Any, _round: int, _source: str) -> None:
    require_writable(instance)
    before = entry.get('pre_run_story')
    if isinstance(before, dict):
        instance.modules[MODULE_NAME] = deepcopy(before)
    else:
        # A pre-plan historical branch has no plan. Never inject future secrets.
        instance.modules[MODULE_NAME] = fresh()


def _record(instance: Any, kind: str, value: Any) -> None:
    if kind == 'story_candidate' and snapshot(instance).get('plan'):
        # Never execute model-authored transitions. GM reviews the typed candidate.
        get_module_state(instance, MODULE_NAME)['candidate'] = deepcopy(value) if isinstance(value, dict) else None


def _reset(instance: Any) -> None:
    require_writable(instance)
    instance.modules[MODULE_NAME] = fresh()


def _workspace_revision(instance: Any, revisions: dict[str, Any]) -> None:
    state = snapshot(instance)
    if state.get('plan'):
        revisions[MODULE_NAME] = {key: state.get(key) for key in
                                 ('run_id', 'revision', 'current_id', 'stalled_rounds', 'candidate', 'warnings')}


register_module_state(ModuleStateSpec(MODULE_NAME, SCHEMA_VERSION, fresh, ensure))
module_hooks.register(module_hooks.GM_WORKSPACE_REVISIONS, MODULE_NAME, _workspace_revision)
module_hooks.register(module_hooks.AUTHORITATIVE_WRITE_ALLOWED, MODULE_NAME, require_writable)
module_hooks.register(module_hooks.ROUND_PROCESSING_BEGIN, MODULE_NAME, _begin)
module_hooks.register(module_hooks.ROUND_COMMIT, MODULE_NAME, _commit)
module_hooks.register(module_hooks.ROUND_ABORT, MODULE_NAME, _abort)
module_hooks.register(module_hooks.ROUND_REWIND_RESTORE, MODULE_NAME, _rewind)
module_hooks.register(module_hooks.STATE_RECORD, MODULE_NAME, _record)
module_hooks.register(module_hooks.NPC_ADMISSION, MODULE_NAME, allow_npc)
module_hooks.register(module_hooks.INSTANCE_RESET_PREFLIGHT, MODULE_NAME, require_writable)
module_hooks.register(module_hooks.INSTANCE_NEW_RUN_PREFLIGHT, MODULE_NAME, require_writable)
module_hooks.register(module_hooks.ROUND_RECOVERY_PREFLIGHT, MODULE_NAME, require_writable)
module_hooks.register(module_hooks.INSTANCE_RESET, MODULE_NAME, _reset)
