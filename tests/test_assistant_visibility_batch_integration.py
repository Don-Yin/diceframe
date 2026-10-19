"""End to end visibility plans through WebAPI, SQLite, and the agent runtime."""

from copy import deepcopy
from dataclasses import replace

import pytest

from src.webui.services.assistant_agent import AgentRuntime
from tests.test_assistant_agent import Planner

pytest_plugins = ["tests.webapi_harness"]


def _entry(book_id, index=0, *, visible_to=None, content=None):
    return {
        "id": f"{book_id}-entry-{index}",
        "name": f"Entry {index}",
        "content": content or f"Authored content for {book_id} {index}",
        "keywords": [f"keyword-{book_id}", f"keyword-{index}"],
        "visible_to": list(visible_to or []),
        "extensions": {"provenance": {"source": "integration", "book": book_id}},
    }


def _books(store, ids, *, visible_to=None, content=None):
    for book_id in ids:
        store.create_lorebook({"id": book_id, "name": f"Book {book_id}", "source_kind": "user"})
        store.add_book_entry(
            book_id,
            _entry(book_id, visible_to=visible_to, content=content),
        )


async def _run(api, planner, *, owner="owner", prompt="Change the selected books", session_id=""):
    api._llm_client.call_tools = planner.call_tools
    events = []

    async def emit(name, value):
        events.append((name, deepcopy(value)))

    await api.assistant_agent_run(owner, [{"role": "user", "content": prompt}],
                                  "en", {"route": "library"}, session_id, emit)
    return events


def _session_id(events):
    return next(value["session_id"] for name, value in events if name == "session")


def _pending(events):
    return next(value for name, value in events if name == "approval")


def _group_planner(book_ids, audience):
    return Planner(
        {"tool": "read_catalog", "arguments": {"kind": "lorebooks"}},
        {"tool": "set_lorebooks_visibility", "arguments": {
            "book_ids": list(book_ids), "audience": audience}},
        {"tool": "respond", "answer": "Done"},
    )


@pytest.mark.asyncio
async def test_task_gm_batch_reads_catalog_and_executes_three_books_without_approval(web_api):
    api, store, *_ = web_api
    book_ids = ["batch-gm-a", "batch-gm-b", "batch-gm-c"]
    _books(store, book_ids, visible_to=["*"])
    before = {book_id: store.list_book_entries(book_id) for book_id in book_ids}
    planner = _group_planner(book_ids, "gm")
    grant = api.assistant_agent_authorize("owner", "", "task", {}, ["lorebook"], 8)

    events = await _run(api, planner, session_id=grant["session_id"])

    assert len(planner.calls) == 3  # read_catalog -> grouped command -> final response
    assert not any(name == "approval" for name, _ in events)
    for book_id in book_ids:
        current = store.list_book_entries(book_id)
        assert current[0]["visible_to"] == []
        assert {key: current[0][key] for key in ("name", "content", "keywords", "extensions")} == {
            key: before[book_id][0][key] for key in ("name", "content", "keywords", "extensions")}
    snapshot = api.assistant_agent_session("owner", grant["session_id"])
    result = snapshot["receipts"][0]["result"]
    assert result["status"] == "completed"
    assert [row["status"] for row in result["books"]] == ["succeeded"] * 3


@pytest.mark.asyncio
async def test_public_twenty_book_selection_has_one_approval_and_one_replayable_receipt(web_api):
    api, store, *_ = web_api
    book_ids = [f"batch-public-{index:02}" for index in range(20)]
    _books(store, book_ids)
    planner = _group_planner(book_ids, "public")
    grant = api.assistant_agent_authorize("owner", "", "task", {}, ["lorebook"], 64)

    events = await _run(api, planner, session_id=grant["session_id"],
                        prompt="Publish all selected lorebooks")

    plan = _pending(events)
    assert plan["preview"]["book_count"] == 20
    assert len([name for name, _ in events if name == "approval"]) == 1
    assert all(store.list_book_entries(book_id)[0]["visible_to"] == [] for book_id in book_ids)
    sid = _session_id(events)
    result = await api.assistant_agent_confirm("owner", sid, plan["approval_id"], plan["plan_digest"], True)
    replay = await api.assistant_agent_confirm("owner", sid, plan["approval_id"], plan["plan_digest"], True)

    assert result == replay
    assert result["result"]["status"] == "completed"
    assert result["result"]["success_count"] == 20
    assert all(store.list_book_entries(book_id)[0]["visible_to"] == ["*"] for book_id in book_ids)


