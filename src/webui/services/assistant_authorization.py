"""Server-held, owner-session authorization for bounded Agent tasks."""
from __future__ import annotations

from copy import deepcopy

SCOPE_KEYS = frozenset({'game_key', 'world_id', 'book_id', 'card_id'})


def make_authorization(mode, scope, domains, max_steps, now):
    if mode not in {'suggest', 'routine', 'task'}:
        raise ValueError('Unknown authorization mode')
    if (not isinstance(scope, dict) or set(scope) - SCOPE_KEYS
            or any(not isinstance(value, str) or not 1 <= len(value) <= 500 for value in scope.values())):
        raise ValueError('Invalid authorization scope')
    if (not isinstance(domains, list) or len(domains) > 16 or len(set(domains)) != len(domains)
            or any(not isinstance(value, str) or not value or len(value) > 40 for value in domains)):
        raise ValueError('Invalid authorization domains')
    if type(max_steps) is not int or not 1 <= max_steps <= 64:
        raise ValueError('Action budget must be between 1 and 64')
    if mode == 'suggest':
        return None
    return {'mode': mode, 'scope': deepcopy(scope), 'domains': list(domains), 'max_steps': max_steps,
            'remaining_steps': max_steps, 'expires_at': now + (3600 if mode == 'task' else 14400)}


def current_authorization(data, now):
    value = data.get('authorization')
    if (not isinstance(value, dict) or value.get('expires_at', 0) <= now
            or value.get('remaining_steps', 0) <= 0):
        return None
    return deepcopy(value)


def permits(grant, action, arguments):
    if not grant or action.effective_effect in {'destructive', 'external'}:
        return False
    if grant['domains'] and action.domain not in grant['domains']:
        return False
    scope = grant['scope']
    if scope:
        if any(key not in arguments or scope[key] != arguments[key] for key in scope):
            return False
    if grant['mode'] == 'routine':
        return action.automatic and action.effective_effect == 'write'
    return grant['mode'] == 'task' and action.effective_effect in {'write', 'disclosure'}
