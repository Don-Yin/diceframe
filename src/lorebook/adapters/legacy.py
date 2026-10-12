from __future__ import annotations

from typing import Any

from src.lorebook.domain import LoreEntryDraft, LorebookDraft


def diceframe_compat_fields(entry: LoreEntryDraft) -> dict[str, Any]:
    """Return legacy DiceFrame fields as real canonical entry attributes."""

    return {
        "type": entry.type,
        "tier": entry.tier,
        "unreliable": entry.unreliable,
        "sync_on_enter": entry.sync_on_enter,
        "visible_to": list(entry.visible_to),
        "connected_to": list(entry.connected_to),
        "triggers_recursive": list(entry.triggers_recursive),
    }


def from_legacy_entries(payload: dict[str, Any] | list[dict[str, Any]]) -> LorebookDraft:
    rows = payload if isinstance(payload, list) else payload.get("entries", payload.get("lorebook", []))
    rows = rows if isinstance(rows, list) else []
    entries = []
    for row in rows:
        row = row if isinstance(row, dict) else {}
        entries.append(LoreEntryDraft(
            name=str(row.get("name", "") or ""), content=str(row.get("content", "") or ""),
            keys=_strings(row.get("keywords", row.get("keys", []))),
            enabled=not bool(row.get("disabled", False)), constant=bool(row.get("is_constant", row.get("constant", False))),
            # Legacy DiceFrame primary matching stays on match_mode; it is a
            # different concept from the ST selective secondary logic and must
            # not be smuggled through that field.
            match_mode=str(row.get("match_mode", "any") or "any"),
            insertion_order=int(row.get("order", 100) or 100), probability=int(row.get("probability", 100) or 100),
            group_weight=int(row.get("group_weight", 1) or 1),
            type=str(row.get("type", "other") or "other"),
            tier=str(row.get("tier", "background") or "background"),
            unreliable=bool(row.get("unreliable", False)),
            sync_on_enter=bool(row.get("sync_on_enter", False)),
            visible_to=_strings(row.get("visible_to", [])),
            connected_to=_strings(row.get("connected_to", [])),
            triggers_recursive=_strings(row.get("triggers_recursive", [])),
            extensions={"diceframe": {k: row[k] for k in ("type", "tier", "unreliable", "connected_to", "visible_to", "triggers_recursive") if k in row}},
            external_id=str(row.get("id", "") or ""),
        ))
    return LorebookDraft(name=str((payload or {}).get("name", "Legacy Lorebook") if isinstance(payload, dict) else "Legacy Lorebook"), entries=entries, source={"kind": "diceframe_legacy"})


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(item).strip() for item in value or [] if str(item).strip()] if isinstance(value, list) else []
