from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from src.application_action_execution import ActionExecutionContext, ActionExecutionStopped
from src.application_actions import PreparedAction, _digest
from src.webui.services.lorebook_visibility_plans import (
    LorebookVisibilityPlanDependencies,
    LorebookVisibilityPlans,
    audience_expands,
)


def _fixture():
    books = {
        "b1": {
            "book": {"id": "b1", "name": "One"},
            "entries": [
                {"id": "e1", "name": "secret", "content": "GM: keep", "visible_to": []},
                {"id": "e2", "name": "public", "content": "clue", "visible_to": ["*"]},
            ],
            "bindings": [{"id": "bind", "book_id": "b1", "scope_kind": "game", "scope_id": "g1"}],
        },
        "b2": {
            "book": {"id": "b2", "name": "Two"},
            "entries": [{"id": "e3", "name": "third", "content": "clue", "visible_to": []}],
            "bindings": [],
        },
    }
    receipts = {}
    writes = []

    def list_entries(book_id):
        snap = books[book_id]
        return {"ok": True, "book": deepcopy(snap["book"]), "entries": deepcopy(snap["entries"])}

    def snapshot(book_id):
        return deepcopy(books[book_id])

    def preview(owner, book_id, rows, digest):
        return {"book_id": book_id, "changed_count": len(rows), "affected_games": ["g1"] if book_id == "b1" else []}

    def write(owner, book_id, rows, digest, *, operation_id):
        for patch in rows:
            row = next(item for item in books[book_id]["entries"] if item["id"] == patch["id"])
            row["visible_to"] = list(patch["visible_to"])
        result = {"ok": True, "operation_id": operation_id, "operation_ids": [f"child-{book_id}"],
                  "changed_count": len(rows),
                  "request_digest": _digest({"book_id": book_id, "rows": rows,
                                              "expected_entries_digest": digest})}
        receipts[(owner, operation_id)] = result
        writes.append((book_id, operation_id))
        return result

    def receipt(owner, operation_id):
        return deepcopy(receipts.get((owner, operation_id)))

    deps = LorebookVisibilityPlanDependencies(
        list_entries=list_entries, snapshot=snapshot, preview=preview,
        write=write, receipt=receipt,
        game_players=lambda game_key, owner: {"players": {"u1": {}}},
    )
    return books, writes, LorebookVisibilityPlans(deps)


def test_audience_expansion_is_based_on_actual_markers():
    assert audience_expands([], ["*"])
    assert audience_expands(["u1"], ["u1", "u2"])
    assert not audience_expands(["*"], ["u1"])
    assert not audience_expands([], [])


def test_prepare_freezes_explicit_population_and_never_payloads_body():
    books, _writes, service = _fixture()
    prepared = service.prepare({"book_ids": ["b1", "b2"], "audience": "public"}, "owner")
    assert isinstance(prepared, PreparedAction)
    assert prepared.assessment.requires_approval is True
    assert prepared.assessment.effect == "disclosure"
    assert prepared.preview["book_count"] == 2
    assert prepared.payload["books"][0]["entry_ids"] == ["e1", "e2"]
    assert "content" not in repr(prepared.payload)

    books["b1"]["entries"].append({"id": "new", "content": "later", "visible_to": []})
    report = asyncio.run(service.execute(prepared.payload, "owner", _context(prepared.payload)))
    assert report["status"] == "failed"


def test_interrupted_report_keeps_running_books_unconfirmed():
    _books, _writes, service = _fixture()
    prepared = service.prepare({"book_ids": ["b1", "b2"], "audience": "gm"}, "owner")
    report = service._report(
        prepared.payload,
        {"books": {
            "b1": {"status": "running", "operation_id": "op-b1"},
            "b2": {},
        }},
        "interrupted",
    )
    assert report["status"] == "interrupted"
    assert [row["status"] for row in report["books"]] == ["unconfirmed", "not_executed"]
    assert report["unconfirmed_count"] == 1
    assert report["not_executed_count"] == 1


def test_checkpoint_completion_requires_every_payload_book_successful():
    _books, _writes, service = _fixture()
    prepared = service.prepare({"book_ids": ["b1", "b2"], "audience": "gm"}, "owner")
    captured = []
    context = ActionExecutionContext(
        plan_id="checkpoint-plan", state={}, persist=lambda value: captured.append(deepcopy(value)),
        check_access=lambda: None,
    )
    service._checkpoint(
        context, prepared.payload,
        {"plan_digest": prepared.guard, "books": {"b1": {"status": "succeeded"}}},
        "completed",
    )
    assert captured[-1]["report"]["status"] == "partial"
    assert captured[-1]["report"]["success_count"] == 1
    assert captured[-1]["report"]["not_executed_count"] == 1


def _context(payload, *, state=None, checks=None):
    checks = checks if checks is not None else []
    persisted = []
    return ActionExecutionContext(
        plan_id="plan-1", state=state or {}, persist=lambda value: persisted.append(value),
        check_access=lambda: checks.append(True),
    )


@pytest.mark.asyncio
async def test_execute_is_per_book_idempotent_and_resumes_after_cancel():
    _books, writes, service = _fixture()
    prepared = service.prepare({"book_ids": ["b1", "b2"], "audience": "gm"}, "owner")
    calls = []

    def stop_after_first():
        calls.append(True)
        if len(calls) > 1:
            raise ActionExecutionStopped()

    context = ActionExecutionContext(
        plan_id="plan-1", state={}, persist=lambda state: None,
        check_access=stop_after_first,
    )
    report = await service.execute(prepared.payload, "owner", context)
    assert report["status"] == "cancelled"
    assert report["success_count"] == 1
    assert context.state["report"]["status"] == "cancelled"
    assert len(writes) == 1

    context.check_access = lambda: None
    resumed = await service.execute(prepared.payload, "owner", context)
    assert resumed["status"] == "completed"
    assert len(writes) == 2


@pytest.mark.asyncio
async def test_execute_reports_partial_when_a_later_book_fails():
    _books, writes, service = _fixture()
    prepared = service.prepare({"book_ids": ["b1", "b2"], "audience": "gm"}, "owner")
    original = service.deps.write

    def fail_second(owner, book_id, rows, digest, *, operation_id):
        if book_id == "b2":
            raise RuntimeError("second book uncertain")
        return original(owner, book_id, rows, digest, operation_id=operation_id)

    service.deps = LorebookVisibilityPlanDependencies(
        list_entries=service.deps.list_entries, snapshot=service.deps.snapshot,
        preview=service.deps.preview, write=fail_second, receipt=service.deps.receipt,
        game_players=service.deps.game_players,
    )
    report = await service.execute(prepared.payload, "owner", _context(prepared.payload))
    assert report["status"] == "partial"
    assert report["success_count"] == 1 and report["unconfirmed_count"] == 1
    assert len(writes) == 1
