from __future__ import annotations

import json
from pathlib import Path

from src.lorebook.bootstrap import seed_builtin_worlds
from src.lorebook.store import LorebookStore


ROOT = Path(__file__).resolve().parents[1]


def test_freeform_sandbox_is_blank_and_legacy_tavern_is_hidden():
    sandbox = json.loads((ROOT / "templates/worlds/freeform_sandbox.json").read_text(encoding="utf-8"))
    legacy = json.loads((ROOT / "templates/worlds/tavern_generic.json").read_text(encoding="utf-8"))

    assert sandbox["sandbox"] is True
    assert sandbox["world_setting"] == ""
    assert sandbox["starter_scene"] == ""
    assert sandbox["starter_lorebook"] == []
    assert sandbox["default_rule"] == "tavern_free"
    assert legacy["deprecated"] is True


def test_deprecated_world_is_not_seeded(tmp_path: Path):
    (tmp_path / "legacy.json").write_text(json.dumps({
        "world_id": "legacy",
        "deprecated": True,
        "starter_lorebook": [{"id": "entry", "name": "Old"}],
    }), encoding="utf-8")

    class Store:
        def get_world(self, world_id):
            return None

        def create_world(self, *args, **kwargs):
            raise AssertionError("deprecated templates must not be seeded")

    assert seed_builtin_worlds(Store(), tmp_path) == 0


def test_blank_builtin_world_is_registered_with_empty_primary_book(tmp_path: Path):
    worlds_dir = tmp_path / "worlds"
    worlds_dir.mkdir()
    source = ROOT / "templates/worlds/freeform_sandbox.json"
    (worlds_dir / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    store = LorebookStore(tmp_path / "lorebook.db")
    store.open()
    try:
        assert seed_builtin_worlds(store, worlds_dir) == 0

        world = store.get_world("freeform_sandbox")
        primary = store.get_lorebook("world:freeform_sandbox")
        bindings = store.list_bindings(scope_id="freeform_sandbox")

        assert world is not None
        assert world["name"] == "自由沙盒"
        assert primary is not None
        assert primary["id"] == "world:freeform_sandbox"
        assert primary["revision"] == 0
        assert [entry for entry in store.list_entries("freeform_sandbox")] == []
        assert bindings == [{
            "id": "binding:world:freeform_sandbox:primary",
            "book_id": "world:freeform_sandbox",
            "scope_kind": "world",
            "scope_id": "freeform_sandbox",
            "role": "primary",
            "enabled": True,
            "order": 100,
            "created_at": bindings[0]["created_at"],
            "updated_at": bindings[0]["updated_at"],
        }]
    finally:
        store.close()


def test_blank_builtin_repeat_seed_preserves_user_books_entries_and_metadata(tmp_path: Path):
    worlds_dir = tmp_path / "worlds"
    worlds_dir.mkdir()
    source = ROOT / "templates/worlds/freeform_sandbox.json"
    (worlds_dir / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    store = LorebookStore(tmp_path / "lorebook.db")
    store.open()
    try:
        seed_builtin_worlds(store, worlds_dir)
        world_id = "freeform_sandbox"
        primary_id = store.primary_world_book_id(world_id)
        store.update_world_metadata(
            world_id, name="用户沙盒", description="用户描述", language="zh-CN",
        )
        store.update_lorebook(
            primary_id,
            {"token_budget": 321, "settings_json": {"locale": "en", "mode": "strict"}},
        )
        store.add_entry({
            "id": "authored-locale-mechanics",
            "world_id": world_id,
            "book_id": primary_id,
            "name": "用户条目",
            "type": "location",
            "keywords": ["custom-key"],
            "content": "用户保留内容",
            "tier": "core",
            "visible_to": ["*"],
            "match_mode": "all",
            "scan_depth": 4,
        })
        store.create_lorebook({
            "id": "custom-book",
            "name": "额外世界书",
            "description": "自定义绑定",
            "language": "en",
            "settings": {"locale": "en"},
        })
        store.bind_lorebook({
            "id": "binding:custom-book:freeform",
            "book_id": "custom-book",
            "scope_kind": "world",
            "scope_id": world_id,
            "role": "custom",
        })
        store.add_entry({
            "id": "custom-book-entry",
            "book_id": "custom-book",
            "world_id": world_id,
            "name": "额外条目",
            "type": "npc",
            "keywords": ["locale-key"],
            "content": "额外书内容",
            "tier": "background",
            "visible_to": [],
            "match_mode": "any",
        })

        before_world = store.get_world(world_id)
        before_primary = store.get_lorebook(primary_id)
        before_primary_entries = store.list_book_entries(primary_id)
        before_custom = store.get_lorebook("custom-book")
        before_custom_entries = store.list_book_entries("custom-book")
        before_bindings = store.list_bindings(scope_id=world_id)

        assert seed_builtin_worlds(store, worlds_dir) == 0

        assert store.get_world(world_id) == before_world
        assert store.get_lorebook(primary_id) == before_primary
        assert store.list_book_entries(primary_id) == before_primary_entries
        assert store.get_lorebook("custom-book") == before_custom
        assert store.list_book_entries("custom-book") == before_custom_entries
        assert store.list_bindings(scope_id=world_id) == before_bindings
        assert [entry["id"] for entry in store.list_entries(world_id)] == [
            "authored-locale-mechanics",
        ]
    finally:
        store.close()
