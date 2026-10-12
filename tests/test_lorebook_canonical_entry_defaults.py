"""§9 — canonical 新条目默认值。

施工单要求：canonical 新建 entry 的默认值为
``priority=100``、``order=100``、``prompt_slot=world_background``、
``vector_activation=hybrid``；legacy adapter 默认值不变。

默认值只在 create 生效：update 必须能把字段清空而不被默认值顶回来。
"""

from __future__ import annotations

from src.lorebook.activation import DEFAULT_VECTOR_ACTIVATION
from src.lorebook.store import LorebookStore


def _store(tmp_path):
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    store.create_lorebook({"id": "book:canon", "name": "Canon"})
    return store


def test_new_canonical_entry_gets_canonical_defaults(tmp_path):
    store = _store(tmp_path)
    try:
        from src.webui.api import CANONICAL_ENTRY_DEFAULTS, WebAPI

        # 只调用真正 owning 的 create 边界，不手搓 payload 默认值。
        api = WebAPI.__new__(WebAPI)
        api._lore = store
        result = api.save_lorebook_entry("book:canon", {
            "name": "Fresh", "content": "body", "keywords": ["k"],
        })

        assert result["ok"] is True
        entry = result["entry"]
        assert entry["priority"] == 100
        assert entry["order"] == 100
        assert entry["prompt_slot"] == "world_background"
        assert entry["vector_activation"] == DEFAULT_VECTOR_ACTIVATION == "hybrid"
        assert CANONICAL_ENTRY_DEFAULTS == {
            "priority": 100, "order": 100,
            "prompt_slot": "world_background", "vector_activation": "hybrid",
        }
    finally:
        store.close()


def test_explicit_values_are_never_overridden_by_defaults(tmp_path):
    store = _store(tmp_path)
    try:
        from src.webui.api import WebAPI

        api = WebAPI.__new__(WebAPI)
        api._lore = store
        result = api.save_lorebook_entry("book:canon", {
            "name": "Explicit", "content": "body",
            "priority": 7, "order": 3,
            "prompt_slot": "scene_context", "vector_activation": "off",
        })
        entry = result["entry"]
        assert entry["priority"] == 7
        assert entry["order"] == 3
        assert entry["prompt_slot"] == "scene_context"
        assert entry["vector_activation"] == "off"
    finally:
        store.close()


def test_update_can_clear_a_field_without_default_snapback(tmp_path):
    """create 之后的 update 清空 prompt_slot，不该被默认值顶回 world_background。"""

    store = _store(tmp_path)
    try:
        from src.webui.api import WebAPI

        api = WebAPI.__new__(WebAPI)
        api._lore = store
        created = api.save_lorebook_entry("book:canon", {"name": "E", "content": "b"})
        entry_id = created["entry"]["id"]
        assert created["entry"]["prompt_slot"] == "world_background"

        updated = api.save_lorebook_entry("book:canon", {
            "id": entry_id, "name": "E", "content": "b", "prompt_slot": "",
        })
        assert updated["ok"] is True
        assert updated["entry"]["prompt_slot"] == ""
    finally:
        store.close()


def test_legacy_adapter_draft_defaults_are_unchanged(tmp_path):
    """legacy adapter 的 draft 默认值不受 §9 影响。"""

    from src.lorebook.domain import LoreEntryDraft

    draft = LoreEntryDraft()
    assert draft.priority == 0
    assert draft.insertion_order == 100
    assert draft.prompt_slot == ""
