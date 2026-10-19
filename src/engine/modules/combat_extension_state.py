"""Generic combat-extension storage and its per-round snapshots.

Services interpret the inner ``current`` payload.  The per-round snapshot
logic (capture / current / restore / discard) lives here; the core round flow
reaches it only through ``module_hooks`` (round recovery preflight, abort,
rewind begin / restore, commit, instance reset), so without this module rounds
roll back players, entities and the world but carry no combat-extension state.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from src.engine import module_hooks
from src.engine.module_state import ModuleStateSpec, get_module_state, register_module_state

MODULE_NAME = "combat_extension"
SCHEMA_VERSION = 1


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "current": {}, "round_snapshots": {}}


def ensure(raw: Any) -> dict[str, Any]:
    """Repair only supported-slot containers, retaining live dict identities.

    Legacy snapshot key/record normalization belongs solely to v19 -> v20.
    Unknown outer schemas and all inner contents remain opaque here.
    """

    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    for key in ("current", "round_snapshots"):
        if not isinstance(raw.get(key), dict):
            raw[key] = {}
    return raw


def current(instance: Any) -> dict[str, Any]:
    """Return the live current payload, rejecting unsupported slot schemas."""

    return get_module_state(instance, MODULE_NAME)["current"]


def replace_current(instance: Any, value: Any) -> None:
    """Keep assigned dicts (even empty ones) by identity; repair other inputs."""

    get_module_state(instance, MODULE_NAME)["current"] = value if isinstance(value, dict) else {}


def round_snapshots(instance: Any) -> dict[str, Any]:
    """Return the live map without interpreting snapshot envelopes."""

    return get_module_state(instance, MODULE_NAME)["round_snapshots"]


def replace_round_snapshots(instance: Any, value: Any) -> None:
    get_module_state(instance, MODULE_NAME)["round_snapshots"] = value if isinstance(value, dict) else {}


def reset(instance: Any) -> None:
    """Match lifecycle reset: replace current, clear the existing snapshot map.

    Validate the slot first so unknown schemas cannot be partially reset.
    Preserve outer extras, sibling modules, and references to old current data.
    """

    slot = get_module_state(instance, MODULE_NAME)
    slot["current"] = {}
    slot["round_snapshots"].clear()


# ---------- per-round snapshots (moved from round_snapshots, #515) ----------


def _current_round(instance: Any) -> int:
    from src.engine import progression

    return progression.current_round(instance)


def capture_combat_extension_snapshot(
    instance: Any,
    entity_fields: Mapping[str, tuple[str, ...]] | None = None,
) -> None:
    """Capture state and source fields before this round's combat writes.

    The extension payload alone is insufficient because HP, declared
    special stats, and consumable inventory live on character/NPC records.
    Later actions may engage new entities, so their fields are merged into
    the same pre-mutation snapshot when first touched.
    """

    try:
        key = str(_current_round(instance))
    except (TypeError, ValueError):
        key = "0"
    if not isinstance(round_snapshots(instance), dict):
        replace_round_snapshots(instance, {})
    snapshot = round_snapshots(instance).get(key)
    if not isinstance(snapshot, dict):
        snapshot = None
    elif "combat_extension" not in snapshot:
        # Older in-memory snapshots stored the raw extension payload.
        # Wrap it before adding source-field tracking so that a legacy
        # branch remains restorable without exposing malformed containers.
        snapshot = {
            "schema_version": 1,
            "combat_extension": copy.deepcopy(snapshot),
            "entity_fields": {},
        }
        round_snapshots(instance)[key] = snapshot
    elif (
        isinstance(snapshot.get("schema_version"), bool)
        or snapshot.get("schema_version") != 1
        or not isinstance(snapshot.get("combat_extension"), dict)
    ):
        snapshot = None
    if snapshot is None:
        snapshot = {
            "schema_version": 1,
            "combat_extension": copy.deepcopy(
                current(instance) if isinstance(current(instance), dict) else {}
            ),
            "entity_fields": {},
        }
        round_snapshots(instance)[key] = snapshot
    snapshot = round_snapshots(instance)[key]
    if isinstance(entity_fields, Mapping) and isinstance(snapshot, dict):
        captured = snapshot.setdefault("entity_fields", {})
        if not isinstance(captured, dict):
            captured = {}
            snapshot["entity_fields"] = captured
        for entity_id, raw_fields in entity_fields.items():
            if (
                not isinstance(entity_id, str)
                or not entity_id
                or not isinstance(raw_fields, (tuple, list, set, frozenset))
            ):
                continue
            fields = tuple(dict.fromkeys(
                field_name
                for field_name in raw_fields
                if isinstance(field_name, str) and field_name
            ))
            if not fields:
                continue
            source: Mapping[str, Any] | None = None
            if entity_id.startswith("player:"):
                uid = entity_id.removeprefix("player:")
                if uid in instance.players:
                    raw_sheet = instance.get_character_sheet(uid)
                    if isinstance(raw_sheet, Mapping):
                        source = raw_sheet
            elif entity_id.startswith("npc:"):
                npc = instance.npcs.get(entity_id.removeprefix("npc:"))
                if isinstance(npc, Mapping):
                    source = npc
            if source is None:
                continue
            entry = captured.get(entity_id)
            if not isinstance(entry, dict):
                entry = {"values": {}, "missing": []}
                captured[entity_id] = entry
            values = entry.get("values")
            if not isinstance(values, dict):
                values = {}
                entry["values"] = values
            missing = entry.get("missing")
            if not isinstance(missing, list):
                missing = []
                entry["missing"] = missing
            missing[:] = [
                field_name
                for field_name in missing
                if isinstance(field_name, str)
                and field_name
                and field_name not in values
            ]
            for field_name in fields:
                if field_name in values or field_name in missing:
                    continue
                if field_name in source:
                    values[field_name] = copy.deepcopy(source[field_name])
                else:
                    missing.append(field_name)
    # Save size stays bounded even in very long sessions. Finished-round
    # logs carry their own copy, so only recent/current snapshots are needed.
    if len(round_snapshots(instance)) > 100:
        def _sort_key(value: str) -> tuple[int, str]:
            try:
                return int(value), value
            except (TypeError, ValueError):
                return -1, value
        for old_key in sorted(round_snapshots(instance), key=_sort_key)[:-100]:
            round_snapshots(instance).pop(old_key, None)


def current_combat_extension_snapshot(instance: Any) -> dict[str, Any]:
    """Return the current combat state using this round's tracked fields."""

    try:
        key = str(_current_round(instance))
    except (TypeError, ValueError):
        key = "0"
    if not isinstance(round_snapshots(instance), dict):
        replace_round_snapshots(instance, {})
    tracked = round_snapshots(instance).get(key, {})
    raw_fields = tracked.get("entity_fields") if isinstance(tracked, dict) else {}
    entity_fields: dict[str, tuple[str, ...]] = {}
    if isinstance(raw_fields, dict):
        for entity_id, entry in raw_fields.items():
            if not isinstance(entry, dict):
                continue
            values = entry.get("values")
            absent = entry.get("missing")
            if (
                not isinstance(entity_id, str)
                or not entity_id
                or not isinstance(values, dict)
                or not isinstance(absent, list)
                or any(not isinstance(name, str) or not name for name in values)
                or any(not isinstance(name, str) or not name for name in absent)
                or len(set(absent)) != len(absent)
                or set(values).intersection(absent)
            ):
                continue
            entity_fields[entity_id] = tuple((*values.keys(), *absent))

    extension_state = copy.deepcopy(
        current(instance) if isinstance(current(instance), dict) else {}
    )
    extension_state.pop("pending_summaries", None)
    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "combat_extension": extension_state,
        "entity_fields": {},
    }
    for entity_id, fields in entity_fields.items():
        source: Mapping[str, Any] | None = None
        if entity_id.startswith("player:"):
            uid = entity_id.removeprefix("player:")
            if uid in instance.players:
                raw_sheet = instance.get_character_sheet(uid)
                if isinstance(raw_sheet, Mapping):
                    source = raw_sheet
        elif entity_id.startswith("npc:"):
            npc = instance.npcs.get(entity_id.removeprefix("npc:"))
            if isinstance(npc, Mapping):
                source = npc
        if source is None:
            continue
        values = {
            field_name: copy.deepcopy(source[field_name])
            for field_name in fields if field_name in source
        }
        snapshot["entity_fields"][entity_id] = {
            "values": values,
            "missing": [field_name for field_name in fields if field_name not in source],
        }
    return snapshot


