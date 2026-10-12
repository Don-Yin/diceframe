"""Viewer projection of D&D 2024 combat data: monster stat blocks are GM-only.

The authoritative state keeps full enemy stat blocks (attacks, abilities,
saving throws) because combat resolution needs them.  Non-GM viewers -- seated
players and P2P guests relayed as a seat -- only get what the combat roster
already shows them: name, exact HP, AC, speed and conditions.  The encounter
preset catalog is GM tooling; players see at most a name/description preview
of the encounter the story is asking for.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from typing import Any

PUBLIC_ENEMY_FIELDS = ("id", "name", "hp", "max_hp", "armor_class", "speed", "conditions")
PUBLIC_PRESET_FIELDS = ("id", "name", "description", "difficulty")
_BATCH_LIST_KEYS = ("automatic_event_batches", "resolved_event_batches")


def public_enemy(enemy: Any) -> Any:
    if not isinstance(enemy, dict):
        return enemy
    return {key: deepcopy(enemy[key]) for key in PUBLIC_ENEMY_FIELDS if key in enemy}


def _public_enemies(enemies: Any) -> Any:
    if isinstance(enemies, dict):
        return {key: public_enemy(value) for key, value in enemies.items()}
    if isinstance(enemies, list):
        return [public_enemy(value) for value in enemies]
    return enemies


def public_combat_state(combat: Any) -> Any:
    if not isinstance(combat, dict):
        return combat
    projected = deepcopy(combat)
    if "enemies" in projected:
        projected["enemies"] = _public_enemies(projected["enemies"])
    return projected


def public_event_batch(batch: Any) -> Any:
    if not isinstance(batch, dict):
        return batch
    projected = deepcopy(batch)
    events = projected.get("events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict) and "enemies" in event:
                event["enemies"] = _public_enemies(event["enemies"])
    return projected


def _public_apply_result(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    projected = dict(result)
    if "combat" in projected:
        projected["combat"] = public_combat_state(projected["combat"])
    if "event_batch" in projected:
        projected["event_batch"] = public_event_batch(projected["event_batch"])
    return projected


def public_intent_result(result: dict[str, Any]) -> dict[str, Any]:
    """Project an intent/automation response for a non-GM viewer (copy)."""

    projected = _public_apply_result(deepcopy(result))
    for key in _BATCH_LIST_KEYS:
        batches = projected.get(key)
        if isinstance(batches, list):
            projected[key] = [public_event_batch(batch) for batch in batches]
    results = projected.get("automatic_results")
    if isinstance(results, list):
        projected["automatic_results"] = [_public_apply_result(item) for item in results]
    return projected


def encounter_preview(
    presets: Iterable[Any], preset_ids: Iterable[str],
) -> dict[str, Any] | None:
    """Name/description of the first preset the story currently points at."""

    by_id = {
        str(preset.get("id") or ""): preset
        for preset in presets if isinstance(preset, dict)
    }
    for preset_id in preset_ids:
        preset = by_id.get(str(preset_id or ""))
        if preset is not None:
            return {
                key: deepcopy(preset[key]) for key in PUBLIC_PRESET_FIELDS if key in preset
            }
    return None


__all__ = [
    "PUBLIC_ENEMY_FIELDS", "PUBLIC_PRESET_FIELDS", "encounter_preview",
    "public_combat_state", "public_enemy", "public_event_batch", "public_intent_result",
]
