from __future__ import annotations

import pytest

pytest_plugins = ["tests.webapi_harness"]


@pytest.mark.asyncio
async def test_canonical_game_creation_binds_books_without_copying(web_api):
    api, lorebook, registry, _llm, _worlds_dir = web_api
    lorebook.ensure_primary_world_book("template_world")
    result = await api.create_game(
        "canonical_target",
        world_ref={
            "source_kind": "world", "source_id": "canonical_target",
            "kind": "world", "id": "canonical_target", "digest": "",
        },
        create_lorebook=True,
        source_world_id="template_world",
        book_bindings=[{
            "ref": {
                "source_kind": "world", "source_id": "template_world",
                "kind": "lorebook", "id": "world:template_world", "digest": "",
            },
        }],
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )

    assert result["ok"] is True
    game_key = result["game_key"]
    instance = registry.get(api._parse_key(game_key))
    assert instance is not None
    assert instance.modules["content_binding"]["world_ref"]["id"] == "canonical_target"
    assert instance.modules["content_binding"]["book_refs"][0]["id"] == "world:template_world"
    assert lorebook.list_entries("canonical_target") == []
    assert lorebook.list_bindings(scope_kind="game", scope_id=game_key)

    deleted = api.delete_game(game_key)
    assert deleted["ok"] is True
    assert lorebook.list_bindings(scope_kind="game", scope_id=game_key) == []


@pytest.mark.asyncio
async def test_creation_keeps_world_ref_source_identity_and_seed_restart_inherits_it(web_api):
    api, _lorebook, registry, _llm, _worlds_dir = web_api
    module_world_ref = {
        "source_kind": "module", "source_id": "ashen_pack",
        "kind": "world", "id": "template_world", "digest": "sha256:abc",
    }
    original = await api.create_game(
        "template_world",
        world_ref=module_world_ref,
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )
    assert original["ok"] is True
    instance = registry.get(api._parse_key(original["game_key"]))
    assert instance.modules["content_binding"]["world_ref"] == module_world_ref

    restarted = await api.create_from_seed(
        original["seed_code"],
        players=[{"character_name": "洛恩", "attributes": {"str": 11}}],
        gm_uid="seed_gm",
    )
    assert restarted["ok"] is True
    reborn = registry.get(api._parse_key(restarted["game_key"]))
    assert reborn.modules["content_binding"]["world_ref"] == module_world_ref


@pytest.mark.asyncio
async def test_seed_restart_of_a_legacy_save_binds_the_plain_world_ref(web_api):
    api, _lorebook, registry, _llm, _worlds_dir = web_api
    original = await api.create_game(
        "template_world",
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )
    # A save from before content_binding existed has no slot at all.
    registry.get(api._parse_key(original["game_key"])).modules.pop("content_binding", None)

    restarted = await api.create_from_seed(
        original["seed_code"],
        players=[{"character_name": "洛恩", "attributes": {"str": 11}}],
        gm_uid="seed_gm",
    )
    assert restarted["ok"] is True
    reborn = registry.get(api._parse_key(restarted["game_key"]))
    assert reborn.modules["content_binding"]["world_ref"] == {
        "source_kind": "world", "source_id": "template_world",
        "kind": "world", "id": "template_world", "digest": "",
    }


@pytest.mark.asyncio
async def test_book_binding_failure_rolls_back_instance_and_earlier_bindings(web_api, monkeypatch):
    api, lorebook, registry, _llm, _worlds_dir = web_api
    lorebook.ensure_primary_world_book("template_world")
    lorebook.create_lorebook({"id": "extra-book", "name": "Extra"})
    real_bind = lorebook.bind_lorebook
    calls = []

    def flaky_bind(binding):
        calls.append(binding["id"])
        if len(calls) == 2:
            raise RuntimeError("disk full")
        return real_bind(binding)

    monkeypatch.setattr(lorebook, "bind_lorebook", flaky_bind)
    before = {tuple(inst.game_key) for inst in registry.list_all()}
    result = await api.create_game(
        "canonical_target",
        create_lorebook=True,
        source_world_id="template_world",
        book_bindings=[
            {"ref": {"source_kind": "world", "source_id": "template_world",
                     "kind": "lorebook", "id": "world:template_world", "digest": ""}},
            {"ref": {"source_kind": "gm", "source_id": "extra",
                     "kind": "lorebook", "id": "extra-book", "digest": ""}},
        ],
        players=[{"character_name": "艾琳", "attributes": {"str": 10}}],
    )

    assert result["ok"] is False
    assert result["error_code"] == "BOOK_BINDING_FAILED"
    assert len(calls) == 2
    assert {tuple(inst.game_key) for inst in registry.list_all()} == before
    assert lorebook.list_bindings(scope_kind="game") == []