@pytest.mark.asyncio
async def test_discarding_partial_plan_keeps_completed_and_failed_target_report(web_api, monkeypatch):
    api, store, *_ = web_api
    ids = ['discard-a', 'discard-b']
    _books(store, ids)
    events = await _run(api, _group_planner(ids, 'public'))
    sid, plan = _session_id(events), _pending(events)
    real_update = store.update_book_entry
    def fail_second(book_id, entry_id, patch):
        return False if book_id == 'discard-b' else real_update(book_id, entry_id, patch)
    monkeypatch.setattr(store, 'update_book_entry', fail_second)
    partial = await api.assistant_agent_confirm('owner', sid, plan['approval_id'], plan['plan_digest'], True)
    assert partial['result']['success_count'] == 1
    cancelled = await api.assistant_agent_confirm('owner', sid, plan['approval_id'], plan['plan_digest'], False)
    assert cancelled['cancelled'] and cancelled['result']['status'] == 'cancelled'
    assert cancelled['result']['success_count'] == 1 and cancelled['result']['failed_count'] == 1
    snapshot = api.assistant_agent_session('owner', sid)
    assert snapshot['pending'] is None
    assert snapshot['receipts'][-1]['result'] == cancelled['result']
    assert store.list_book_entries('discard-a')[0]['visible_to'] == ['*']
    assert store.list_book_entries('discard-b')[0]['visible_to'] == []


@pytest.mark.asyncio
async def test_public_alias_cannot_hide_private_marker_validation_in_entry_writer(web_api):
    api, store, *_ = web_api
    _books(store, ['alias'], visible_to=['Public'])
    grant = api.assistant_agent_authorize('owner', '', 'task', {}, [], 8)
    planner = Planner({'tool': 'write_lorebook_entries', 'arguments': {'book_id': 'alias', 'entries': [{
        'id': 'alias-entry-0', 'name': 'Secret', 'content': 'GM: private detail'}]}},
        {'tool': 'respond', 'answer': 'Cannot publish this'})
    before = store.list_book_entries('alias')
    events = await _run(api, planner, session_id=grant['session_id'])
    assert store.list_book_entries('alias') == before
    assert not any(name == 'approval' for name, _ in events)


@pytest.mark.asyncio
@pytest.mark.parametrize('tool_name', ['set_lorebook_entry_visibility', 'write_lorebook_entries'])
async def test_repeated_entry_calls_cannot_publish_a_hidden_book_under_task_grant(web_api, tool_name):
    api, store, *_ = web_api
    _books(store, ['split'])
    for index in (1, 2):
        store.add_book_entry('split', _entry('split', index))
    before = store.list_book_entries('split')
    for index in range(3):
        identity = f'split-entry-{index}'
        arguments = {'book_id': 'split'}
        if tool_name == 'set_lorebook_entry_visibility':
            arguments.update(entry_ids=[identity], audience='public')
        else:
            arguments['entries'] = [{'id': identity, 'name': f'Entry {index}',
                                     'content': f'Authored content for split {index}', 'visibility': 'public'}]
        grant = api.assistant_agent_authorize('owner', '', 'task', {}, [], 8)
        events = await _run(api, Planner({'tool': tool_name, 'arguments': arguments}), session_id=grant['session_id'])
        plan = _pending(events)
        assert plan['assessment']['requires_approval']
        await api.assistant_agent_confirm('owner', grant['session_id'], plan['approval_id'], plan['plan_digest'], False)
        assert store.list_book_entries('split') == before


@pytest.mark.asyncio
async def test_task_scope_cannot_auto_execute_a_gm_batch_outside_the_book_grant(web_api):
    api, store, *_ = web_api
    book_ids = ["scope-in", "scope-out"]
    _books(store, book_ids, visible_to=["*"])
    planner = _group_planner(book_ids, "gm")
    grant = api.assistant_agent_authorize("owner", "", "task", {"book_id": "scope-in"}, ["lorebook"], 8)

    events = await _run(api, planner, session_id=grant["session_id"])

    assert _pending(events)["tool"] == "set_lorebooks_visibility"
    assert all(store.list_book_entries(book_id)[0]["visible_to"] == ["*"] for book_id in book_ids)


