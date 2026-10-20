"""Generic preparation and signing for owner-defined application commands."""
from __future__ import annotations

import json
from copy import deepcopy

from src.application_actions import ActionAssessment, PreparedAction
from src.webui.services.assistant_authorization import SCOPE_KEYS

_SIGNED_FIELDS = ('approval_id', 'tool', 'label', 'arguments', 'expires_at', 'guard')
_OPTIONAL_SIGNED_FIELDS = ('preview', 'contract_digest', 'prepared', 'assessment')


def signed_plan(plan: dict) -> dict:
    return {**{key: plan[key] for key in _SIGNED_FIELDS},
            **{key: plan[key] for key in _OPTIONAL_SIGNED_FIELDS if key in plan}}


def prepare_action(action, arguments: dict, owner: str) -> PreparedAction | None:
    if action.prepare is None:
        return None
    prepared = action.prepare(deepcopy(arguments), owner)
    if not isinstance(prepared, PreparedAction) or not isinstance(prepared.assessment, ActionAssessment):
        raise ValueError('Invalid prepared application command')
    impact = prepared.assessment
    if (impact.effect not in {'write', 'disclosure', 'external', 'destructive'}
            or type(impact.requires_approval) is not bool or not isinstance(impact.targets, tuple)
            or not isinstance(prepared.preview, dict) or not isinstance(prepared.payload, dict)
            or not isinstance(prepared.guard, str) or not prepared.guard):
        raise ValueError('Invalid prepared application impact')
    if action.effective_effect in {'external', 'destructive'} and impact.effect != action.effective_effect:
        raise ValueError('Prepared commands cannot downgrade external or destructive effects')
    for target in impact.targets:
        if (not isinstance(target, dict) or not target or set(target) - SCOPE_KEYS
                or any(not isinstance(value, str) or not value.strip() or len(value) > 500 for value in target.values())):
            raise ValueError('Invalid prepared target scope')
    if len(json.dumps(prepared.payload, ensure_ascii=False).encode()) > 4 * 1024 * 1024:
        raise ValueError('Prepared execution payload exceeds the durable plan limit')
    return prepared


def stored_assessment(plan: dict) -> ActionAssessment | None:
    value = plan.get('assessment')
    if value is None:
        return None
    return ActionAssessment(value['effect'], value['requires_approval'], tuple(deepcopy(value['targets'])))
