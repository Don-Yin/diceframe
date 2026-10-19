from __future__ import annotations

from copy import deepcopy

import pytest

from src.webui.services.content_metadata_recovery import (
    MetadataRecoveryDependencies,
    MetadataRecoveryService,
)


class Store:
    def __init__(self):
        self.rows = {}

    def record_lorebook_operation(self, operation):
        self.rows[operation["id"]] = deepcopy(operation)

    def get_lorebook_operation(self, operation_id, owner):
        row = self.rows.get(operation_id)
        return deepcopy(row) if row and row["owner"] == owner else None

    def update_lorebook_operation(self, operation_id, owner, changes):
        row = self.rows.get(operation_id)
        if not row or row["owner"] != owner:
            return False
        row.update(deepcopy(changes))
        return True


@pytest.fixture
def harness():
    store = Store()
    world = {"name": "Old", "description": "Before", "language": "en", "version": "v1", "untouched": "keep"}
    card = {"character_name": "Ada", "background": "Before", "race": "human", "class": "wizard", "version": "v1", "untouched": "keep"}
    writes = []

    def world_snapshot(_):
        return {"target_name": world["name"], "fields": {key: world[key] for key in ("name", "description", "language")}, "version": world["version"]}

    def card_snapshot(_):
        return {"target_name": card["character_name"], "fields": {key: card[key] for key in ("character_name", "background", "race", "class")}, "version": card["version"]}

    def world_update(_, patch):
        writes.append(("world", patch))
        world.update(patch)
        world["version"] = f"v{len(writes) + 1}"
        return {"ok": True}

    def card_update(_, patch):
        writes.append(("card", patch))
        card.update(patch)
        card["version"] = f"v{len(writes) + 1}"
        return {"ok": True}

    service = MetadataRecoveryService(MetadataRecoveryDependencies(
        store, world_snapshot, world_update, card_snapshot, card_update,
    ))
    return service, store, world, card, writes


def test_owner_private_world_undo_preserves_untouched_fields(harness):
    service, _store, world, _card, _writes = harness
    result = service.write_world("owner", "world-1", {"description": "Agent edit"})
    assert result["reversible"] is True
    service.undo("owner", result["operation_id"])
    assert world["description"] == "Before"
    assert world["untouched"] == "keep"
    with pytest.raises(ValueError):
        service.undo("owner", result["operation_id"])


def test_owner_isolation_and_later_same_value_write_conflict(harness):
    service, _store, world, _card, _writes = harness
    result = service.write_world("owner", "world-1", {"description": "Agent edit"})
    with pytest.raises(ValueError):
        service.recovery_preview("other", result["operation_id"])
    world["version"] = "later-same-value"
    world["description"] = "Agent edit"
    with pytest.raises(ValueError):
        service.undo("owner", result["operation_id"])


def test_snapshot_record_failure_prevents_writer(harness, monkeypatch):
    service, store, _world, _card, writes = harness
    monkeypatch.setattr(store, "record_lorebook_operation", lambda _: (_ for _ in ()).throw(OSError("journal")))
    with pytest.raises(OSError):
        service.write_card("owner", "card-1", {"background": "edit"})
    assert writes == []


def test_writer_and_finalization_failure_leave_prepared_and_cannot_undo(harness, monkeypatch):
    service, store, world, _card, writes = harness
    def fail_writer(_, patch):
        writes.append(("world", patch))
        world.update(patch)
        world["version"] = "writer-wrote"
        raise OSError("uncertain")
    service.deps = MetadataRecoveryDependencies(store, service.deps.world_snapshot, fail_writer, service.deps.card_snapshot, service.deps.card_update)
    with pytest.raises(OSError):
        service.write_world("owner", "world-1", {"description": "edit"})
    operation = next(iter(store.rows.values()))
    assert operation["status"] == "prepared"
    with pytest.raises(ValueError):
        service.undo("owner", operation["id"])


def test_finalization_failure_does_not_claim_applied(harness, monkeypatch):
    service, store, _world, _card, _writes = harness
    original = store.update_lorebook_operation
    def fail_finalization(operation_id, owner, changes):
        if changes.get("status") == "applied":
            raise OSError("journal finalization")
        return original(operation_id, owner, changes)
    monkeypatch.setattr(store, "update_lorebook_operation", fail_finalization)
    with pytest.raises(OSError):
        service.write_card("owner", "card-1", {"background": "edit"})
    assert next(iter(store.rows.values()))["status"] == "prepared"
