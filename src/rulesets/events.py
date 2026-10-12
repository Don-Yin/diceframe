"""Generic transactional EventBatch validation and replay protection."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from json import dumps
from typing import Any, Callable


class EventBatchError(ValueError):
    """Raised when an event batch cannot be applied atomically."""


EventReducer = Callable[[dict[str, Any], dict[str, Any]], None]


def stable_batch_id(intent: dict[str, Any], expected_version: int) -> str:
    """Return one retry-stable identifier without trusting a client batch id."""

    intent_id = str(intent.get("intent_id") or "").strip()
    if not intent_id:
        raise EventBatchError("intent_id is required")
    payload = dumps(intent, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = sha256(f"{expected_version}:{intent_id}:{payload}".encode()).hexdigest()
    return f"batch_{digest[:32]}"


def validate_batch(batch: dict[str, Any]) -> None:
    batch_id = str(batch.get("batch_id") or "")
    intent_id = str(batch.get("intent_id") or "")
    if not batch_id.startswith("batch_") or len(batch_id) > 80:
        raise EventBatchError("batch_id is invalid")
    if not intent_id or len(intent_id) > 120:
        raise EventBatchError("intent_id is invalid")
    before = batch.get("expected_version")
    after = batch.get("result_version")
    if (
        isinstance(before, bool) or not isinstance(before, int) or before < 0
        or isinstance(after, bool) or not isinstance(after, int) or after != before + 1
    ):
        raise EventBatchError("event batch versions are invalid")
    events = batch.get("events")
    if not isinstance(events, list) or not events or len(events) > 100:
        raise EventBatchError("event batch must contain 1 to 100 events")
    for event in events:
        if not isinstance(event, dict):
            raise EventBatchError("event must be an object")
        event_type = str(event.get("type") or "")
        if not event_type or len(event_type) > 100:
            raise EventBatchError("event type is invalid")


def apply_event_batch(
    snapshot: dict[str, Any],
    ledger: list[dict[str, Any]],
    batch: dict[str, Any],
    reducer: EventReducer,
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    """Apply a whole batch to copies, or leave both inputs untouched.

    Returns ``(snapshot, ledger, duplicate)``. Re-applying the same batch is a
    successful no-op; conflicting versions and reducer failures reject the
    entire transaction.
    """

    validate_batch(batch)
    batch_id = str(batch["batch_id"])
    existing = next(
        (item for item in ledger if str(item.get("batch_id") or "") == batch_id),
        None,
    )
    if existing is not None:
        if str(existing.get("intent_id") or "") != str(batch["intent_id"]):
            raise EventBatchError("batch_id conflicts with an existing intent")
        return deepcopy(snapshot), deepcopy(ledger), True
    current_version = snapshot.get("version", 0)
    if current_version != batch["expected_version"]:
        raise EventBatchError(
            f"state version conflict: expected {batch['expected_version']}, "
            f"current {current_version}"
        )
    updated = deepcopy(snapshot)
    for event in batch["events"]:
        reducer(updated, deepcopy(event))
    updated["version"] = batch["result_version"]
    next_ledger = deepcopy(ledger)
    next_ledger.append(deepcopy(batch))
    return updated, next_ledger, False
