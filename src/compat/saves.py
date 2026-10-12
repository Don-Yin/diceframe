"""Compatibility helpers for persisted game saves."""

from __future__ import annotations

from typing import Any

from .aliases import canonical_class_id, canonical_item_id


def normalize_save_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Add a non-destructive schema marker while retaining every legacy field."""
    result = dict(payload)
    result.setdefault("save_schema_version", 1)
    for container in (result.get("players"), result.get("npcs")):
        if not isinstance(container, dict):
            continue
        for actor in container.values():
            if not isinstance(actor, dict):
                continue
            sheet = actor.get("character_sheet") if isinstance(actor.get("character_sheet"), dict) else actor
            legacy_class = sheet.get("class") or sheet.get("class_name")
            if legacy_class and not sheet.get("class_id"):
                class_id = canonical_class_id(legacy_class)
                if class_id:
                    sheet["class_id"] = class_id
            equipment = sheet.get("equipment")
            if isinstance(equipment, list):
                for item in equipment:
                    if not isinstance(item, dict) or item.get("item_key"):
                        continue
                    item_id = canonical_item_id(item.get("name"))
                    if item_id:
                        item["item_key"] = item_id
    return result


def legacy_chatlog_name() -> str:
    return "chatlog.jsonl"
