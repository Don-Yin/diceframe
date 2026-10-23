"""Spells granted by origin feats (Magic Initiate) for D&D 2024.

Character creation stores each Magic Initiate choice under
``spellcasting.magic_initiate``. This module is the one place that turns those
canonical choices into castable grants: the feat's own spellcasting ability
(not the class one) sets the attack bonus and save DC, and the level 1 spell
has one free cast per Long Rest tracked by ``free_cast_used`` on the entry.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.rulesets.dnd2024.character.builder import ability_modifier


def magic_initiate_entries(character: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    spellcasting = (character or {}).get("spellcasting")
    rows = spellcasting.get("magic_initiate") if isinstance(spellcasting, Mapping) else None
    return [row for row in rows or [] if isinstance(row, dict) and row.get("feat_ref")]


def feat_spell_grants(character: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Castable cantrip / level 1 spell grants from every Magic Initiate entry."""

    if not isinstance(character, Mapping):
        return []
    abilities = character.get("abilities") or {}
    derived = character.get("derived") or {}
    proficiency = int(derived.get("proficiency_bonus", 2) or 2)
    grants: list[dict[str, Any]] = []
    for entry in magic_initiate_entries(character):
        ability = str(entry.get("spellcasting_ability") or "")
        if ability not in abilities:
            continue
        modifier = ability_modifier(int(abilities[ability]))
        common = {
            "source": "feat",
            "feat_ref": str(entry["feat_ref"]),
            "spell_ability": ability,
            "spell_attack_bonus": proficiency + modifier,
            "spell_save_dc": 8 + proficiency + modifier,
        }
        for cantrip_id in entry.get("cantrip_ids") or []:
            if cantrip_id:
                grants.append({"spell_ref": f"spell:{cantrip_id}", **common})
        spell_id = str(entry.get("level_1_spell_id") or "")
        if spell_id:
            grants.append({
                "spell_ref": f"spell:{spell_id}", **common,
                "free_cast_available": not bool(entry.get("free_cast_used")),
            })
    return grants


def spend_feat_free_cast(character: dict[str, Any], feat_ref: str) -> None:
    entry = next(
        (row for row in magic_initiate_entries(character) if row["feat_ref"] == feat_ref),
        None,
    )
    if entry is None:
        raise ValueError(f"feat spell grant is missing: {feat_ref}")
    if entry.get("free_cast_used"):
        raise ValueError(f"feat free cast is already spent: {feat_ref}")
    entry["free_cast_used"] = True


def restore_feat_free_casts(character: dict[str, Any]) -> list[str]:
    """Long Rest recovery; returns the feat refs whose free cast came back."""

    restored = []
    for entry in magic_initiate_entries(character):
        if entry.pop("free_cast_used", False):
            restored.append(str(entry["feat_ref"]))
    return restored


def concentration_holder(character: dict[str, Any]) -> dict[str, Any]:
    """Where an actor's concentration lives.

    Class casters keep it on ``spellcasting.class`` (existing saves); a
    character whose only spells come from a feat keeps it on ``spellcasting``.
    """

    spellcasting = character.setdefault("spellcasting", {})
    class_magic = spellcasting.get("class")
    return class_magic if isinstance(class_magic, dict) else spellcasting
