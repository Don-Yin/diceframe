import pytest
from pathlib import Path

from src.webui.services.assistant_agent import validate_arguments
from src.webui.services.assistant_library_tools import LibraryToolCallbacks, build_library_actions, build_library_tools
from src.lorebook.store import LorebookStore
from src.webui.services.lorebooks import LorebookDependencies, commit_lorebook_plan, export_lorebook, preview_lorebook_import


@pytest.mark.asyncio
async def test_lorebook_export_metadata_roundtrip_and_strict_ids():
    books = {"book-1": {"id": "book-1", "name": "Canon", "entries": [{"uid": "e1", "content": "rumor"}]}}
    tools = {tool.name: tool for tool in build_library_tools(LibraryToolCallbacks(
        list_lorebooks=lambda: list(books.values()),
        export_lorebook=lambda book_id: {"ok": True, "format": "native", "book": books[book_id]},
        update_lorebook=lambda book_id, changes: {"ok": True, "book": {**books[book_id], **changes}},
    ))}
    listed = await tools["list_lorebooks"].handler({}, "owner")
    exported = await tools["export_lorebook"].handler({"book_id": "book-1"}, "owner")
    assert listed["books"][0]["name"] == "Canon"
    assert exported["book"]["entries"][0]["content"] == "rumor"
    with pytest.raises(KeyError):
        await tools["export_lorebook"].handler({"book_id": "foreign"}, "owner")


@pytest.mark.asyncio
async def test_real_lorebook_store_native_preview_commit_roundtrip(tmp_path: Path):
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    store.create_lorebook({"id": "book-real", "name": "Real Book"})
    store.add_book_entry("book-real", {"id": "e1", "name": "Rumor", "content": "harbor", "keywords": ["harbor"]})
    deps = LorebookDependencies(store, lambda key: None, lambda: None)
    actions = {item.name: item for item in build_library_actions(LibraryToolCallbacks(
        export_lorebook=lambda identity: export_lorebook(deps, identity),
        preview_lorebook_import=lambda payload: preview_lorebook_import(deps, payload),
        commit_lorebook_plan=lambda body: commit_lorebook_plan(deps, body),
    ))}
    exported = await actions['export_lorebook'].handler({'book_id': 'book-real'}, 'owner')
    assert exported["ok"] is True and exported["data"]["lorebook"]["entries"][0]["content"] == "harbor"
    preview = await actions['preview_lorebook_import'].handler({'payload': exported}, 'owner')
    assert preview["plan"]["plan_digest"].startswith("sha256:")
    args = {"payload": exported, "plan_digest": preview["plan"]["plan_digest"], "decision": "create"}
    assert actions['commit_lorebook_import'].guard(args, 'owner') == args['plan_digest']
    with pytest.raises(ValueError, match='stale'):
        actions['commit_lorebook_import'].guard({**args, 'plan_digest': 'sha256:invented'}, 'owner')
    committed = await actions['commit_lorebook_import'].handler(args, 'owner')
    assert committed["ok"] is True
    assert store.list_book_entries(committed["book_id"])[0]["content"] == "harbor"
    store.close()


@pytest.mark.asyncio
async def test_import_commit_requires_server_plan_digest_and_propagates_stale_error():
    seen = []
    callbacks = LibraryToolCallbacks(
        preview_lorebook_import=lambda payload: {"ok": True, "plan_digest": "sha256:server", "payload": payload},
        commit_lorebook_plan=lambda body: seen.append(body) or {"ok": False, "error_code": "PLAN_STALE", "error": "stale"},
    )
    tools = {tool.name: tool for tool in build_library_tools(callbacks)}
    validate_arguments({"payload": {"name": "Book"}}, tools["preview_lorebook_import"].schema)
    with pytest.raises(ValueError, match="stale"):
        await tools["commit_lorebook_import"].handler({"payload": {"name": "Book"}, "plan_digest": "sha256:invented", "decision": "create"}, "owner")
    assert seen[0]["plan_digest"] == "sha256:invented"


@pytest.mark.asyncio
async def test_metadata_update_exposes_owner_snapshot_guard():
    current = {"id": "book-1", "revision": 1, "name": "Before"}
    tools = {tool.name: tool for tool in build_library_tools(LibraryToolCallbacks(
        read_lorebook=lambda book_id: current,
        update_lorebook=lambda book_id, changes: {"ok": True, "book": {**current, **changes}},
    ))}
    action = tools["update_lorebook_metadata"]
    args = {"book_id": "book-1", "changes": {"name": "After"}}
    first = action.guard(args, "owner")
    current["revision"] = 2
    assert action.guard(args, "owner") != first


@pytest.mark.asyncio
async def test_builtin_source_protection_is_delegated_to_world_owner():
    calls = []
    tools = {tool.name: tool for tool in build_library_tools(LibraryToolCallbacks(
        clone_world=lambda template_id, name: calls.append((template_id, name)) or {"ok": False, "error": "内置世界不可修改，请先克隆"},
    ))}
    with pytest.raises(ValueError, match="内置世界"):
        await tools["clone_world_from_template"].handler({"template_id": "builtin:core", "name": "Copy"}, "owner")
    assert calls == [("builtin:core", "Copy")]


def test_actions_have_domain_and_effect_metadata():
    callbacks = LibraryToolCallbacks(
        clone_world=lambda *_: {"ok": True},
        update_lorebook=lambda *_: {"ok": True},
        read_lorebook=lambda _: {"id": "book", "revision": 1},
        preview_lorebook_import=lambda _: {"ok": True},
        commit_lorebook_plan=lambda _: {"ok": True},
        guard=lambda operation, args: "sha256:stable",
    )
    actions = {action.name: action for action in build_library_actions(callbacks)}
    assert actions["clone_world_from_template"].domain == "worlds"
    assert actions["clone_world_from_template"].effect == "write"
    assert actions["update_lorebook_metadata"].effect == "write"
    assert actions["commit_lorebook_import"].effect == "disclosure"
