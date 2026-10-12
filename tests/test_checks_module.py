"""Checks slot migration, identity, codec and reset contracts."""

from copy import deepcopy
from dataclasses import fields
from types import SimpleNamespace

import pytest

from src.engine.game_instance import GameInstance
from src.engine.module_state import ModuleStateError
from src.engine.modules import checks as module
from src.migrations.instance import (
    CURRENT_INSTANCE_SCHEMA_VERSION,
    _migrate_v30_to_v31,
    migrate_game_state_payload,
)

VALUES = {
    "last_check": {"check_id": "latest", "roll": 12},
    "last_checks": [{"check_id": "latest", "roll": 12}],
    "round_checks_prepared": True,
    "manual_roll_requests": [{"id": "manual", "status": "pending"}],
}


def new_instance(**kwargs):
    return GameInstance(game_key=("test", "checks", "bot"), **kwargs)


def read_field(instance, key):
    return getattr(module, key)(instance)


def write_field(instance, key, value):
    getattr(module, f"replace_{key}")(instance, value)


def test_migration_moves_fields_without_mutating_input_and_is_idempotent():
    original = {"instance_schema_version": 30, **deepcopy(VALUES), "opaque": {"items": [1]}}
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert original == before
    assert migrated["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert migrated["modules"][module.MODULE_NAME] == {"schema_version": 1, **VALUES}
    assert not VALUES.keys() & migrated.keys()
    assert migrate_game_state_payload(migrated) == migrated
    step = _migrate_v30_to_v31(deepcopy(original))
    assert _migrate_v30_to_v31(deepcopy(step)) == step
    migrated["modules"][module.MODULE_NAME]["last_check"]["roll"] = 20
    assert original == before


@pytest.mark.parametrize("slot", [{}, {"schema_version": 1, **VALUES}, {"schema_version": 99, "opaque": [1]}])
def test_existing_slot_wins(slot):
    original = {"instance_schema_version": 30, **VALUES, "modules": {module.MODULE_NAME: slot}}
    before = deepcopy(original)
    migrated = migrate_game_state_payload(original)
    assert migrated["modules"][module.MODULE_NAME] == slot
    assert not VALUES.keys() & migrated.keys()
    assert original == before


@pytest.mark.parametrize("key,value,expected", [
    ("last_check", [], None), ("last_check", "bad", None), ("last_check", None, None),
    ("last_checks", None, []), ("last_checks", {}, []),
    ("manual_roll_requests", None, []), ("manual_roll_requests", "bad", []),
    ("round_checks_prepared", "yes", True), ("round_checks_prepared", [], False),
    ("round_checks_prepared", 1, True), ("round_checks_prepared", None, False),
])
def test_invalid_fields_normalize_identically_in_migration_and_ensure(key, value, expected):
    values = {**deepcopy(VALUES), key: value}
    wanted = {"schema_version": 1, **values, key: expected}
    raw = {"schema_version": 1, **values}
    assert module.ensure(raw) is raw
    assert raw == wanted
    migrated = migrate_game_state_payload({"instance_schema_version": 30, **values})
    assert migrated["modules"][module.MODULE_NAME] == wanted


@pytest.mark.parametrize("raw", [None, [], 12, "bad"])
def test_missing_or_malformed_slot_materializes_defaults(raw):
    instance = new_instance(modules={module.MODULE_NAME: raw})
    assert instance.modules[module.MODULE_NAME] == module.fresh()
    assert module.ensure(raw) == module.fresh()
    assert module.ensure({"schema_version": 1}) == module.fresh()
    migrated = migrate_game_state_payload({"instance_schema_version": 30, "modules": raw})
    assert migrated["modules"][module.MODULE_NAME] == module.fresh()


def test_ensure_preserves_valid_objects_and_does_not_filter_list_elements():
    raw = {"schema_version": 1, **deepcopy(VALUES)}
    raw["last_checks"].extend([None, 4, "opaque"])
    raw["manual_roll_requests"].extend([None, "opaque"])
    objects = dict(raw)
    assert module.ensure(raw) is raw
    assert all(raw[key] is value for key, value in objects.items())
    instance = GameInstance.from_dict({"game_key": ["test", "checks", "bot"], "state": "waiting",
                                       "instance_schema_version": 30,
                                       **{key: raw[key] for key in VALUES}})
    assert module.last_checks(instance) == raw["last_checks"]
    assert module.manual_roll_requests(instance) == raw["manual_roll_requests"]


def test_future_instance_version_is_rejected():
    with pytest.raises(ValueError, match="unsupported game instance schema"):
        GameInstance.from_dict({"instance_schema_version": CURRENT_INSTANCE_SCHEMA_VERSION + 1})


def test_unknown_module_version_is_preserved_and_access_fails_closed():
    raw = {"schema_version": 99, "opaque": [1]}
    assert module.ensure(raw) is raw
    instance = new_instance(modules={module.MODULE_NAME: raw})
    before = deepcopy(instance.modules)
    for key, value in VALUES.items():
        with pytest.raises(ModuleStateError):
            read_field(instance, key)
        with pytest.raises(ModuleStateError):
            write_field(instance, key, value)
    assert instance.modules == before
    encoded = instance.to_dict()
    assert encoded["modules"][module.MODULE_NAME] == raw
    restored = GameInstance.from_dict(encoded)
    assert restored.modules[module.MODULE_NAME] == raw


def test_game_instance_has_no_checks_facades():
    instance = new_instance()
    for key in VALUES:
        assert not hasattr(GameInstance, key)
        assert not hasattr(instance, key)


def test_module_accessors_use_live_slot_and_roundtrip_has_one_storage_owner():
    instance = new_instance()
    other = new_instance()
    slot = instance.modules[module.MODULE_NAME]
    assert slot is not other.modules[module.MODULE_NAME]
    assert slot["last_checks"] is not module.last_checks(other)
    assert slot["manual_roll_requests"] is not module.manual_roll_requests(other)
    assert not VALUES.keys() & {item.name for item in fields(instance)}
    assert not VALUES.keys() & vars(instance).keys()
    for key, value in deepcopy(VALUES).items():
        write_field(instance, key, value)
        assert slot[key] is value
        assert read_field(instance, key) is slot[key]
    module.last_checks(instance).append({"check_id": "in-place"})
    module.manual_roll_requests(instance)[0]["status"] = "cancelled"
    encoded = instance.to_dict()
    assert not VALUES.keys() & encoded.keys()
    restored = GameInstance.from_dict(deepcopy(encoded))
    assert restored.modules[module.MODULE_NAME] == slot
    instance.replace_persisted_state_from(restored)
    assert instance.modules[module.MODULE_NAME] == slot


@pytest.mark.parametrize("prepared", [False, True])
def test_clear_round_preserves_manual_rolls_and_list_identity(prepared):
    instance = new_instance()
    for key, value in deepcopy(VALUES).items():
        write_field(instance, key, value)
    requests, records = module.manual_roll_requests(instance), module.last_checks(instance)
    module.clear_round(instance, prepared=prepared)
    assert module.last_check(instance) is None
    assert module.last_checks(instance) is records
    assert records == []
    assert module.round_checks_prepared(instance) is prepared
    assert module.manual_roll_requests(instance) is requests
    assert requests == VALUES["manual_roll_requests"]


@pytest.mark.asyncio
async def test_reset_preserves_manual_roll_requests_implicitly():
    instance = new_instance()
    for key, value in deepcopy(VALUES).items():
        write_field(instance, key, value)
    requests = module.manual_roll_requests(instance)
    await instance.reset()
    assert instance.modules[module.MODULE_NAME] == {**module.fresh(), "manual_roll_requests": requests}
    assert module.manual_roll_requests(instance) is requests
    assert requests == VALUES["manual_roll_requests"]


def test_record_sync_and_preparation_preserve_aliasing_contract():
    instance = new_instance()
    check = {"check_id": "record", "roll": 12}
    instance.record_check(check)
    assert module.last_check(instance) is module.last_checks(instance)[-1] is check
    instance.sync_last_check(check)
    assert module.last_check(instance) == check
    assert module.last_check(instance) is not check
    check["roll"] = 20
    assert module.last_check(instance)["roll"] == 12
    instance.complete_round_check_preparation()
    assert module.last_check(instance) is check
    assert module.round_checks_prepared(instance) is True
    module.invalidate_prepared(instance)
    assert module.round_checks_prepared(instance) is False


def test_mark_prepared_with_empty_list_preserves_last_check():
    instance = new_instance()
    module.replace_last_check(instance, {"check_id": "previous"})
    previous = module.last_check(instance)
    instance.complete_round_check_preparation()
    assert module.last_check(instance) is previous
    assert module.round_checks_prepared(instance) is True


def test_legacy_null_lists_keep_codec_defaults():
    instance = GameInstance.from_dict({
        "instance_schema_version": 30, "game_key": ["test", "checks", "bot"], "state": "waiting",
        "last_checks": None, "manual_roll_requests": None, "round_checks_prepared": "truthy",
    })
    assert module.last_checks(instance) == []
    assert module.manual_roll_requests(instance) == []
    assert module.round_checks_prepared(instance) is True


def test_manual_roll_append_writes_module_slot_on_non_aggregate_doubles():
    instance = SimpleNamespace(modules={})
    request = {"id": "manual"}
    module.add_manual_roll_request(instance, request)
    assert module.manual_roll_requests(instance)[-1] is request
    assert instance.modules[module.MODULE_NAME]["manual_roll_requests"] == [request]
    assert not hasattr(instance, "manual_roll_requests")
