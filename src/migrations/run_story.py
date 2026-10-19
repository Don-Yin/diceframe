"""Explicit import/normalization boundary for run-story version 1 slots."""
from typing import Any


def validate_slot_envelopes(payload: dict[str, Any]) -> None:
    """Reject damaged authority before generic module defaults discard it.

    Absent slots belong to older saves and may receive defaults. An explicitly
    stored non-object is corruption, not evidence that no settlement exists.
    Unknown object versions remain opaque for their owners to refuse on use.
    """
    modules = payload.get('modules')
    if 'modules' in payload and not isinstance(modules, dict):
        raise ValueError('invalid persisted module container')
    if isinstance(modules, dict):
        for name in ('run_story', 'skill_growth', 'run_finale'):
            if name in modules and not isinstance(modules[name], dict):
                raise ValueError(f'invalid persisted {name} module envelope')


def preserves_frozen_roster(payload: dict[str, Any]) -> bool:
    modules = payload.get('modules') or {}
    finale = modules.get('run_finale') or {}
    # Opaque future versions also must not undergo speculative ghost cleanup.
    return bool(finale and (finale.get('schema_version') != 1 or finale.get('job') or finale.get('archive')))


def rebind_story_state(payload: dict[str, Any], *, run_id: str) -> None:
    modules = payload.get('modules') or {}
    for name in ('run_story', 'skill_growth', 'run_finale'):
        raw = modules.get(name)
        if raw is not None and (not isinstance(raw, dict) or raw.get('schema_version') != 1):
            raise ValueError(f'cannot rebind unsupported {name} schema')
    finale = modules.get('run_finale') or {}
    if finale.get('job'):
        raise ValueError('cancel finale preparation before importing this save into another run')
    story = modules.get('run_story')
    if isinstance(story, dict) and story.get('plan'):
        story['run_id'] = run_id
        story.pop('candidate', None)
        story.pop('_before_round', None)
    for entry in payload.get('log') or []:
        if not isinstance(entry, dict):
            continue
        before = entry.get('pre_run_story')
        if isinstance(before, dict) and before.get('schema_version') == 1 and before.get('plan'):
            before['run_id'] = run_id
            before.pop('candidate', None)
            before.pop('_before_round', None)
    # Completed receipts/archives keep their original run provenance. Imported
    # ENDED saves remain read-only; import never reissues settled marks/rewards.
