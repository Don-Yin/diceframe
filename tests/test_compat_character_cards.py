from __future__ import annotations

import pytest

from src.compat import character_cards


class _CharacterCardHost:
    def list_character_cards(self):
        return {"cards": []}

    def save_character_card(self, character):
        return {"ok": True, "card": character}

    def update_character_card(self, card_id, patch):
        return {"ok": True, "card_id": card_id, "patch": patch}

    def export_character_cards(self, card_ids):
        return {"ok": True, "card_ids": card_ids}

    async def import_character_card(self, payload):
        return {"ok": True, "payload": payload}


def test_compat_facade_delegates_to_host_port() -> None:
    host = _CharacterCardHost()

    assert character_cards.list_character_cards(host) == {"cards": []}
    assert character_cards.save_character_card(host, {"id": "one"})["card"]["id"] == "one"
    assert character_cards.update_character_card(host, "one", {"name": "A"})["card_id"] == "one"
    assert character_cards.export_character_cards(host, ["one"])["card_ids"] == ["one"]


@pytest.mark.asyncio
async def test_compat_import_delegates_to_async_host_port() -> None:
    result = await character_cards.import_character_card(_CharacterCardHost(), "encoded")

    assert result == {"ok": True, "payload": "encoded"}
