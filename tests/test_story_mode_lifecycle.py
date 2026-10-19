from __future__ import annotations

import pytest

pytest_plugins = ["tests.webapi_harness"]

from src.engine.game_instance import GameInstance
from src.engine.modules import storytelling


def test_story_mode_round_trips_without_top_level_field() -> None:
    instance = GameInstance(game_key=("web", "story-mode", "bot"))
    storytelling.replace_mode(instance, "dialogue")
    restored = GameInstance.from_dict(instance.to_dict())

    assert storytelling.mode(restored) == "dialogue"
    assert "story_mode" not in restored.to_dict()


@pytest.mark.asyncio
async def test_invalid_story_mode_is_rejected_before_save(web_api) -> None:
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api

    result = await api.create_game(
        "template_world",
        "invalid-story-mode",
        story_mode="invalid",
        players=[{"character_name": "艾琳", "class": "游侠", "attributes": {"str": 12}}],
    )

    assert result["ok"] is False
    assert not registry.list_all()


@pytest.mark.asyncio
async def test_story_mode_is_projected_and_kept_by_reset_and_restart(web_api) -> None:
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api

    created = await api.create_game(
        "template_world",
        "dialogue-story",
        story_mode="dialogue",
        players=[{"character_name": "艾琳", "class": "游侠", "attributes": {"str": 12}}],
    )
    assert created["ok"] is True
    game_key = created["game_key"]
    instance = registry.get(api._parse_key(game_key))
    storytelling.set_portrait(
        instance,
        "s_1234567890abcdef1234",
        {"kind": "builtin", "id": "freeform_fantasy:1"},
    )
    assert api.game_detail(game_key)["story_mode"] == "dialogue"

    assert (await api.reset_game(game_key))["ok"] is True
    instance = registry.get(api._parse_key(game_key))
    assert storytelling.mode(instance) == "dialogue"
    assert storytelling.portraits(instance)["s_1234567890abcdef1234"] == {
        "kind": "builtin", "id": "freeform_fantasy:1",
    }

    created_for_restart = await api.create_game(
        "template_world",
        "dialogue-story-restart",
        story_mode="dialogue",
        players=[{"character_name": "艾琳", "class": "游侠", "attributes": {"str": 12}}],
    )
    restart_key = created_for_restart["game_key"]
    assert (await api.restart_game(restart_key))["ok"] is True
    instance = registry.get(api._parse_key(restart_key))
    assert storytelling.mode(instance) == "dialogue"


@pytest.mark.asyncio
async def test_seed_creation_inherits_story_preferences_and_namespace(web_api) -> None:
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api

    source_result = await api.create_game(
        "template_world",
        "seed-source",
        story_mode="dialogue",
        players=[{"character_name": "艾琳", "class": "游侠", "attributes": {"str": 12}}],
    )
    source_key = source_result["game_key"]
    source = registry.get(api._parse_key(source_key))
    storytelling.set_portrait(
        source,
        "s_1234567890abcdef1234",
        {"kind": "builtin", "id": "freeform_fantasy:1"},
    )
    source_namespace = storytelling.identity_namespace(source)

    seeded = await api.create_from_seed(
        source_result["seed_code"],
        players=[{"character_name": "艾琳", "class": "游侠", "attributes": {"str": 12}}],
    )

    assert seeded["ok"] is True
    candidate = registry.get(api._parse_key(seeded["game_key"]))
    assert storytelling.mode(candidate) == "dialogue"
    assert storytelling.identity_namespace(candidate) == source_namespace
    assert storytelling.portraits(candidate) == {
        "s_1234567890abcdef1234": {
            "kind": "builtin", "id": "freeform_fantasy:1",
        },
    }


@pytest.mark.asyncio
async def test_seed_invalid_story_mode_has_no_creation_artifacts(web_api) -> None:
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api

    source_result = await api.create_game(
        "template_world",
        "seed-invalid-mode-source",
        players=[{"character_name": "艾琳", "class": "游侠", "attributes": {"str": 12}}],
    )
    before = {instance.game_key for instance in registry.list_all()}

    result = await api.create_from_seed(
        source_result["seed_code"],
        story_mode="invalid",
        players=[{"character_name": "艾琳", "class": "游侠", "attributes": {"str": 12}}],
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_STORY_MODE"
    assert {instance.game_key for instance in registry.list_all()} == before
