"""Isolated aggregate planning with optimistic, all-or-nothing publication."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def _projection(instance: Any) -> dict:
    result = deepcopy(instance.to_dict())
    # The save codec bounds inline history. A transaction must fence all history.
    result["log"] = deepcopy(instance.log)
    return result


def fork_domain_state(instance: Any) -> Any:
    """Copy a live aggregate without load-time normalization or shared locks.

    Loading a save intentionally removes ghost players and bounds history; it
    cannot be used to clone a currently running table with newly joined seats.
    The existing aggregate publication contract preserves domain objects while
    leaving runtime coordination attached to a fresh aggregate.
    """
    staged = type(instance)(game_key=instance.game_key, run_id=instance.run_id)
    staged.replace_persisted_state_from(instance)
    return staged


class StagedGameTransaction:
    """Caller captures/publishes under authority/state gates; planning is unlocked."""

    def __init__(self, instance: Any):
        self.before = fork_domain_state(instance)
        self.staged = fork_domain_state(instance)
        self._expected = _projection(instance)

    def matches(self, instance: Any) -> bool:
        return _projection(instance) == self._expected

    def publish(self, instance: Any) -> None:
        if not self.matches(instance):
            raise ValueError("game changed during transaction planning")
        instance.replace_persisted_state_from(self.staged)

    def rollback(self, instance: Any) -> None:
        instance.replace_persisted_state_from(self.before)
