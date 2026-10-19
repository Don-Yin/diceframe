"""Stage the existing rules authority ladder while model requests run unlocked."""
from __future__ import annotations

import random
import logging
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from src.engine.modules import session_stats
from src.engine.staged_transaction import StagedGameTransaction
from src.llm.combat_choice import HostedCombatChooser
from src.llm.seat_policy import SeatRuntime
from src.rulesets.automation import advance_automatic_intents_with_choice

logger = logging.getLogger("trpg")


async def plan_and_commit(
    instance: Any, runtime: Any, seats: SeatRuntime, *,
    preflight: Callable[[], Awaitable[dict | None]], save: Callable[[Any], Awaitable[None]],
    project_batch: Callable[[Any, dict, dict], None],
    initial_intent: dict | None = None, resume_uid: str | None = None,
) -> dict:
    async with instance._lock:
        error = await preflight()
        if error:
            return error
        if resume_uid is not None:
            pending = runtime.next_automatic_intent(instance)
            if not pending or pending.get("actor_id") != f"player:{resume_uid}":
                return {"ok": True, "resumed": False, "reason": "not_this_seat"}
        transaction = StagedGameTransaction(instance)
    staged, rng = transaction.staged, random.SystemRandom()
    chooser = HostedCombatChooser(runtime, seats)
    initial, batch, applied = {}, None, {}
    try:
        if initial_intent is not None:
            initial = runtime.resolve_intent(staged, initial_intent, rng)
            if not initial.get("ok"):
                return initial
            batch = initial.get("event_batch")
            if not isinstance(batch, dict):
                return {"ok": False, "code": "INVALID_EVENT_BATCH", "error": "Invalid event batch"}
            applied = runtime.apply_event_batch(staged, batch)
            project_batch(staged, batch, applied)
        batches, results = await advance_automatic_intents_with_choice(
            runtime, staged, rng, choose=chooser.choose,
            on_applied=lambda b, a: project_batch(staged, b, a),
        )
        session_stats.touch(staged)
    except (ValueError, KeyError, TypeError):
        logger.warning("Hosted combat plan rejected before publication", exc_info=True)
        return {"ok": False, "code": "AUTOMATIC_TURN_FAILED", "error": "Combat plan rejected; refresh and retry"}
    # Do not hold any live authority, processing or state lock across model I/O.
    async with instance.authoritative_write() as entered:
        if not entered:
            return {"ok": False, "code": "AUTOMATIC_PLAN_STALE", "error": "Game is being rewritten; retry later"}
        async with instance._lock:
            if not transaction.matches(instance) or chooser.admission_check():
                return {"ok": False, "code": "AUTOMATIC_PLAN_STALE", "error": "Game or AI configuration changed; refresh and retry"}
            error = await preflight()
            if error:
                return error
            transaction.publish(instance)
            try:
                await save(instance)
            except BaseException:
                transaction.rollback(instance)
                raise
    resolved_batches = [*([batch] if batch is not None else []), *batches]
    return {"ok": True, "resumed": True, "batches": resolved_batches,
            "result": {**applied, "replayed": bool(initial.get("replayed", False)),
                "pending_decision": deepcopy(initial.get("pending_decision")),
                "automatic_event_batches": batches, "automatic_results": results,
                "resolved_event_batches": resolved_batches}}
