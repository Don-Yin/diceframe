from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.engine.module_state import ModuleStateError
from src.engine.modules import content_binding


def test_content_binding_keeps_source_aware_refs_detached() -> None:
    instance = SimpleNamespace(modules={})
    content_binding.set_world_ref(instance, {
        "source_kind": "world", "source_id": "ashen", "kind": "world", "id": "ashen",
    })
    content_binding.add_book_ref(instance, {
        "source_kind": "module", "source_id": "ruins", "kind": "lorebook", "id": "ruins-book",
    })

    world = content_binding.world_ref(instance)
    books = content_binding.book_refs(instance)
    world["id"] = "changed"
    books[0]["id"] = "changed"

    assert content_binding.world_ref(instance)["id"] == "ashen"
    assert content_binding.book_refs(instance)[0]["id"] == "ruins-book"
    assert set(instance.modules["content_binding"]) == {"schema_version", "world_ref", "book_refs"}


@pytest.mark.parametrize("method, ref", [
    (content_binding.set_world_ref, {"kind": "lorebook", "id": "book"}),
    (content_binding.add_book_ref, {"kind": "world", "id": "world"}),
])
def test_content_binding_rejects_wrong_kind(method, ref) -> None:
    instance = SimpleNamespace(modules={})
    with pytest.raises(ValueError):
        method(instance, ref)


@pytest.mark.parametrize("raw", [None, [], "corrupt", {"schema_version": 1, "book_refs": None}])
def test_preflight_does_not_repair_slot(raw) -> None:
    instance = SimpleNamespace(modules={"content_binding": deepcopy(raw)})
    content_binding.require_writable(instance)
    assert instance.modules == {"content_binding": raw}


def test_preflight_does_not_materialize_missing_slot() -> None:
    instance = SimpleNamespace(modules={})
    content_binding.require_writable(instance)
    assert instance.modules == {}


@pytest.mark.parametrize("method, ref", [
    (content_binding.set_world_ref, {"kind": "world", "id": "ashen"}),
    (content_binding.add_book_ref, {"kind": "lorebook", "id": "book"}),
])
@pytest.mark.parametrize("schema", [99, None, "1"])
def test_writers_reject_unknown_schema_without_mutation(method, ref, schema) -> None:
    slot = {"schema_version": schema, "world_ref": {}, "book_refs": []}
    instance = SimpleNamespace(modules={"content_binding": deepcopy(slot), "other": {"x": 1}})
    with pytest.raises(ModuleStateError, match="unsupported content_binding module schema"):
        method(instance, ref)
    assert instance.modules == {"content_binding": slot, "other": {"x": 1}}


def test_ensure_drops_the_unreleased_adventure_refs_key() -> None:
    raw = {"schema_version": 1, "world_ref": {}, "book_refs": [], "adventure_refs": [{"id": "intro"}]}
    assert content_binding.ensure(raw) == {"schema_version": 1, "world_ref": {}, "book_refs": []}


def test_module_has_no_adventure_writer() -> None:
    assert not hasattr(content_binding, "add_adventure_ref")
    assert not hasattr(content_binding, "adventure_refs")


# ---- v35 -> v36 save migration ---------------------------------------------

from src.engine.game_instance import GameInstance  # noqa: E402
from src.migrations.instance import (  # noqa: E402
    CURRENT_INSTANCE_SCHEMA_VERSION,
    _migrate_v35_to_v36,
    migrate_game_state_payload,
)


def test_v34_save_gets_a_world_ref_slot_without_mutating_input() -> None:
    original = {"instance_schema_version": 34, "world_id": "ashen", "modules": {"economy": {"x": 1}}}
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert original == before
    assert migrated["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert migrated["modules"]["content_binding"] == {
        "schema_version": 1,
        "world_ref": {"source_kind": "world", "source_id": "ashen", "kind": "world", "id": "ashen", "digest": ""},
        "book_refs": [],
    }
    assert migrated["modules"]["economy"] == {"x": 1}
    assert migrate_game_state_payload(migrated) == migrated


def test_migration_never_overwrites_an_existing_slot() -> None:
    slot = {"schema_version": 1, "world_ref": {"source_kind": "module", "source_id": "pack",
            "kind": "world", "id": "ashen", "digest": "sha256:x"}, "book_refs": [{"id": "b"}]}
    future = {"schema_version": 7, "anything": True}
    for existing in (slot, future):
        payload = {"instance_schema_version": 35, "world_id": "ashen", "modules": {"content_binding": deepcopy(existing)}}
        assert _migrate_v35_to_v36(payload)["modules"]["content_binding"] == existing


@pytest.mark.parametrize("modules", [None, [], "corrupt"])
def test_migration_tolerates_non_dict_modules(modules) -> None:
    migrated = _migrate_v35_to_v36({"instance_schema_version": 35, "world_id": "ashen", "modules": modules})
    assert migrated["modules"]["content_binding"]["world_ref"]["id"] == "ashen"
    assert migrated["instance_schema_version"] == 36


@pytest.mark.parametrize("world_id", ["", None, "bad id with spaces/and:colons"])
def test_migration_leaves_world_ref_empty_without_a_valid_world_id(world_id) -> None:
    migrated = _migrate_v35_to_v36({"instance_schema_version": 35, "world_id": world_id, "modules": {}})
    assert migrated["modules"]["content_binding"] == {"schema_version": 1, "world_ref": {}, "book_refs": []}


def test_migrated_save_loads_and_round_trips() -> None:
    saved = GameInstance(game_key=("t", "cb", "bot"), world_id="ashen").to_dict()
    saved["instance_schema_version"] = 34
    saved["modules"].pop("content_binding", None)
    migrated = migrate_game_state_payload(saved)
    instance = GameInstance.from_dict(migrated)
    assert content_binding.world_ref(instance)["id"] == "ashen"
    assert instance.to_dict()["modules"]["content_binding"] == migrated["modules"]["content_binding"]
