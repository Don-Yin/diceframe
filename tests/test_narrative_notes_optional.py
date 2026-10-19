from __future__ import annotations

from copy import deepcopy

import pytest

from src.engine import module_hooks
from src.engine.game_instance import GameInstance
from src.engine.modules import narrative_notes
from src.llm.context_builder import build_context


@pytest.fixture
def without_notes():
    handlers = module_hooks.unregister_owner(narrative_notes.MODULE_NAME)
    try:
        yield
    finally:
        for point, handler in handlers.items():
            module_hooks.register(point, narrative_notes.MODULE_NAME, handler)


def test_missing_narrative_owner_drops_optional_writes(without_notes):
    instance = GameInstance(game_key=("web", "optional-notes", "bot"))
    instance.set_scene("discarded_scene_marker")
    assert narrative_notes.scene(instance) == ""


@pytest.mark.asyncio
async def test_missing_owner_hides_its_notes_and_reset_preserves_opaque_storage(without_notes):
    instance = GameInstance(game_key=("web", "optional-notes", "bot"))
    narrative_notes.replace_scene(instance, "hidden_scene_marker")
    narrative_notes.summary(instance)["narrative"] = "hidden_summary_marker"
    before = deepcopy(instance.modules[narrative_notes.MODULE_NAME])
    context = await build_context(instance, "system", [], "action")
    assert "hidden_scene_marker" not in context and "hidden_summary_marker" not in context
    await instance.reset()
    assert instance.modules[narrative_notes.MODULE_NAME] == before
