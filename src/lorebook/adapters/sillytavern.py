from __future__ import annotations

from typing import Any

from src.lorebook.activation import (
    DEFAULT_VECTOR_ACTIVATION,
    normalize_selective_logic,
    python_regex_incompatibility,
)
from src.lorebook.domain import LoreEntryDraft, LorebookDraft

# DiceFrame canonical prompt slots. ST `position` is a numeric anchor enum
# (0=before, 1=after, 2/3=Author's Note, 4=atDepth, 5/6=Example Messages,
# 7=outlet) with no 1:1 equivalent, so only an already-canonical value is kept.
CANONICAL_PROMPT_SLOTS = frozenset(
    {"world_background", "character_context", "scene_context", "pre_history", "post_history"}
)

# ST entry fields DiceFrame intentionally does not model. They stay preserved in
# the entry's extensions and are reported as preview warnings, never dropped.
UNMAPPED_ST_FIELDS = frozenset(
    {
        "vectorized", "addMemo", "useProbability", "depth", "groupOverride",
        "automationId", "role", "displayIndex", "world", "outlet", "trigger",
        "matchPersonaDescription", "matchCharacterDescription", "matchCharacterDepth",
        "matchPersonaDepth", "matchWholeWordsPrompt",
    }
)


def from_sillytavern(payload: dict[str, Any]) -> LorebookDraft:
    rows = payload.get("entries", []) if isinstance(payload, dict) else []
    entries = []
    unmapped_fields: set[str] = set()
    unmapped_positions = 0
    regex_warnings: set[str] = set()
    for raw in rows if isinstance(rows, list) else []:
        row = raw if isinstance(raw, dict) else {}
        timed = {k: int(row[k]) for k in ("sticky", "cooldown", "delay") if isinstance(row.get(k), (int, float))}
        # ST's own recursion field names are excludeRecursion / preventRecursion;
        # the snake_case spellings stay supported for DiceFrame-flavoured exports.
        recursion_flags = {
            key: value for key, value in {
                "non_recursable": bool(row.get("nonRecursable", row.get("excludeRecursion", row.get("non_recursable", False)))),
                "prevent_further_recursion": bool(row.get("preventFurtherRecursion", row.get("preventRecursion", row.get("prevent_further_recursion", False)))),
                "delay_until_recursion": bool(row.get("delayUntilRecursion", row.get("delay_until_recursion", False))),
                "recursion_level": int(row.get("recursionLevel", row.get("recursion_level", 0)) or 0),
            }.items() if value
        }
        slot = _prompt_slot(row)
        if row.get("position") not in (None, "") and not slot:
            unmapped_positions += 1
        unparsed = UNMAPPED_ST_FIELDS & set(row)
        unmapped_fields |= unparsed
        extensions = {k: v for k, v in row.items() if k not in {"comment", "name", "content", "key", "keys", "keysecondary", "secondary_keys", "disable", "disabled", "constant", "selective", "selectiveLogic", "selective_logic", "useRegex", "use_regex", "order", "probability"}}
        # ST regexes are JavaScript; only the safely-mappable subset may run.
        # Incompatible patterns are preserved verbatim and reported, never
        # rewritten -- and never handed to Python ``re`` either, because that
        # would silently apply different semantics.
        use_regex = bool(row.get("useRegex", row.get("use_regex", False)))
        regex_executable = True
        if use_regex:
            for key in _strings(row.get("key", row.get("keys", []))):
                reason = python_regex_incompatibility(key)
                if reason:
                    regex_warnings.add(reason)
                    regex_executable = False
        # The raw anchor is kept for round-tripping but is never executed.
        extensions.setdefault("_preserved_position", row.get("position", ""))
        entries.append(LoreEntryDraft(
            name=str(row.get("comment", row.get("name", "")) or ""), content=str(row.get("content", "") or ""),
            keys=_strings(row.get("key", row.get("keys", []))), secondary_keys=_strings(row.get("keysecondary", row.get("secondary_keys", []))),
            enabled=not bool(row.get("disable", row.get("disabled", False))), constant=bool(row.get("constant", False)),
            # ST ships selectiveLogic as a numeric enum (0=AND_ANY, 1=NOT_ALL,
            # 2=NOT_ANY, 3=AND_ALL). It is a SECONDARY filter: the primary key
            # must still match first, so it is never folded into match_mode.
            selective_logic=normalize_selective_logic(row.get("selectiveLogic", row.get("selective_logic"))),
            # ST ``selective`` decides whether keysecondary filters at all; the
            # keys themselves are preserved either way.
            selective=bool(row.get("selective", True)),
            use_regex=use_regex, regex_executable=regex_executable,
            case_sensitive=bool(row.get("caseSensitive", False)),
            match_whole_words=bool(row.get("matchWholeWords", False)), scan_depth=int(row.get("scanDepth", 0) or 0),
            insertion_order=int(row.get("order", 100) or 100), probability=int(row.get("probability", 100) or 100),
            groups=_strings(row.get("group", row.get("groups", []))), group_weight=int(row.get("groupWeight", 1) or 1),
            prioritize_inclusion=bool(row.get("prioritizeInclusion", row.get("prioritize_inclusion", False))),
            group_scoring=str(row.get("groupScoring", row.get("useGroupScoring", row.get("group_scoring", ""))) or ""),
            recursion_flags=recursion_flags, vector_activation=_vector_activation(row),
            timed=timed, prompt_slot=slot, external_id=str(row.get("uid", row.get("id", "")) or ""),
            extensions=extensions,
        ))
    warnings = ["ST timed effects are message-based; DiceFrame applies authoritative turn ticks."] if any(e.timed for e in entries) else []
    warnings.extend(sorted(regex_warnings))
    if unmapped_positions:
        warnings.append(
            f"{unmapped_positions} ST position anchor(s) have no DiceFrame prompt slot equivalent; "
            "kept in extensions and not executed."
        )
    if unmapped_fields:
        warnings.append(
            "Unmapped ST fields are preserved in extensions and ignored by activation: "
            + ", ".join(sorted(unmapped_fields)) + "."
        )
    return LorebookDraft(name=str(payload.get("name", "SillyTavern World Info") or "SillyTavern World Info"), entries=entries, source={"kind": "sillytavern"}, warnings=warnings)


def _prompt_slot(row: dict[str, Any]) -> str:
    """Keep only an already-canonical slot; ST numeric anchors never execute."""

    raw = row.get("position", row.get("prompt_slot", ""))
    if raw is None:
        return ""
    text = str(raw).strip().casefold()
    return text if text in CANONICAL_PROMPT_SLOTS else ""


def _vector_activation(row: dict[str, Any]) -> str:
    """ST/CCv3 entries default to hybrid; only an explicit narrower request wins."""

    raw = row.get("vectorActivation", row.get("vector_activation"))
    if raw is None:
        return DEFAULT_VECTOR_ACTIVATION
    mode = str(raw or "").strip().lower()
    return mode if mode in {"off", "hybrid", "vector_only"} else DEFAULT_VECTOR_ACTIVATION


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(item).strip() for item in value or [] if str(item).strip()] if isinstance(value, list) else []
