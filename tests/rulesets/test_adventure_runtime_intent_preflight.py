"""A future adventure_runtime slot rejects the node-complete intent before any write."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock, Mock

import pytest

from src.engine.module_state import ModuleStateError
from src.webui.services import ruleset_gameplay
from tests.rulesets.test_intent_judgment_gate import _game
from webapi_harness import web_api  # noqa: F401

MATCH = "unsupported adventure_runtime module schema"


def live_state(instance):
    return {key: value for key, value in vars(instance).items() if not isinstance(value, asyncio.Lock)}


def make_unsupported(instance):
    instance.modules["adventure_runtime"] = {
        "schema_version": 99, "progress": {"active_nodes": ["gate"]}, "play_mode": "adventure",
    }
    instance.modules.pop("economy", None)
    return instance


@pytest.mark.asyncio
async def test_node_complete_intent_rejects_before_binding_migration(web_api):
    _api, _lorebook, registry, _llm, _worlds = web_api
    instance, _runtime, gameplay, _body = _game(registry)
    make_unsupported(instance)
    complete = Mock(side_effect=AssertionError("completion must not run"))
    binding = Mock(side_effect=AssertionError("binding migration must not run"))
    save = AsyncMock()
    deps = replace(
        gameplay._gameplay_dependencies, complete_adventure_node=complete,
        resolve_adventure_binding=binding, save_instance=save,
    )
    before = deepcopy(live_state(instance))
    with pytest.raises(ModuleStateError, match=MATCH):
        await ruleset_gameplay.submit_intent(
            deps, "|".join(instance.game_key), "gm", True,
            {"type": "adventure.node.complete", "node_id": "gate"},
        )
    assert live_state(instance) == before
    complete.assert_not_called()
    binding.assert_not_called()
    save.assert_not_awaited()
