from __future__ import annotations

import pytest

from src.engine.game_instance import GameInstance
from src.webui.services.game_media import (
    GameMediaDependencies,
    GameMediaService,
)


class _MediaContext:
    def __init__(self, instance: GameInstance) -> None:
        self.instance = instance
        self.saved = 0
        self.refreshed: list[str] = []

    async def save(self, _instance) -> None:
        self.saved += 1

    def service(self) -> GameMediaService:
        return GameMediaService(GameMediaDependencies(
            parse_game_key=lambda raw: tuple(raw.split("|")),
            get_instance=lambda _key: self.instance,
            save_instance=self.save,
            load_world_template=lambda _world_id: None,
            get_lore_world=lambda world_id: {
                "id": world_id,
                "name": "Custom Lore World",
            },
            refresh_lorebook_index=self.refreshed.append,
            resolve_rule_id=lambda _instance: "freeform_fantasy",
            resolve_default_scene_image=lambda world_id, rule_id: {
                "kind": "builtin",
                "path": f"{world_id}/{rule_id}.webp",
            },
            materialize_scene_image=lambda reference: dict(reference),
        ))


@pytest.mark.asyncio
async def test_switch_world_uses_lore_fallback_and_saves_once() -> None:
    context = _MediaContext(GameInstance(("web", "room", "bot")))

    result = await context.service().switch_world(
        "web|room|bot", "custom_lore",
    )

    assert result == {
        "ok": True,
        "world_id": "custom_lore",
        # No user title (empty) -> the title follows the selected world.
        "world_name": "Custom Lore World",
        "world_display_name": "Custom Lore World",
    }
    assert context.saved == 1
    assert context.refreshed == ["custom_lore"]


@pytest.mark.asyncio
async def test_default_scene_materialization_attaches_projected_rule() -> None:
    instance = GameInstance(
        ("web", "room", "bot"), world_id="custom_lore", rule_id="",
    )
    context = _MediaContext(instance)

    result = await context.service().update_scene_image(
        "web|room|bot", use_default=True,
    )

    assert result["ok"] is True
    assert result["scene_image"] == {
        "kind": "builtin",
        "path": "custom_lore/freeform_fantasy.webp",
    }
    assert instance.rule_id == "freeform_fantasy"
    assert context.saved == 1
