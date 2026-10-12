from __future__ import annotations

import shutil
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.adventures import AdventureBundleLoader
from src.compat.dnd2024_adventure_bindings import (
    apply_unreleased_adventure_binding_migration,
    migrate_unreleased_adventure_binding,
)
from src.engine.game_instance import GameRegistry
from src.engine.modules import ruleset_runtime


ROOT = Path(__file__).parents[1]
OLD_DIGEST = (
    "sha256:363c6786c0e9460ec911d85460c49b610addf8e86cc86d136538daee24d6740c"
)


def _bindings(world_id: str = "greymoor") -> tuple[dict, dict]:
    current = AdventureBundleLoader(ROOT / "templates" / "adventures").resolve(
        "core:lanterns_of_greymoor", "zh-CN",
    ).binding(world_id)
    old = {**current, "content_digest": OLD_DIGEST}
    return old, current


def test_known_unreleased_digest_migrates_to_current_binding() -> None:
    old, current = _bindings()

    assert migrate_unreleased_adventure_binding(old, current) == current


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("adventure_id", "core:another_adventure"),
        ("version", "9.9.9"),
        ("format", "diceframe:another-format"),
        ("world_id", "another-world"),
        ("content_digest", "sha256:unknown"),
    ],
)
def test_unknown_or_different_binding_does_not_migrate(field: str, value: str) -> None:
    old, current = _bindings()
    old[field] = value

    assert migrate_unreleased_adventure_binding(old, current) is None


def test_instance_migration_updates_campaign_projection_without_losing_metadata() -> None:
    old, current = _bindings("portable-world")
    instance = SimpleNamespace(
        adventure_binding=deepcopy(old),
        modules={"ruleset_runtime": {**ruleset_runtime.fresh(), "state": {
            "campaign": {
                "adventure_binding": {
                    "adventure_id": old["adventure_id"],
                    "world_id": old["world_id"],
                    "recommended_world_id": "greymoor",
                    "compatibility": "review_required",
                    "scene_source": "adventure",
                    "version": old["version"],
                    "content_digest": old["content_digest"],
                },
            },
        }}},
    )

    assert apply_unreleased_adventure_binding_migration(instance, current) is True
    assert instance.adventure_binding == current
    projected = ruleset_runtime.state(instance)["campaign"]["adventure_binding"]
    assert projected["content_digest"] == current["content_digest"]
    assert projected["version"] == current["version"]
    assert projected["recommended_world_id"] == "greymoor"
    assert projected["compatibility"] == "review_required"
    assert projected["scene_source"] == "adventure"


def test_conflicting_campaign_projection_fails_closed() -> None:
    old, current = _bindings()
    instance = SimpleNamespace(
        adventure_binding=deepcopy(old),
        modules={"ruleset_runtime": {**ruleset_runtime.fresh(), "state": {
            "campaign": {
                "adventure_binding": {
                    "adventure_id": old["adventure_id"],
                    "world_id": old["world_id"],
                    "version": old["version"],
                    "content_digest": "sha256:another-unknown-digest",
                },
            },
        }}},
    )

    assert apply_unreleased_adventure_binding_migration(instance, current) is None
    assert instance.adventure_binding == old


@pytest.mark.optional
@pytest.mark.asyncio
async def test_real_unreleased_save_copy_migrates_and_persists(tmp_path: Path) -> None:
    save_name = (
        "web#default_fantasy_copy_1787754499523_1787754499750449800#web_bot"
    )
    source = ROOT / "data" / "saves" / save_name
    if not source.is_dir():
        pytest.skip("local unreleased development save is not present")
    save_dir = tmp_path / "saves"
    shutil.copytree(source, save_dir / save_name)
    registry = GameRegistry(save_dir)
    game_key = (
        "web", "default_fantasy_copy_1787754499523_1787754499750449800", "web_bot",
    )
    instance = await registry.load(game_key)
    assert instance is not None
    expected = AdventureBundleLoader(ROOT / "templates" / "adventures").resolve(
        "core:lanterns_of_greymoor", "zh-CN",
    ).binding(instance.world_id)

    assert apply_unreleased_adventure_binding_migration(instance, expected) is True
    await registry.save(instance)

    recovered = await GameRegistry(save_dir).load(game_key)
    assert recovered is not None
    assert recovered.adventure_binding == expected
    projected = ruleset_runtime.state(recovered)["campaign"]["adventure_binding"]
    assert projected["content_digest"] == expected["content_digest"]
