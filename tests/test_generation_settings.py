from __future__ import annotations

from copy import deepcopy

import pytest

from src.engine.game_instance import GameInstance
from src.llm.context_builder import build_context
from src.webui.config_update import prepare_config_update
from src.webui.runtime_config import ConfigStore, RuntimePaths


def test_generation_settings_persist_and_are_public_without_credentials(tmp_path):
    store = ConfigStore(RuntimePaths.from_root(tmp_path, {}), {})
    initial = store.load()
    update = {"llm_generation_options": {"temperature": .8, "frequency_penalty": .3}, "context_recent_rounds": 10}
    prepared = prepare_config_update(initial.state, update)
    assert not prepared.error
    store.save(prepared.state)
    public = store.public_view(store.load())
    for key, value in update.items():
        assert public[key] == value


@pytest.mark.parametrize("options", [
    {"temperature": 3}, {"temperature": True}, {"top_p": -1}, {"frequency_penalty": 3},
    {"presence_penalty": float("nan")}, {"unknown": 1}, [], None,
], ids=["temperature-range", "boolean", "top-p", "penalty", "nan", "unknown", "list", "null"])
def test_invalid_generation_options_are_rejected_atomically(options):
    original = {"model": "unchanged", "llm_generation_options": {}}
    prepared = prepare_config_update(original, {"model": "candidate", "llm_generation_options": options})
    assert prepared.error
    assert original == {"model": "unchanged", "llm_generation_options": {}}


@pytest.mark.parametrize("value", [-1, 101, 1.5, True, "10"])
def test_recent_history_requires_an_integer_in_range(value):
    assert prepare_config_update({}, {"context_recent_rounds": value}).error


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None, [], {}])
def test_dedicated_check_model_toggle_requires_a_boolean(value):
    assert prepare_config_update({}, {"check_model_enabled": value}).error


@pytest.mark.asyncio
async def test_recent_round_limit_affects_context_without_truncating_the_save_or_swipe_override():
    instance = GameInstance(game_key=("web", "history", "bot"), gm_uid="gm")
    instance.log = [{"round": i, "gm_response": f"round_marker_{i:03d}"} for i in range(1, 7)]
    original = deepcopy(instance.log)
    context = await build_context(instance, "system", [], "action", context_recent_rounds=2)
    assert "round_marker_006" in context and "round_marker_005" in context
    assert "round_marker_004" not in context
    swipe = await build_context(instance, "system", [], "action", history_override=instance.log[:4], context_recent_rounds=2)
    assert "round_marker_004" in swipe and "round_marker_003" in swipe
    assert "round_marker_005" not in swipe and "round_marker_002" not in swipe
    assert instance.log == original