def restore_combat_extension_snapshot(instance: Any, snapshot: Any) -> bool:
    """Restore a snapshot produced by the combat-extension snapshot API."""

    if not isinstance(snapshot, dict):
        return False
    if "combat_extension" not in snapshot:
        # Compatibility with the short-lived raw-payload snapshot shape.
        try:
            restored_extension = copy.deepcopy(snapshot)
        except (TypeError, ValueError, RecursionError):
            return False
        replace_current(instance, restored_extension)
        return True
    version = snapshot.get("schema_version")
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version != 1
        or not isinstance(snapshot.get("combat_extension"), dict)
    ):
        return False
    entity_fields = snapshot.get("entity_fields")
    if entity_fields is None:
        entity_fields = {}
    if not isinstance(entity_fields, dict):
        return False
    staged: list[tuple[dict[str, Any], dict[str, Any], list[str]]] = []
    for entity_id, entry in entity_fields.items():
        if not isinstance(entity_id, str) or not isinstance(entry, dict):
            return False
        target: dict[str, Any] | None = None
        if entity_id.startswith("player:"):
            uid = entity_id.removeprefix("player:")
            if uid in instance.players:
                raw_sheet = instance.get_character_sheet(uid)
                if isinstance(raw_sheet, dict):
                    target = raw_sheet
        elif entity_id.startswith("npc:"):
            npc = instance.npcs.get(entity_id.removeprefix("npc:"))
            if isinstance(npc, dict):
                target = npc
        if target is None:
            continue
        values = entry.get("values")
        absent = entry.get("missing")
        if (
            not isinstance(values, dict)
            or not isinstance(absent, list)
            or any(not isinstance(field_name, str) or not field_name for field_name in values)
            or any(not isinstance(field_name, str) or not field_name for field_name in absent)
            or len(set(absent)) != len(absent)
            or set(values).intersection(absent)
        ):
            return False
        if target is None:
            continue
        try:
            copied_values = {
                field_name: copy.deepcopy(value)
                for field_name, value in values.items()
            }
        except (TypeError, ValueError, RecursionError):
            return False
        staged.append((target, copied_values, list(absent)))
    try:
        restored_extension = copy.deepcopy(snapshot["combat_extension"])
    except (TypeError, ValueError, RecursionError):
        return False
    replace_current(instance, restored_extension)
    for target, values, absent in staged:
        target.update(values)
        for field_name in absent:
            target.pop(field_name, None)
    return True


