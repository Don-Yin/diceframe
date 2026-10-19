"""Explicit execution dependencies for checkpointed application commands.

Owners retain their transactions and receipts. The Agent supplies only its
durable checkpoint, cancellation fence and current authorization boundary.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable


class ActionExecutionStopped(Exception):
    """No new owner transaction may start; already committed receipts survive."""


@dataclass
class ActionExecutionContext:
    plan_id: str
    state: dict
    persist: Callable[[dict], None]
    check_access: Callable[[], None]

    def check(self) -> None:
        self.check_access()

    def checkpoint(self, state: dict) -> None:
        candidate = deepcopy(state)
        self.persist(candidate)
        self.state = candidate
