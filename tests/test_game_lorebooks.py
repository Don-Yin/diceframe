from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.engine.modules import content_binding
from src.engine.game_state import GameState
from src.lorebook.resolver import resolve_active_books
from src.lorebook.store import LorebookStore
from src.webui.services.game_lorebooks import (
    GameLorebookDependencies,
    GameLorebookService,
)


def _instance(key: str = "web|room|bot", *, gm: str = "gm") -> SimpleNamespace:
    return SimpleNamespace(
        game_key=tuple(key.split("|")), game_id="legacy-room", run_id="run-1",
        round_number=3, world_id="world-1", world_name="World One", gm_uid=gm,
        players={"char-1": {}}, action_actor_uids=["char-1"], modules={"content_binding": content_binding.fresh()},
    )


def _book(store: LorebookStore, book_id: str, *, enabled: bool = True, name: str | None = None):
    store.create_lorebook({"id": book_id, "name": name or book_id, "enabled": enabled})


def _deps(store, games, saved=None):
    def books():
        rows = []
        for book in store.list_lorebooks():
            rows.append({
                **book,
                "entry_count": len(store.list_book_entries(book["id"])),
                "ref": {
                    "source_kind": "user", "source_id": book["id"],
                    "kind": "lorebook", "id": book["id"], "digest": "",
                },
            })
        return {"books": rows}

    async def save(instance):
        if saved is not None:
            saved.append(instance.to_dict() if hasattr(instance, "to_dict") else instance)

    return GameLorebookDependencies(store, games.get, books, save)


@pytest.fixture()
def store(tmp_path: Path):
    value = LorebookStore(tmp_path / "lorebook.db")
    value.open()
    try:
        yield value
    finally:
        value.close()


def test_carried_game_materializes_its_explicit_refs_without_changing_source_bindings(store):
    from copy import deepcopy
    _book(store, 'selected')
    source = _instance()
    candidate = _instance('web|next|bot')
    content_binding.replace_book_refs(candidate, [{
        'source_kind': 'user', 'source_id': 'selected', 'kind': 'lorebook', 'id': 'selected', 'digest': '',
    }])
    content_binding.select_books_explicitly(candidate)
    store.bind_lorebook({'id': 'source-binding', 'book_id': 'selected', 'scope_kind': 'game', 'scope_id': 'web|room|bot'})
    before = deepcopy(store.list_bindings())
    service = GameLorebookService(_deps(store, {}))
    service.bind_carried_game(candidate)
    service.bind_carried_game(candidate)
    resolved = resolve_active_books(candidate, viewer_kind='gm', viewer_uid='', action_actor_uids=[], store=store)
    assert [ref.book_id for ref in resolved] == ['selected']
    assert [row for row in store.list_bindings() if row['id'] == 'source-binding'] == before
    assert len(store.list_bindings()) == 2


def test_auto_selection_marks_character_books_locked_and_is_read_only(store):
    _book(store, "global-book")
    _book(store, "world-book")
    _book(store, "char-book")
    store.bind_lorebook({"id": "bg", "book_id": "global-book", "scope_kind": "global", "scope_id": ""})
    store.bind_lorebook({"id": "bw", "book_id": "world-book", "scope_kind": "world", "scope_id": "world-1"})
    store.bind_lorebook({"id": "bc", "book_id": "char-book", "scope_kind": "character", "scope_id": "char-1"})
    instance = _instance()
    before = instance.modules.copy()
    service = GameLorebookService(_deps(store, {"web|room|bot": instance}))

    result = service.selection("web|room|bot", "gm")

    expected = {
        "ok": True, "game_key": "web|room|bot", "world_id": "world-1", "world_name": "World One",
        "mode": "auto", "max_books": 16,
        "books": [
            {"id": "global-book", "name": "global-book", "enabled": True, "entry_count": 0, "selected": True, "locked": False},
            {"id": "world-book", "name": "world-book", "enabled": True, "entry_count": 0, "selected": True, "locked": False},
            {"id": "char-book", "name": "char-book", "enabled": True, "entry_count": 0, "selected": True, "locked": True},
        ],
    }
    # The catalogue orders by updated_at, which may change between fixture
    # inserts. This contract protects membership and locks, not insertion order.
    assert {**result, 'books': sorted(result['books'], key=lambda row: row['id'])} == {
        **expected, 'books': sorted(expected['books'], key=lambda row: row['id']),
    }
    assert instance.modules == before


