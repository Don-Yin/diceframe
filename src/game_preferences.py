"""Versioned application contract for new-table defaults (never live inheritance)."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.content.gm_style import normalize_gm_style_override

UNSET = object()
ENUMS = {
    'dice_reveal_mode': {'auto', 'click'},
    'narrative_perspective': {'auto', 'immersive', 'third_person'},
    'story_mode': {'prose', 'dialogue'},
    'advancement_mode': {'milestone', 'xp'},
    'advancement_authority': {'ai_gm', 'gm'},
}


def default_preferences() -> dict[str, Any]:
    return {
        'push_enabled': True, 'quick_actions_enabled': True, 'dice_reveal_mode': 'auto', 'luck_timeout_seconds': 60,
        'narrative_perspective': 'auto', 'story_mode': 'prose', 'gm_style_override': None,
        'advancement_mode': 'milestone', 'advancement_authority': 'ai_gm',
    }


def validate_preferences(raw: Any, *, partial: bool = False) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError('game preferences must be an object')
    if raw.keys() - default_preferences().keys():
        raise ValueError('unknown game preference fields: ' + ', '.join(sorted(raw.keys() - default_preferences().keys())))
    result = {} if partial else default_preferences()
    for key, value in raw.items():
        if key in {'push_enabled', 'quick_actions_enabled'} and type(value) is not bool:
            raise ValueError(f'{key} must be a boolean')
        if key == 'luck_timeout_seconds' and (type(value) is not int or not 0 <= value <= 3600):
            raise ValueError('luck_timeout_seconds must be an integer between 0 and 3600')
        if key in ENUMS and (not isinstance(value, str) or value not in ENUMS[key]):
            raise ValueError(f'invalid {key}')
        if key == 'gm_style_override':
            value = normalize_gm_style_override(value)
        result[key] = deepcopy(value)
    return result