def discard_combat_extension_snapshots_from(instance: Any, round_number: int) -> None:
    """Drop live snapshots belonging to a discarded history branch."""

    if not isinstance(round_snapshots(instance), dict):
        replace_round_snapshots(instance, {})
        return
    for key in list(round_snapshots(instance)):
        try:
            snapshot_round = int(key)
        except (TypeError, ValueError):
            # Malformed keys cannot be associated with the retained branch.
            round_snapshots(instance).pop(key, None)
            continue
        if snapshot_round >= round_number:
            round_snapshots(instance).pop(key, None)


SPEC = ModuleStateSpec(name=MODULE_NAME, schema_version=SCHEMA_VERSION, fresh=fresh, ensure=ensure)
register_module_state(SPEC)


# ---------- lifecycle hooks (#515) ----------------------------------------


def _restore_or_clear(instance: Any, snapshot: Any) -> None:
    if not restore_combat_extension_snapshot(instance, snapshot):
        replace_current(instance, {})


def _live_round_snapshot(instance: Any, round_key: Any, default: Any = None) -> Any:
    return round_snapshots(instance).get(str(round_key), default)


def preflight(instance: Any) -> None:
    current(instance)


def abort_round(instance: Any) -> bool:
    from src.engine.modules import progression_state

    snapshot = _live_round_snapshot(instance, progression_state.round_value(instance))
    if not isinstance(snapshot, dict):
        return False
    _restore_or_clear(instance, snapshot)
    return True