@pytest.mark.asyncio
async def test_apply_replaces_only_this_game_bindings_and_preserves_character_sources(store):
    _book(store, "one")
    _book(store, "two")
    _book(store, "char-book")
    store.bind_lorebook({"id": "old", "book_id": "one", "scope_kind": "game", "scope_id": "web|room|bot", "role": "runtime"})
    store.bind_lorebook({"id": "legacy", "book_id": "one", "scope_kind": "game", "scope_id": "legacy-room", "role": "runtime"})
    store.bind_lorebook({"id": "char", "book_id": "char-book", "scope_kind": "character", "scope_id": "char-1", "role": "character"})
    instance = _instance()
    games = {"web|room|bot": instance}
    service = GameLorebookService(_deps(store, games))

    result = await service.apply("web|room|bot", ["two"], "gm")

    assert result["ok"] is True
    state = instance.modules["content_binding"]
    assert state["book_selection"] == "explicit"
    assert [ref["id"] for ref in state["book_refs"]] == ["two"]
    game_rows = [b for b in store.list_bindings() if b["scope_kind"] == "game"]
    assert {(b["scope_id"], b["book_id"]) for b in game_rows} == {("web|room|bot", "two")}
    assert any(b["scope_kind"] == "character" and b["book_id"] == "char-book" for b in store.list_bindings())
    assert {ref.book_id for ref in resolve_active_books(instance, action_actor_uids=instance.action_actor_uids, store=store)} == {"two", "char-book"}
    operations = store.list_lorebook_operations(GameLorebookService._owner_id("gm"))
    assert operations and operations[0]["kind"] == "game_lorebooks"
    assert operations[0]["status"] == "applied" and operations[0]["payload"]["phase"] == "applied"


@pytest.mark.asyncio
async def test_apply_rejects_disabled_missing_locked_and_non_gm_without_mutation(store):
    _book(store, "disabled", enabled=False)
    _book(store, "char-book")
    store.bind_lorebook({"id": "char", "book_id": "char-book", "scope_kind": "character", "scope_id": "char-1"})
    instance = _instance()
    service = GameLorebookService(_deps(store, {"web|room|bot": instance}))

    with pytest.raises(PermissionError):
        service.selection("web|room|bot", "player")
    with pytest.raises(ValueError):
        await service.apply("web|room|bot", ["disabled"], "gm")
    with pytest.raises(ValueError):
        await service.apply("web|room|bot", ["missing"], "gm")
    with pytest.raises(ValueError):
        await service.apply("web|room|bot", ["char-book"], "gm")
    assert store.list_bindings(scope_kind="game", scope_id="web|room|bot") == []


@pytest.mark.asyncio
async def test_preview_and_guard_are_metadata_only_and_games_are_isolated(store):
    _book(store, "one")
    _book(store, "two")
    first, second = _instance("web|one|bot"), _instance("web|two|bot")
    games = {"web|one|bot": first, "web|two|bot": second}
    service = GameLorebookService(_deps(store, games))
    before = (first.modules.copy(), second.modules.copy(), store.list_bindings())

    preview = service.preview("web|one|bot", ["one"], "gm")
    digest = service.guard("web|one|bot", ["one"], "gm")

    assert preview["target_name"] == "World One"
    assert preview["books"] == [{"id": "one", "name": "one"}]
    assert preview["target_count"] == 1
    assert preview["affected_games"] == ["web|one|bot"]
    assert digest.startswith("sha256:") and len(digest) == 71
    assert first.modules == before[0] and second.modules == before[1] and store.list_bindings() == before[2]


@pytest.mark.asyncio
async def test_save_failure_compensates_and_concurrent_writes_are_serialized(store):
    _book(store, "one")
    _book(store, "two")
    instance = _instance()
    calls = 0
    entered = asyncio.Event()
    release = asyncio.Event()

    async def save(_instance):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
            raise RuntimeError("save failed")

    deps = _deps(store, {"web|room|bot": instance})
    deps = GameLorebookDependencies(deps.store, deps.get_game, deps.list_books, save)
    service = GameLorebookService(deps)
    first = asyncio.create_task(service.apply("web|room|bot", ["one"], "gm"))
    assert await asyncio.wait_for(entered.wait(), 1)
    second = asyncio.create_task(service.apply("web|room|bot", ["two"], "gm"))
    await asyncio.sleep(0)
    assert not second.done()
    release.set()
    failed = await first
    assert failed["ok"] is False
    assert await second
    assert {row["book_id"] for row in store.list_bindings(scope_kind="game", scope_id="web|room|bot")} == {"two"}


