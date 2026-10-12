from __future__ import annotations
from typing import Any

from src.lorebook.activation import DEFAULT_VECTOR_ACTIVATION


def export_lorebook_v3(store: Any, book_id: str) -> dict[str, Any]:
    """Export a canonical book using the stable ``lorebook_v3`` shape."""
    book = store.get_lorebook(book_id) or {}
    settings = dict(book.get("settings") or {})
    portable_book = {
        "name": book.get("name", ""), "description": book.get("description", ""),
        **settings,
        "scan_depth": book.get("scan_depth", settings.get("scan_depth", 0)),
        "token_budget": book.get("token_budget", settings.get("token_budget", 0)),
        "recursive_scanning": bool(book.get("recursive_scanning", settings.get("recursive_scanning", False))),
        "entries": [_v3_entry(row) for row in store.list_book_entries(book_id)],
    }
    return {"spec": "lorebook_v3", "data": {"lorebook": portable_book}}


def export_lorebook_native(store: Any, book_id: str) -> dict[str, Any]:
    """Export a lossless DiceFrame-native backup of one canonical book."""
    book = dict(store.get_lorebook(book_id) or {})
    entries = [dict(row) for row in store.list_book_entries(book_id)]
    bindings = [dict(row) for row in store.list_bindings() if row.get("book_id") == book_id]
    provenance = {
        "book": {key: book.get(key, "") for key in ("source_kind", "source_id", "source_version", "source_digest")},
        "entries": {str(row.get("id")): row.get("provenance", {}) for row in entries},
    }
    return {"spec": "diceframe_lorebook_native", "version": 1, "data": {
        "book": book, "bindings": bindings, "entries": entries,
        "provenance": provenance, "settings": dict(book.get("settings") or {}),
    }}


#: Entry fields that ``lorebook_v3`` has no standard slot for. The Adapter Guide
#: requires DiceFrame-specific fields to live in explicit extensions instead of
#: expanding the standard top-level with private keys.
DICEFRAME_ONLY_ENTRY_FIELDS = (
    "type", "tier", "unreliable", "sync_on_enter", "visible_to",
    "connected_to", "triggers_recursive", "match_mode", "regex_executable",
)


def _v3_entry(row: dict[str, Any]) -> dict[str, Any]:
    """Project one canonical entry onto the portable ``lorebook_v3`` shape.

    施工单 §6：lorebook_v3 能表达的 runtime semantics 必须全部导出，否则
    ``canonical → export → reimport`` 会静默丢行为。DiceFrame-only 的东西
    全部收进 ``extensions.diceframe``，不往标准字段里塞自创键。
    """

    entry: dict[str, Any] = {
        "id": row.get("id"), "name": row.get("name"), "content": row.get("content", ""),
        "keys": row.get("keywords", []), "secondary_keys": row.get("secondary_keys", []),
        "enabled": bool(row.get("enabled", True)), "constant": bool(row.get("is_constant", False)),
        "insertion_order": row.get("order", 100), "priority": row.get("priority", 0),
        # secondary filter：keys 与「是否启用」是两个独立概念。
        "selective": bool(row.get("selective", True)),
        "selective_logic": row.get("selective_logic", "and_any"),
        "use_regex": bool(row.get("use_regex", False)),
        "case_sensitive": bool(row.get("case_sensitive", False)),
        "match_whole_words": bool(row.get("match_whole_words", False)),
        "scan_depth": int(row.get("scan_depth", 0) or 0),
        "probability": int(row.get("probability", 100) or 0),
        "groups": row.get("groups", []),
        "group_weight": int(row.get("group_weight", 1) or 1),
        "prioritize_inclusion": bool(row.get("prioritize_inclusion", False)),
        "group_scoring": row.get("group_scoring", ""),
        "sticky": int(row.get("sticky", 0) or 0),
        "cooldown": int(row.get("cooldown", 0) or 0),
        "delay": int(row.get("delay", 0) or 0),
        "vector_activation": row.get("vector_activation", DEFAULT_VECTOR_ACTIVATION),
        "prompt_slot": row.get("prompt_slot", ""),
        "non_recursable": bool(row.get("non_recursable", False)),
        "prevent_further_recursion": bool(row.get("prevent_further_recursion", False)),
        "delay_until_recursion": bool(row.get("delay_until_recursion", False)),
        "recursion_level": int(row.get("recursion_level", 0) or 0),
        "provenance": row.get("provenance", {}),
    }
    # DiceFrame-only semantics stay in an explicit extension bucket. Legacy
    # ``match_mode`` is deliberately NOT written as a top-level standard field
    # any more: it is DiceFrame private vocabulary, and the adapter still reads
    # files produced by the older exporter that did put it there.
    extensions = dict(row.get("extensions") or {})
    diceframe = dict(extensions.get("diceframe") or {})
    diceframe.update({
        "type": row.get("type", "other"),
        "tier": row.get("tier", "background"),
        "unreliable": bool(row.get("unreliable", False)),
        "sync_on_enter": bool(row.get("sync_on_enter", False)),
        "visible_to": row.get("visible_to", []),
        "connected_to": row.get("connected_to", []),
        "triggers_recursive": row.get("triggers_recursive", []),
        "match_mode": row.get("match_mode", "any"),
        "regex_executable": bool(row.get("regex_executable", True)),
    })
    extensions["diceframe"] = diceframe
    entry["extensions"] = extensions
    return entry