@pytest.mark.asyncio
async def test_entry_public_expansion_and_public_write_with_private_marker_stop_before_writes(web_api):
    api, store, *_ = web_api
    store.create_lorebook({"id": "entry-public", "name": "Entry", "source_kind": "user"})
    store.add_book_entry("entry-public", _entry("entry-public", content="GM: secret clue"))
    grant = api.assistant_agent_authorize("owner", "", "task", {"book_id": "entry-public"},
                                          ["lorebook"], 8)
    planner = Planner(
        {"tool": "set_lorebook_entry_visibility", "arguments": {
            "book_id": "entry-public", "entry_ids": ["entry-public-entry-0"], "audience": "public"}},
    )
    before = store.list_book_entries("entry-public")
    events = await _run(api, planner, session_id=grant["session_id"],
                        prompt="Publish this entry")
    assert _pending(events)["tool"] == "set_lorebook_entry_visibility"
    assert store.list_book_entries("entry-public") == before

    planner = Planner(
        {"tool": "write_lorebook_entries", "arguments": {"book_id": "entry-public", "entries": [{
            "id": "entry-public-entry-0", "name": "Entry", "content": "GM: secret clue",
            "visibility": "public"}]}},
        {"tool": "respond", "answer": "The private marker blocked publication."},
    )
    events = await _run(api, planner, session_id="", prompt="Rewrite and publish this entry")
    assert not any(name == "approval" for name, _ in events)
    assert store.list_book_entries("entry-public") == before


@pytest.mark.asyncio
async def test_gm_batch_noop_rejects_no_change_and_replay_is_stable(web_api):
    api, store, *_ = web_api
    book_ids = ["noop-a", "noop-b", "noop-c"]
    _books(store, book_ids, visible_to=[])
    before = {book_id: store.list_book_entries(book_id) for book_id in book_ids}
    planner = _group_planner(book_ids, "gm")
    grant = api.assistant_agent_authorize("owner", "", "task", {}, ["lorebook"], 8)

    events = await _run(api, planner, session_id=grant["session_id"], prompt="Keep all books GM-only")

    assert not any(name == "approval" for name, _ in events)
    snapshot = api.assistant_agent_session("owner", grant["session_id"])
    result = snapshot["receipts"][0]["result"]
    assert result["status"] == "completed" and result["changed_count"] == 0
    assert all(row["operation_ids"] == [] for row in result["books"])
    assert api.assistant_content_operations("owner")["operations"] == []
    assert {book_id: store.list_book_entries(book_id) for book_id in book_ids} == before


@pytest.mark.asyncio
async def test_visibility_confirmation_rejects_wrong_owner_digest_and_stale_new_entry(web_api):
    api, store, *_ = web_api
    _books(store, ["stale-book"])
    planner = _group_planner(["stale-book"], "public")
    grant = api.assistant_agent_authorize("owner", "", "task", {}, ["lorebook"], 8)
    events = await _run(api, planner, session_id=grant["session_id"], prompt="Publish the book")
    plan = _pending(events)
    sid = _session_id(events)
    with pytest.raises(PermissionError):
        await api.assistant_agent_confirm("other-owner", sid, plan["approval_id"], plan["plan_digest"], True)
    with pytest.raises(ValueError, match="stale|integrity|changed|Approval"):
        await api.assistant_agent_confirm("owner", sid, plan["approval_id"], "sha256:stale", True)
    store.add_book_entry("stale-book", _entry("stale-book", 1))
    with pytest.raises(ValueError, match="changed|plan"):
        await api.assistant_agent_confirm("owner", sid, plan["approval_id"], plan["plan_digest"], True)
    assert store.list_book_entries("stale-book")[0]["visible_to"] == []


@pytest.mark.asyncio
async def test_second_book_sqlite_failure_reports_failed_and_not_executed_then_resume_skips_first(web_api, monkeypatch):
    api, store, *_ = web_api
    book_ids = ["failure-a", "failure-b", "failure-c"]
    _books(store, book_ids, visible_to=["*"])
    real_update = store.update_book_entry

    def fail_second(book_id, entry_id, patch):
        if book_id == "failure-b":
            raise ValueError("injected second-book failure")
        return real_update(book_id, entry_id, patch)

    monkeypatch.setattr(store, "update_book_entry", fail_second)
    planner = _group_planner(book_ids, "gm")
    grant = api.assistant_agent_authorize("owner", "", "task", {}, ["lorebook"], 8)
    events = await _run(api, planner, session_id=grant["session_id"])
    sid = _session_id(events)
    pending = api.assistant_agent_session("owner", sid)["pending"]
    report = pending["execution_state"]["report"]
    assert report["status"] == "partial"
    assert [row["status"] for row in report["books"]] == ["succeeded", "failed", "not_executed"]
    assert store.list_book_entries("failure-a")[0]["visible_to"] == []
    assert store.list_book_entries("failure-b")[0]["visible_to"] == ["*"]
    assert store.list_book_entries("failure-c")[0]["visible_to"] == ["*"]

    monkeypatch.setattr(store, "update_book_entry", real_update)
    resumed = await api.assistant_agent_resume("owner", sid, pending["approval_id"], pending["plan_digest"])

    assert resumed["result"]["status"] == "completed"
    assert all(store.list_book_entries(book_id)[0]["visible_to"] == [] for book_id in book_ids)