def test_authenticated_owner_can_manage_game_but_player_cannot(store):
    _book(store, "one")
    instance = _instance(gm="different-gm")
    service = GameLorebookService(_deps(store, {"web|room|bot": instance}))

    assert service.selection("web|room|bot", "owner", owner_authenticated=True)["ok"] is True
    with pytest.raises(PermissionError):
        service.selection("web|room|bot", "player")


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [GameState.CREATED, GameState.ACTIVE_JUDGMENT])
async def test_preview_and_apply_reject_unsafe_game_phase(store, state):
    _book(store, "one")
    instance = _instance()
    instance.state = state
    service = GameLorebookService(_deps(store, {"web|room|bot": instance}))

    with pytest.raises(ValueError):
        service.preview("web|room|bot", ["one"], "gm")
    with pytest.raises(ValueError):
        await service.apply("web|room|bot", ["one"], "gm")


def test_round_processing_in_flight_is_rejected(store):
    _book(store, "one")
    instance = _instance()
    instance.round_processing_in_flight = lambda: True
    service = GameLorebookService(_deps(store, {"web|room|bot": instance}))
    with pytest.raises(ValueError):
        service.preview("web|room|bot", ["one"], "gm")


@pytest.mark.parametrize('modules', [[], {'content_binding': {'schema_version': True, 'book_refs': []}}])
def test_malformed_module_container_or_boolean_schema_is_not_treated_as_legacy(store, modules):
    _book(store, 'one')
    instance = _instance()
    instance.modules = modules
    service = GameLorebookService(_deps(store, {'web|room|bot': instance}))
    with pytest.raises(ValueError):
        service.selection('web|room|bot', 'gm')


def test_catalog_without_canonical_ref_fails_closed(store):
    _book(store, "one")
    instance = _instance()
    deps = GameLorebookDependencies(
        store, {"web|room|bot": instance}.get,
        lambda: {"books": [{"id": "one", "name": "one", "enabled": True}]},
        _deps(store, {"web|room|bot": instance}).save_instance,
    )
    service = GameLorebookService(deps)
    with pytest.raises(ValueError, match="missing ref"):
        service.selection("web|room|bot", "gm")


@pytest.mark.parametrize(
    "slot",
    [
        {"schema_version": 999, "book_refs": []},
        {"schema_version": content_binding.SCHEMA_VERSION, "book_refs": "bad"},
        {"schema_version": content_binding.SCHEMA_VERSION, "book_refs": [{"kind": "world", "id": "not-a-book"}]},
    ],
)
def test_unknown_or_bad_content_binding_fails_closed_without_overwrite(store, slot):
    _book(store, "one")
    instance = _instance()
    instance.modules = {"content_binding": slot}
    service = GameLorebookService(_deps(store, {"web|room|bot": instance}))
    before = instance.modules.copy()
    with pytest.raises(ValueError):
        service.selection("web|room|bot", "gm")
    assert instance.modules == before


@pytest.mark.asyncio
async def test_missing_content_module_stays_absent_when_prepared_journal_fails(store, monkeypatch):
    _book(store, "one")
    instance = _instance()
    instance.modules = {}
    service = GameLorebookService(_deps(store, {"web|room|bot": instance}))

    def fail_record(_operation):
        raise RuntimeError("journal unavailable")

    monkeypatch.setattr(store, "record_lorebook_operation", fail_record)
    with pytest.raises(RuntimeError, match="journal unavailable"):
        await service.apply("web|room|bot", ["one"], "gm")
    assert instance.modules == {}


