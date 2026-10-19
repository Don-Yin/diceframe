"""Application-owned action contracts shared by UI adapters and agents.

Registration is explicit at application composition, never inferred from Python
members or HTTP routes. Domain handlers retain authorization and state authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Callable, Iterable


@dataclass(frozen=True)
class ApplicationAction:
    name: str
    label: str
    schema: dict
    handler: Callable
    mutation: bool = False
    creates_draft: bool = False
    uses_draft: bool = False
    guard: Callable | None = None
    preview: Callable | None = None
    domain: str = 'application'
    effect: str = 'read'
    version: int = 1
    automatic: bool = False
    instructions: str = ''
    authorize: Callable | None = None

    @property
    def effective_effect(self) -> str:
        return 'write' if self.mutation and self.effect == 'read' else self.effect

    def descriptor(self) -> dict:
        return {'name': self.name, 'label': self.label, 'description': self.label,
                'parameters': deepcopy(self.schema), 'requires_confirmation': self.mutation,
                'domain': self.domain, 'effect': self.effective_effect, 'version': self.version,
                'automatic': self.automatic, 'instructions': self.instructions}

    @property
    def contract_digest(self) -> str:
        return _digest(self.descriptor())


def _digest(value) -> str:
    return 'sha256:' + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                                separators=(',', ':')).encode()).hexdigest()


class ActionRegistry:
    def __init__(self, actions: Iterable[ApplicationAction] = ()):
        self._actions: dict[str, ApplicationAction] = {}
        self._sources: dict[str, Callable] = {}
        self._source_names: dict[str, set[str]] = {}
        self._source_errors: set[str] = set()
        for action in actions:
            self.register(action)

    @staticmethod
    def _validate(action):
        if (not isinstance(action, ApplicationAction) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,95}', action.name)
                or not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', action.domain)
                or action.effect not in {'read', 'write', 'disclosure', 'destructive', 'external'}
                or type(action.version) is not int or action.version < 1
                or not isinstance(action.schema, dict) or action.schema.get('type') != 'object'
                or not callable(action.handler)):
            raise ValueError('Invalid application action contract')
        if action.automatic and (not action.mutation or action.effective_effect != 'write' or not action.guard):
            raise ValueError('Automatic actions require a guarded ordinary write')

    def register(self, action: ApplicationAction) -> None:
        self._validate(action)
        if action.name in self._actions:
            raise ValueError('duplicate application action')
        self._actions[action.name] = replace(action, schema=deepcopy(action.schema))

    def replace(self, action: ApplicationAction) -> None:
        self._validate(action)
        previous = self._actions.get(action.name)
        if previous is None or action.version <= previous.version:
            raise ValueError('Replacement requires an existing action and a newer contract version')
        self._actions[action.name] = replace(action, schema=deepcopy(action.schema))

    def unregister(self, name: str) -> None:
        self._actions.pop(name, None)

    def register_source(self, name: str, provider: Callable) -> None:
        """Attach a trusted owner of a changing action set, such as PluginHost."""
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', name) or not callable(provider):
            raise ValueError('Invalid application action source')
        if name in self._sources:
            raise ValueError('duplicate application action source')
        self._sources[name] = provider
        self._source_names[name] = set()

    def refresh_sources(self) -> None:
        for name, provider in self._sources.items():
            previous = self._source_names[name]
            try:
                actions = tuple(provider())
                for action in actions:
                    self._validate(action)
                identities = {action.name for action in actions}
                if len(identities) != len(actions) or identities & (set(self._actions) - previous):
                    raise ValueError('Action source conflicts with another owner')
            except (ValueError, TypeError, RuntimeError):
                for identity in previous:
                    self._actions.pop(identity, None)
                self._source_names[name] = set()
                self._source_errors.add(name)
                continue
            for identity in previous - identities:
                self._actions.pop(identity, None)
            for action in actions:
                self._actions[action.name] = replace(action, schema=deepcopy(action.schema))
            self._source_names[name] = identities
            self._source_errors.discard(name)

    def get(self, name: str) -> ApplicationAction | None:
        return self._actions.get(name)

    def values(self) -> tuple[ApplicationAction, ...]:
        return tuple(self._actions.values())

    @property
    def revision(self) -> str:
        return _digest([action.descriptor() for action in sorted(self.values(), key=lambda item: item.name)])

    def describe(self, name: str) -> dict:
        action = self.get(name)
        if action is None:
            raise ValueError('Application capability unavailable')
        return action.descriptor()

    def search(self, query: str = '', domain: str = '', *, limit: int = 80) -> dict:
        if not isinstance(query, str) or len(query) > 200 or not isinstance(domain, str) or len(domain) > 40:
            raise ValueError('Invalid capability query')
        words = query.casefold().split()
        matches = []
        for action in sorted(self.values(), key=lambda item: item.name):
            haystack = f'{action.name} {action.label} {action.domain} {action.instructions}'.casefold()
            if (not domain or action.domain == domain) and all(word in haystack for word in words):
                item = action.descriptor()
                item.pop('parameters')
                matches.append(item)
        return {'ok': True, 'revision': self.revision, 'capabilities': matches[:limit],
                'unavailable_sources': sorted(self._source_errors),
                'total': len(matches)}
