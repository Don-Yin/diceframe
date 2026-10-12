"""Legacy free-form mechanics projected onto the generic game context."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.engine.game_context_projector import GameContextProjector
from src.engine.game_state_contracts import CharacterSheetView, GameContextView

if TYPE_CHECKING:
    from src.engine.game_instance import GameInstance


def project_legacy_character_sheet(character_sheet: dict[str, Any]) -> CharacterSheetView:
    """Preserve the pre-runtime character view used by legacy prompts."""
    attributes = character_sheet.get("attributes", {})
    equipment = character_sheet.get("equipment", [])
    skills = character_sheet.get("skills", [])
    if skills and isinstance(skills[0], str):
        skills = [{"name": skill, "value": 20} for skill in skills]
    sheet: CharacterSheetView = {
        "hp": character_sheet.get("hp", 0),
        "max_hp": character_sheet.get("max_hp", 0),
        "class": character_sheet.get("class", ""),
        "race": character_sheet.get("race", ""),
        "level": character_sheet.get("level", 1),
        "xp": character_sheet.get("xp", 0),
        "gold": character_sheet.get("gold", 0),
        "attributes": attributes,
        "_modifiers": {key: (value - 10) // 2 for key, value in attributes.items()},
        "equipment": equipment,
        "_armor": sum(
            item.get("armor", 1)
            if item.get("type") in ("armor", "clothing")
            else item.get("armor", 0)
            for item in equipment
        ),
        "skills": skills,
        "inventory": character_sheet.get("inventory", []),
        "key_items": character_sheet.get("key_items", []),
    }
    if character_sheet.get("background"):
        sheet["background"] = character_sheet["background"]
    if character_sheet.get("deceased"):
        sheet["deceased"] = True
    special_stats: dict[str, int] = {}
    for key in (
        "sanity",
        "qi",
        "luck",
        "cyberware",
        "cyberware_load",
        "humanity",
        "heat",
    ):
        if key in character_sheet:
            special_stats[key] = character_sheet[key]
    if special_stats:
        sheet["_special_stats"] = special_stats
    return sheet


def project_legacy_game_context(instance: GameInstance) -> GameContextView:
    """Build generic context with explicit legacy mechanic fallbacks."""
    return GameContextProjector.project(
        instance,
        character_sheet_projector=project_legacy_character_sheet,
    )
