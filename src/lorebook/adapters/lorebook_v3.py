from __future__ import annotations

from typing import Any

from src.lorebook.activation import (
    DEFAULT_VECTOR_ACTIVATION,
    normalize_primary_match_mode,
    normalize_selective_logic,
    python_regex_incompatibility,
)
from src.lorebook.domain import LoreEntryDraft, LorebookDraft


def from_lorebook_v3(payload: dict[str, Any]) -> LorebookDraft:
    root = payload.get("data", payload)
    book = root.get("lorebook", root) if isinstance(root, dict) else {}
    raw_entries = book.get("entries", []) if isinstance(book, dict) else []
    entries: list[LoreEntryDraft] = []
    regex_warnings: set[str] = set()
    for raw in raw_entries if isinstance(raw_entries, list) else []:
        row = raw if isinstance(raw, dict) else {}
        known_entry = {
            "id", "uid", "name", "comment", "content", "keys", "key", "secondary_keys", "keysecondary", "enabled", "constant",
            "selective", "selective_logic", "selectiveLogic", "case_sensitive", "use_regex", "match_whole_words",
            "scan_depth", "depth", "priority", "insertion_order", "order", "position", "probability", "groups",
            "group", "group_weight", "prioritize_inclusion", "group_scoring", "recursion_flags",
            "non_recursable", "prevent_further_recursion", "delay_until_recursion", "recursion_level",
            "sticky", "cooldown", "delay", "vector_activation", "prompt_slot", "extensions",
            "match_mode", "provenance",
        }
        unknown_entry = {k: v for k, v in row.items() if k not in known_entry}
        extensions = dict(row.get("extensions", {})) if isinstance(row.get("extensions"), dict) else {}
        if unknown_entry:
            extensions.setdefault("_external_raw", {}).update(unknown_entry)
        # DiceFrame-only fields travel inside ``extensions.diceframe`` so the
        # standard top-level is never expanded with private keys. Tolerant read:
        # an explicit standard top-level value still wins, and files written by
        # the older DiceFrame exporter (which put ``match_mode`` at top level)
        # keep being understood.
        private = extensions.get("diceframe") if isinstance(extensions.get("diceframe"), dict) else {}

        def _private(key: str, default: Any = None) -> Any:
            top = row.get(key)
            if top not in (None, ""):
                return top
            value = private.get(key, default)
            return default if value is None else value

        # A regex reaching this format originated as JavaScript; only the
        # safely-mappable subset may be executed by Python. The declared flag from
        # a previous export is honoured too, so a pattern already known to be
        # unmappable can never silently become executable again.
        use_regex = bool(row.get("use_regex", False))
        detected_executable = True
        if use_regex:
            for key in _strings(row.get("keys", row.get("key", []))):
                reason = python_regex_incompatibility(key)
                if reason:
                    regex_warnings.add(reason)
                    detected_executable = False
        regex_executable = detected_executable and bool(private.get("regex_executable", True))
        entries.append(LoreEntryDraft(
            name=str(row.get("name") or row.get("comment") or row.get("uid") or ""), content=str(row.get("content", "") or ""),
            keys=_strings(row.get("keys", row.get("key", []))), secondary_keys=_strings(row.get("secondary_keys", row.get("keysecondary", []))),
            enabled=bool(row.get("enabled", True)), constant=bool(row.get("constant", False)),
            # lorebook_v3 carries the ST selective secondary logic; the primary
            # key must still match first, so it is never folded into match_mode.
            selective_logic=normalize_selective_logic(row.get("selective_logic", row.get("selectiveLogic"))),
            # ``selective`` is a separate concept from ``secondary_keys``: the keys
            # are preserved either way, the flag only decides whether they gate.
            selective=bool(row.get("selective", True)),
            # Legacy DiceFrame primary matching stays its own concept and must
            # survive a lorebook_v3 round trip instead of resetting to ``any``.
            match_mode=normalize_primary_match_mode(_private("match_mode")),
            probability=int(row.get("probability", 100) or 100),
            case_sensitive=bool(row.get("case_sensitive", False)), use_regex=use_regex,
            regex_executable=regex_executable,
            match_whole_words=bool(row.get("match_whole_words", False)),
            insertion_order=int(row.get("insertion_order", row.get("order", row.get("position", 100))) or 100), priority=int(row.get("priority", 0) or 0),
            scan_depth=int(row.get("scan_depth", row.get("depth", book.get("scan_depth", 0))) or 0), external_id=str(row.get("id", row.get("uid", "")) or ""),
            groups=_strings(row.get("groups", row.get("group", []))),
            group_weight=int(row.get("group_weight", 1) or 1),
            prioritize_inclusion=bool(row.get("prioritize_inclusion", False)),
            group_scoring=str(row.get("group_scoring", "") or ""),
            recursion_flags={
                key: value for key, value in {
                    "non_recursable": bool(row.get("non_recursable", False)),
                    "prevent_further_recursion": bool(row.get("prevent_further_recursion", False)),
                    "delay_until_recursion": bool(row.get("delay_until_recursion", False)),
                    "recursion_level": int(row.get("recursion_level", 0) or 0),
                }.items() if value
            },
            timed={k: int(row[k]) for k in ("sticky", "cooldown", "delay") if isinstance(row.get(k), (int, float))},
            vector_activation=_vector_activation(row),
            prompt_slot=str(row.get("prompt_slot", "") or ""),
            # DiceFrame-only compatibility semantics: read tolerantly (standard
            # top-level first, then ``extensions.diceframe``) so a lorebook_v3
            # round trip never silently loses them.
            type=str(_private("type", "other") or "other"),
            tier=str(_private("tier", "background") or "background"),
            unreliable=bool(_private("unreliable", False)),
            sync_on_enter=bool(_private("sync_on_enter", False)),
            visible_to=_strings(_private("visible_to", [])),
            connected_to=_strings(_private("connected_to", [])),
            triggers_recursive=_strings(_private("triggers_recursive", [])),
            extensions=extensions,
        ))
    # A previous DiceFrame export re-offers its preserved payload at book level;
    # merge it back instead of nesting it one level deeper on every round trip.
    preserved_book = book.get("preserved_extensions") if isinstance(book.get("preserved_extensions"), dict) else {}
    known = {"name", "description", "scan_depth", "token_budget", "recursive_scanning", "entries", "extensions", "preserved_extensions"}
    unknown = {k: v for k, v in book.items() if k not in known}
    raw = dict(preserved_book.get("raw") or {})
    raw.update(unknown)
    extensions = dict(preserved_book.get("extensions") or {})
    extensions.update(book.get("extensions", {}) or {})
    warnings = [f"preserved unknown field: {k}" for k in sorted(unknown)]
    warnings.extend(sorted(regex_warnings))
    settings = {k: book[k] for k in ("scan_depth", "token_budget", "recursive_scanning") if k in book}
    return LorebookDraft(name=str(book.get("name", "Lorebook v3") or "Lorebook v3"), description=str(book.get("description", "") or ""), settings=settings, entries=entries, source={"kind": "lorebook_v3"}, warnings=warnings, preserved_extensions={"raw": raw, "extensions": extensions})


def _vector_activation(row: dict[str, Any]) -> str:
    """Canonical v3 entries default to hybrid; only an explicit request narrows it."""

    raw = row.get("vector_activation")
    if raw is None:
        return DEFAULT_VECTOR_ACTIVATION
    mode = str(raw or "").strip().lower()
    return mode if mode in {"off", "hybrid", "vector_only"} else DEFAULT_VECTOR_ACTIVATION


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(item).strip() for item in value or [] if str(item).strip()] if isinstance(value, list) else []
