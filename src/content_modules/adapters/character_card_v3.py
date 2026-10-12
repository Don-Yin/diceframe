"""Portable character card: a Tavern ``chara_card_v3`` envelope.

The client-side library stores one interoperable file per character:

- the standard v3 fields (``name``, ``description``, ...) so other Character
  Card tools can open it;
- the complete DiceFrame card body (schema 2) in
  ``data.extensions.diceframe``, which is the authority for DiceFrame;
- the embedded lore in the standard ``data.character_book`` field
  (Lorebook v3 shape).

This module is pure: it neither validates mechanics nor touches storage.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

CARD_V3_SPEC = "chara_card_v3"
CARD_V3_SPEC_VERSION = "3.0"
DICEFRAME_EXTENSION = "diceframe"
CARD_V3_INVALID = "CARD_V3_INVALID"


class CardV3FormatError(ValueError):
    code = CARD_V3_INVALID


@dataclass(frozen=True)
class CardV3Document:
    body: dict[str, Any]
    character_book: dict[str, Any] | None


def read_card_v3(document: Any) -> CardV3Document:
    """Extract the DiceFrame body and embedded book; fail closed on shape."""

    if not isinstance(document, dict) or document.get("spec") != CARD_V3_SPEC:
        raise CardV3FormatError("document must be a chara_card_v3 card")
    data = document.get("data")
    if not isinstance(data, dict):
        raise CardV3FormatError("chara_card_v3 card has no data object")
    extensions = data.get("extensions")
    body = extensions.get(DICEFRAME_EXTENSION) if isinstance(extensions, dict) else None
    if not isinstance(body, dict):
        raise CardV3FormatError("card has no data.extensions.diceframe body")
    body = copy.deepcopy(body)
    if not str(body.get("character_name") or "").strip():
        body["character_name"] = str(data.get("name") or "").strip()
    book = data.get("character_book")
    return CardV3Document(
        body=body,
        character_book=copy.deepcopy(book) if isinstance(book, dict) else None,
    )


def write_card_v3(body: dict[str, Any], *, character_book: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wrap a DiceFrame card body in a complete ``chara_card_v3`` envelope."""

    data: dict[str, Any] = {
        "name": str(body.get("character_name") or ""),
        "description": str(body.get("background") or ""),
        "personality": "",
        "scenario": "",
        "first_mes": "",
        "mes_example": "",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [],
        "group_only_greetings": [],
        "tags": [],
        "creator": "",
        "character_version": "",
        "extensions": {DICEFRAME_EXTENSION: copy.deepcopy(body)},
    }
    if character_book is not None:
        data["character_book"] = copy.deepcopy(character_book)
    return {"spec": CARD_V3_SPEC, "spec_version": CARD_V3_SPEC_VERSION, "data": data}


__all__ = [
    "CARD_V3_INVALID",
    "CARD_V3_SPEC",
    "CardV3Document",
    "CardV3FormatError",
    "DICEFRAME_EXTENSION",
    "read_card_v3",
    "write_card_v3",
]
