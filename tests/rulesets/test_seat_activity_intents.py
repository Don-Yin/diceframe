"""A player-side rules-aware intent marks its seat as having acted.

After that, applying a library card to the seat (or deleting it) is GM-only;
see ``seat_activity`` and ``tests/test_character_sheet_authority.py``.
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from src.engine.modules import seat_activity
from src.webui.services import ruleset_gameplay
from tests.rulesets.test_intent_judgment_gate import _game
from webapi_harness import web_api  # noqa: F401


@pytest.mark.asyncio
async def test_gm_intent_does_not_mark_a_seat(web_api):
    _api, _lorebook, registry, _llm, _worlds = web_api
    instance, _runtime, gameplay, body = _game(registry)

    result = await gameplay.ruleset_submit_intent("|".join(instance.game_key), "gm", True, body)

    assert result["ok"] is True, result
    assert not seat_activity.has_acted(instance, "gm")


@pytest.mark.asyncio
async def test_applied_player_intent_marks_the_seat(web_api):
    _api, _lorebook, registry, _llm, _worlds = web_api
    instance, _runtime, gameplay, body = _game(registry)
    game_key = "|".join(instance.game_key)
    assert not seat_activity.has_acted(instance, "gm")

    result = await gameplay.ruleset_submit_intent(game_key, "gm", False, body)

    assert result["ok"] is True, result
    assert seat_activity.has_acted(instance, "gm")


@pytest.mark.asyncio
async def test_rolled_back_intent_does_not_mark_the_seat(web_api):
    _api, _lorebook, registry, _llm, _worlds = web_api
    instance, _runtime, gameplay, body = _game(registry)
    save = AsyncMock(side_effect=ValueError("disk full"))
    deps = replace(gameplay._gameplay_dependencies, save_instance=save)

    result = await ruleset_gameplay.submit_intent(
        deps, "|".join(instance.game_key), "gm", False, body,
    )

    assert result["ok"] is False
    assert not seat_activity.has_acted(instance, "gm")