@pytest.mark.asyncio
async def test_state_or_actor_change_during_save_requires_recovery_without_replay(store):
    _book(store, "one")
    instance = _instance()
    started = asyncio.Event()
    release = asyncio.Event()

    async def save(_instance):
        instance.state = GameState.ACTIVE_JUDGMENT
        instance.action_actor_uids.append("char-2")
        started.set()
        await release.wait()

    deps = _deps(store, {"web|room|bot": instance})
    service = GameLorebookService(GameLorebookDependencies(deps.store, deps.get_game, deps.list_books, save))
    task = asyncio.create_task(service.apply("web|room|bot", ["one"], "gm"))
    assert await asyncio.wait_for(started.wait(), 1)
    release.set()
    result = await task
    assert result["ok"] is False and result["recovery_required"] is True
    assert instance.state == GameState.ACTIVE_JUDGMENT
    assert store.list_bindings(scope_kind="game", scope_id="web|room|bot")


def test_guard_changes_when_canonical_reference_changes(store):
    _book(store, "one")
    instance = _instance()
    ref = {"source_kind": "user", "source_id": "one", "kind": "lorebook", "id": "one", "digest": "a"}
    rows = [{"id": "one", "name": "one", "enabled": True, "entry_count": 0, "ref": ref}]
    deps = GameLorebookDependencies(store, {"web|room|bot": instance}.get, lambda: {"books": rows}, _deps(store, {"web|room|bot": instance}).save_instance)
    service = GameLorebookService(deps)
    first = service.guard("web|room|bot", ["one"], "gm")
    rows[0]["ref"] = {**ref, "digest": "b"}
    assert service.guard("web|room|bot", ["one"], "gm") != first


@pytest.mark.asyncio
async def test_expected_guard_is_checked_after_waiting_for_game_lock(store):
    _book(store, "one")
    _book(store, "two")
    instance = _instance()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def save(_instance):
        entered.set()
        await release.wait()

    deps = _deps(store, {"web|room|bot": instance})
    service = GameLorebookService(GameLorebookDependencies(deps.store, deps.get_game, deps.list_books, save))
    approved = service.guard("web|room|bot", ["two"], "gm")
    first = asyncio.create_task(service.apply("web|room|bot", ["one"], "gm"))
    assert await asyncio.wait_for(entered.wait(), 1)
    stale_task = asyncio.create_task(service.apply("web|room|bot", ["two"], "gm", expected_guard=approved))
    release.set()
    assert (await first)["ok"] is True
    stale = await stale_task
    assert stale["ok"] is False and stale["error_code"] == "STALE_GUARD"


@pytest.mark.asyncio
async def test_manual_binding_change_during_save_requires_recovery(store):
    _book(store, "one")
    instance = _instance()
    started = asyncio.Event()
    release = asyncio.Event()

    async def save(_instance):
        store.bind_lorebook({"id": "manual", "book_id": "one", "scope_kind": "game", "scope_id": "web|room|bot", "role": "manual"})
        started.set()
        await release.wait()

    deps = _deps(store, {"web|room|bot": instance})
    service = GameLorebookService(GameLorebookDependencies(deps.store, deps.get_game, deps.list_books, save))
    task = asyncio.create_task(service.apply("web|room|bot", ["one"], "gm"))
    assert await asyncio.wait_for(started.wait(), 1)
    release.set()
    result = await task
    assert result["ok"] is False and result["recovery_required"] is True
    assert any(row["role"] == "manual" for row in store.list_bindings(scope_kind="game", scope_id="web|room|bot"))


@pytest.mark.asyncio
async def test_uncertain_compensation_is_marked_for_recovery_and_survives_restart(store, tmp_path):
    _book(store, "one")
    instance = _instance()
    calls = 0

    async def save(_instance):
        nonlocal calls
        calls += 1
        raise RuntimeError("save failed")

    deps = _deps(store, {"web|room|bot": instance})
    service = GameLorebookService(GameLorebookDependencies(deps.store, deps.get_game, deps.list_books, save))
    result = await service.apply("web|room|bot", ["one"], "gm")
    assert result["ok"] is False and result["recovery_required"] is True
    owner_id = service._owner_id("gm")
    rows = store.list_lorebook_operations(owner_id)
    assert rows and rows[0]["kind"] == "game_lorebooks"
    assert rows[0]["status"] == "prepared" and rows[0]["payload"]["phase"] == "uncertain"

    path = store.db_path
    store.close()
    reopened = LorebookStore(path)
    reopened.open()
    try:
        persisted = reopened.list_lorebook_operations(owner_id)
        assert persisted and persisted[0]["status"] == "prepared"
    finally:
        reopened.close()
