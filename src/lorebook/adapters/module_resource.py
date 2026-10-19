"""Explicit module Book/legacy-entry to editable v3 review boundary."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any

from src.engine.language import normalize_language
from src.lorebook.adapters.legacy import diceframe_compat_fields, from_legacy_entries


def module_book_review_payload(payload: dict[str, Any], language: str = "") -> dict[str, Any]:
    if payload.get("spec") == "lorebook_v3":
        return deepcopy(payload)
    if int(payload.get("lorebook_schema_version", 1)) != 1:
        raise ValueError("unsupported module Book resource schema")
    rows = payload.get("entries", [])
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("module Book entries must be objects")
    draft = from_legacy_entries(payload)
    entries = []
    for entry, raw in zip(draft.entries, rows, strict=True):
        row = asdict(entry)
        extensions = deepcopy(raw.get("extensions") or {})
        if not isinstance(extensions, dict) or not isinstance(extensions.get("diceframe", {}), dict):
            raise ValueError("module entry extensions must be objects")
        extensions.update(entry.extensions)
        extensions["diceframe"] = {**extensions.get("diceframe", {}), **diceframe_compat_fields(entry), "regex_executable": entry.regex_executable}
        extensions["module_original_entry"] = deepcopy(raw)
        row.update({"id": entry.external_id, "extensions": extensions, **entry.timed, **entry.recursion_flags})
        entries.append(row)
    book = deepcopy(payload)
    book.update({"entries": entries, "language": normalize_language(payload.get("language") or language)})
    return {"spec": "lorebook_v3", "data": {"lorebook": book}}
