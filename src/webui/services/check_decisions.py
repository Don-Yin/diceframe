"""Atomic application boundary for post-roll decisions and guarded re-rolls."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.engine import check_decisions
from src.engine.game_state import GameState
from src.engine.participant_view import Viewer
from src.engine.staged_transaction import StagedGameTransaction


@dataclass(frozen=True)
class CheckDecisionDependencies:
    get_instance: Callable[[str], Any | None]
    save_instance: Callable[[Any], Awaitable[None]]


def decision_payload(inst: Any, result: dict) -> dict:
    luck = inst.pending_luck_checks()
    push = check_decisions.pending(inst)
    done = inst.state != GameState.ACTIVE_JUDGMENT
    return {**result, "phase": "done" if done else "luck" if luck or push else "ready",
            "pending_luck_decisions": luck, "pending_push_decisions": push,
            "ready_to_resolve": not done and not luck and not push, "round_already_resolved": done}


class CheckDecisionService:
    def __init__(self, dependencies: CheckDecisionDependencies):
        self.deps = dependencies

    async def update(self, key: str, check_id: str, viewer: Viewer, operation: str, body: Any) -> dict:
        inst = self.deps.get_instance(key)
        if inst is None:
            return {"ok": False, "code": "GAME_NOT_FOUND"}
        uid = inst.gm_uid if viewer.is_gm else viewer.uid if viewer.is_seat else ""
        if not uid or (not viewer.is_gm and uid not in inst.players):
            return {"ok": False, "code": "PUSH_FORBIDDEN"}
        if not isinstance(body, dict) or body.keys() - {"run_id", "round_number", "expected_revision", "reason", "consequence"}:
            return {"ok": False, "code": "PUSH_INVALID_REQUEST"}
        try:
            async with inst.authoritative_write() as entered:
                if not entered:
                    return {"ok": False, "code": "REWRITE_IN_PROGRESS"}
                async with inst._lock:
                    if self.deps.get_instance(key) is not inst:
                        return {"ok": False, "code": "STALE_RUN"}
                    transaction = StagedGameTransaction(inst)
                    result = check_decisions.change(transaction.staged, check_id, uid, operation,
                        run_id=body.get("run_id"), round_number=body.get("round_number"),
                        expected_revision=body.get("expected_revision"), reason=body.get("reason"), consequence=body.get("consequence"))
                    transaction.publish(inst)
                    try:
                        await self.deps.save_instance(inst)
                    except BaseException:
                        transaction.rollback(inst)
                        raise
                    # Runtime timers belong to the live instance; cancel after persistence.
                    inst._cancel_luck_timer(check_id)
                    return decision_payload(inst, {"ok": True, "check_result": result})
        except PermissionError:
            return {"ok": False, "code": "PUSH_FORBIDDEN"}
        except ValueError:
            return {"ok": False, "code": "PUSH_INVALID_OR_STALE", "error": "检定选择已变化，请刷新后重试"}
