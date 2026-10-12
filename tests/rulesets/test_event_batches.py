from __future__ import annotations

from copy import deepcopy

import pytest

from src.rulesets.events import EventBatchError, apply_event_batch, stable_batch_id


def _batch(intent_id: str = "intent-1") -> dict:
    intent = {"intent_id": intent_id, "type": "test.add", "amount": 3}
    return {
        "batch_id": stable_batch_id(intent, 0),
        "intent_id": intent_id,
        "expected_version": 0,
        "result_version": 1,
        "events": [{"type": "counter.added", "amount": 3}],
    }


def test_event_batch_is_atomic_versioned_and_retry_idempotent() -> None:
    initial = {"version": 0, "counter": 1}
    ledger: list[dict] = []

    updated, next_ledger, duplicate = apply_event_batch(
        initial, ledger, _batch(),
        lambda state, event: state.update(counter=state["counter"] + event["amount"]),
    )
    replayed, replay_ledger, replay_duplicate = apply_event_batch(
        updated, next_ledger, _batch(), lambda state, event: state.clear(),
    )

    assert initial == {"version": 0, "counter": 1}
    assert ledger == []
    assert updated == {"version": 1, "counter": 4}
    assert duplicate is False
    assert replayed == updated
    assert replay_ledger == next_ledger
    assert replay_duplicate is True


def test_event_batch_rolls_back_when_any_event_fails() -> None:
    initial = {"version": 0, "counter": 1}
    batch = _batch()
    batch["events"].append({"type": "counter.rejected"})
    before = deepcopy(initial)

    def reducer(state: dict, event: dict) -> None:
        if event["type"] == "counter.rejected":
            raise EventBatchError("rejected")
        state["counter"] += event["amount"]

    with pytest.raises(EventBatchError, match="rejected"):
        apply_event_batch(initial, [], batch, reducer)

    assert initial == before


def test_event_batch_rejects_stale_version() -> None:
    with pytest.raises(EventBatchError, match="version conflict"):
        apply_event_batch({"version": 7}, [], _batch(), lambda _state, _event: None)