def rewind_begin(instance: Any, target_round: int) -> None:
    from src.engine.modules import progression_state

    round_value = progression_state.round_value(instance)
    snapshot = _live_round_snapshot(instance, round_value)
    if round_value >= target_round and isinstance(snapshot, dict):
        _restore_or_clear(instance, snapshot)


def rewind_restore(instance: Any, entry: Mapping[str, Any], target_round: int, source: str) -> None:
    # Combat actions run during ACTIVE_ACTION, before the ordinary round
    # snapshot is captured at judgment entry, so this source-field snapshot is
    # restored after the players: HP / inventory are not overwritten by the
    # later round_start_snapshot.
    if source == module_hooks.REWIND_SOURCE_ROLLBACK:
        missing = object()
        snapshot: Any = entry.get("combat_extension_round_start", missing)
        if snapshot is missing:
            snapshot = _live_round_snapshot(instance, target_round, missing)
        if snapshot is not missing:
            _restore_or_clear(instance, snapshot)
    elif source == module_hooks.REWIND_SOURCE_SWIPE:
        snapshot = entry.get("pre_combat_extension_snapshot")
        if isinstance(snapshot, dict):
            _restore_or_clear(instance, snapshot)
    discard_combat_extension_snapshots_from(instance, target_round)


def commit_round(instance: Any, entry: dict[str, Any], pre_snapshot: Any) -> None:
    from src.engine.modules import progression_state

    payload = current(instance)
    raw_schema = payload.get("schema_version") if isinstance(payload, dict) else None
    if isinstance(payload, dict) and (
        raw_schema is None
        or (isinstance(raw_schema, int) and not isinstance(raw_schema, bool) and raw_schema == 1)
    ):
        raw_pending = payload.pop("pending_summaries", [])
        if isinstance(raw_pending, list):
            state_changes = entry.setdefault("state_changes", [])
            for item in [str(item) for item in raw_pending if str(item).strip()][-50:]:
                if item not in state_changes:
                    state_changes.append(item)
    round_key = str(progression_state.round_value(instance))
    entry["combat_extension_round_start"] = copy.deepcopy(
        round_snapshots(instance).get(
            round_key, current(instance) if isinstance(current(instance), dict) else {},
        )
    )
    entry["pre_combat_extension_snapshot"] = copy.deepcopy(
        pre_snapshot if pre_snapshot is not None else current_combat_extension_snapshot(instance)
    )
    round_snapshots(instance).pop(round_key, None)


def read_state(instance: Any, kind: str) -> Any:
    if kind == module_hooks.COMBAT_EXTENSION:
        return current(instance)
    if kind == module_hooks.COMBAT_EXTENSION_SNAPSHOT:
        return current_combat_extension_snapshot(instance)
    return None


module_hooks.register(module_hooks.ROUND_RECOVERY_PREFLIGHT, MODULE_NAME, preflight)
module_hooks.register(module_hooks.ROUND_ABORT, MODULE_NAME, abort_round)
module_hooks.register(module_hooks.ROUND_REWIND_BEGIN, MODULE_NAME, rewind_begin)
module_hooks.register(module_hooks.ROUND_REWIND_RESTORE, MODULE_NAME, rewind_restore)
module_hooks.register(module_hooks.ROUND_COMMIT, MODULE_NAME, commit_round)
module_hooks.register(module_hooks.INSTANCE_RESET_PREFLIGHT, MODULE_NAME, preflight)
module_hooks.register(module_hooks.INSTANCE_RESET, MODULE_NAME, reset)
module_hooks.register(module_hooks.STATE_READ, MODULE_NAME, read_state)