@pytest.mark.asyncio
async def test_cancel_between_books_preserves_first_receipt_and_resume_finishes_remaining(web_api, monkeypatch):
    api, store, *_ = web_api
    book_ids = ["cancel-a", "cancel-b", "cancel-c"]
    _books(store, book_ids, visible_to=["*"])
    captured = {}
    real_update = store.update_book_entry
    cancelled = False

    def cancel_after_first(book_id, entry_id, patch):
        nonlocal cancelled
        result = real_update(book_id, entry_id, patch)
        if book_id == "cancel-a" and not cancelled:
            cancelled = True
            api.assistant_agent_cancel("owner", captured["session_id"])
        return result

    monkeypatch.setattr(store, "update_book_entry", cancel_after_first)
    planner = _group_planner(book_ids, "gm")

    async def emit(name, value):
        if name == "session":
            captured["session_id"] = value["session_id"]

    api._llm_client.call_tools = planner.call_tools
    await api.assistant_agent_run("owner", [{"role": "user", "content": "GM-only all books"}],
                                  "en", {"route": "library"}, "", emit)
    pending = api.assistant_agent_session("owner", captured["session_id"])["pending"]
    result = await api.assistant_agent_confirm("owner", captured["session_id"],
                                               pending["approval_id"], pending["plan_digest"], True)
    pending = result["pending"]
    assert pending and pending["execution_status"] == "cancelled", pending
    assert store.list_book_entries("cancel-a")[0]["visible_to"] == []
    assert store.list_book_entries("cancel-b")[0]["visible_to"] == ["*"]

    monkeypatch.setattr(store, "update_book_entry", real_update)
    resumed = await api.assistant_agent_resume("owner", captured["session_id"],
                                               pending["approval_id"], pending["plan_digest"])
    assert resumed["result"]["status"] == "completed"
    assert all(store.list_book_entries(book_id)[0]["visible_to"] == [] for book_id in book_ids)


@pytest.mark.asyncio
async def test_restarted_runtime_reconciles_owner_receipt_before_finishing_batch(web_api):
    api, store, *_ = web_api
    book_ids = ["restart-a", "restart-b"]
    _books(store, book_ids, visible_to=["*"])
    old_runtime = api._assistant_agent
    registry = old_runtime.registry
    action = registry.get("set_lorebooks_visibility")
    original_execute = action.execute
    crashed = False

    class ProcessInterrupted(BaseException):
        pass

    async def crash_after_first_receipt(payload, owner, context):
        nonlocal crashed
        real_checkpoint = context.checkpoint

        def checkpoint(state):
            nonlocal crashed
            real_checkpoint(state)
            if (not crashed
                    and state.get("books", {}).get("restart-a", {}).get("status") == "succeeded"):
                crashed = True
                raise ProcessInterrupted("simulated process restart")

        context.checkpoint = checkpoint
        return await original_execute(payload, owner, context)

    wrapped = replace(action, execute=crash_after_first_receipt)
    registry.unregister(action.name)
    registry.register(wrapped)
    planner = _group_planner(book_ids, "gm")
    grant = api.assistant_agent_authorize("owner", "", "task", {}, ["lorebook"], 8)
    sid = grant["session_id"]
    with pytest.raises(ProcessInterrupted):
        await _run(api, planner, session_id=sid)

    pending = old_runtime.snapshot("owner", sid)["pending"]
    assert pending and pending["execution_state"]["books"]["restart-a"]["status"] == "succeeded"
    assert pending["execution_state"]["report"]["status"] != "completed"
    assert pending["execution_state"]["report"]["success_count"] == 1
    assert pending["execution_state"]["report"]["not_executed_count"] == 1
    assert len(api.assistant_content_operations("owner")["operations"]) == 1

    registry.unregister(action.name)
    registry.register(action)
    restarted = AgentRuntime(replace(old_runtime.deps, tools=()))
    api._assistant_agent = restarted
    recovered = restarted.snapshot("owner", sid)
    assert recovered["status"] == "paused"
    assert recovered["pending"]["execution_state"]["report"]["status"] == "partial"
    assert recovered["pending"]["execution_state"]["report"]["success_count"] == 1
    assert recovered["pending"]["execution_state"]["report"]["not_executed_count"] == 1
    resumed = await api.assistant_agent_resume("owner", sid, pending["approval_id"], pending["plan_digest"])

    assert resumed["result"]["status"] == "completed"
    assert all(store.list_book_entries(book_id)[0]["visible_to"] == [] for book_id in book_ids)
    assert len(api.assistant_content_operations("owner")["operations"]) == 2
