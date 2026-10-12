"""New games bind generic versioned runtimes before configuration or joining."""

from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.engine.game_instance import GameInstance
from src.rulesets.contracts import RulesetCapabilities
from src.rulesets.dnd2024.runtime import Dnd2024Runtime
from src.webui.services import game_creation_phases
from tests.test_webui_create_flow import web_api  # noqa: F401
from src.engine.modules import ruleset_runtime


@pytest.fixture
def professional_game(web_api):
    api, _lorebook, registry, _llm, worlds_dir = web_api
    rule_id = "dnd2024_srd"
    (api._rules_dir / f"{rule_id}.json").write_text(json.dumps({
        "rule_id": rule_id,
        "runtime": {"id": "core:dnd2024", "minimum_version": 1},
        "dice_system": "d20",
    }), encoding="utf-8")
    preset = api.ruleset_builder_choices(rule_id, {"locale": "en"}, "en")["choices"]["quick_presets"][0]
    character = api.ruleset_builder_finalize(
        rule_id, {**preset["draft"], "locale": "en", "name": "Binding Hero"}, "en",
    )["character"]
    return api, registry, character, worlds_dir


@pytest.mark.parametrize("locale", ["en", "zh-CN"])
def test_game_binding_matches_existing_character_binding(locale):
    runtime = Dnd2024Runtime()
    preset = runtime.builder_choices(None, {"locale": locale})["quick_presets"][0]
    character = runtime.derive_character(None, {**preset["draft"], "locale": locale, "name": "Hero"})
    binding = runtime.game_binding(None, locale)
    assert binding == character["rule_binding"] == {
        "rule_id": "dnd2024_srd", "runtime_id": "core:dnd2024",
        "runtime_version": 1, "content_version": "srd-5.2.1+r5", "state_schema_version": 1,
    }


@pytest.mark.parametrize("from_seed", [False, True], ids=["normal", "seed"])
@pytest.mark.asyncio
async def test_creation_policy_survives_save_before_and_after_character_join(professional_game, monkeypatch, from_seed):
    api, registry, character, _worlds_dir = professional_game
    payload = dict(rule_id="dnd2024_srd", players=[character], language="en", advancement_mode="xp", advancement_authority="gm")
    original = await api.create_game("template_world", **payload)
    assert original["ok"], original
    source = registry.get(api._parse_key(original["game_key"]))
    source_before = deepcopy(source.to_dict())
    runtime = Dnd2024Runtime()
    create_player = api.create_player
    joined = []

    def assert_policy(instance):
        restored = GameInstance.from_dict(instance.to_dict())
        assert ruleset_runtime.binding(restored) == ruleset_runtime.binding(instance)
        assert ruleset_runtime.binding(restored)["id"] == "core:dnd2024"
        assert ruleset_runtime.state(restored) == ruleset_runtime.state(instance)
        policy = runtime.live_advancement_policy(restored)
        assert (policy["mode"], policy["authority"]) == ("xp", "gm")

    async def observe_join(game_key, *args, **kwargs):
        instance = registry.get(api._parse_key(game_key))
        assert not instance.players
        assert_policy(instance)
        joined.append(game_key)
        return await create_player(game_key, *args, **kwargs)

    monkeypatch.setattr(api, "create_player", observe_join)
    if from_seed:
        result = await api.create_from_seed(original["seed_code"], players=[character], language="en")
    else:
        result = await api.create_game("template_world", **payload)
    assert result["ok"], result
    assert joined == [result["game_key"]]
    assert_policy(registry.get(api._parse_key(result["game_key"])))
    assert source.to_dict() == source_before


@pytest.mark.parametrize("from_seed", [False, True], ids=["normal", "seed"])
@pytest.mark.parametrize("failure", ["rejected", "exception", "missing-contract", "wrong-runtime-id"])
@pytest.mark.asyncio
async def test_binding_failure_rolls_back_creation_before_configuration_or_join(professional_game, monkeypatch, from_seed, failure):
    api, registry, character, worlds_dir = professional_game
    source = await api.create_game("template_world", rule_id="dnd2024_srd", players=[character])
    assert source["ok"], source
    before = {inst.game_key: deepcopy(inst.to_dict()) for inst in registry.list_all()}
    saves_before = set(registry.save_dir.rglob("state.json"))
    configure = Mock(side_effect=AssertionError("configuration must not run"))
    join = AsyncMock(side_effect=AssertionError("join must not run"))
    monkeypatch.setattr(Dnd2024Runtime, "configure_live_advancement", configure)
    monkeypatch.setattr(api, "create_player", join)
    if failure == "missing-contract":
        monkeypatch.delattr(Dnd2024Runtime, "game_binding")
    elif failure == "wrong-runtime-id":
        real_binding = Dnd2024Runtime.game_binding
        monkeypatch.setattr(
            Dnd2024Runtime, "game_binding",
            lambda self, rule, locale: {**real_binding(self, rule, locale), "runtime_id": "test:wrong"},
        )
    elif failure == "exception":
        monkeypatch.setattr(Dnd2024Runtime, "game_binding", Mock(side_effect=ValueError("binding unavailable")))
    else:
        monkeypatch.setattr(GameInstance, "bind_ruleset_runtime", lambda self, binding: False)
    if from_seed:
        result = await api.create_from_seed(source["seed_code"], players=[character])
    else:
        result = await api.create_game("binding_failure_world", rule_id="dnd2024_srd", players=[character], create_lorebook=True)
    assert result["ok"] is False
    assert result["error_code"] == "RULESET_BINDING_FAILED"
    assert {inst.game_key: inst.to_dict() for inst in registry.list_all()} == before
    assert set(registry.save_dir.rglob("state.json")) == saves_before
    assert not (worlds_dir / "binding_failure_world.json").exists()
    configure.assert_not_called()
    join.assert_not_called()


@pytest.mark.asyncio
async def test_character_join_keeps_existing_incompatible_binding_error(professional_game):
    api, registry, character, _worlds_dir = professional_game
    result = await api.create_game("template_world", rule_id="dnd2024_srd", players=[character])
    assert result["ok"], result
    instance = registry.get(api._parse_key(result["game_key"]))
    ruleset_runtime.binding(instance)["version"] = 999
    before = deepcopy(instance.to_dict())
    rejected = await api.create_player(result["game_key"], character, assign_new_id=True)
    assert rejected["ok"] is False
    assert rejected["error_code"] == "INCOMPATIBLE_RULESET_CHARACTER"
    assert instance.to_dict() == before


@pytest.mark.parametrize("runtime", [None, SimpleNamespace(capabilities=RulesetCapabilities())])
def test_unversioned_creation_does_not_bind(runtime):
    transaction = Mock()
    instance = GameInstance(game_key=("web", "legacy", "bot"))
    before = deepcopy(instance.to_dict())
    assert game_creation_phases.bind_ruleset_runtime(transaction, instance, runtime, None, "en") is None
    assert instance.to_dict() == before
    transaction.rollback.assert_not_called()


def test_creation_binding_uses_generic_contract_and_preserves_matching_state():
    transaction = Mock()
    instance = GameInstance(game_key=("web", "other", "bot"))
    rule = object()
    binding = {"rule_id": "other-rule", "runtime_id": "test:other", "runtime_version": 4, "content_version": "v2", "state_schema_version": 3}
    runtime = SimpleNamespace(
        runtime_id="test:other",
        capabilities=RulesetCapabilities(versioned_state=True),
        game_binding=Mock(return_value=binding),
    )
    assert game_creation_phases.bind_ruleset_runtime(transaction, instance, runtime, rule, "en") is None
    runtime.game_binding.assert_called_once_with(rule, "en")
    ruleset_runtime.state(instance)["custom_state"] = {"value": 7}
    before = deepcopy(instance.to_dict())
    assert instance.bind_ruleset_runtime(binding)
    assert instance.to_dict() == before
    assert not instance.bind_ruleset_runtime({**binding, "runtime_version": 5})
    assert instance.to_dict() == before
    transaction.rollback.assert_not_called()


def test_creation_binding_rejects_binding_for_a_different_runtime():
    transaction = Mock()
    instance = GameInstance(game_key=("web", "other", "bot"))
    before = deepcopy(instance.to_dict())
    binding = {"rule_id": "other-rule", "runtime_id": "test:wrong", "runtime_version": 4, "content_version": "v2", "state_schema_version": 3}
    runtime = SimpleNamespace(
        runtime_id="test:expected",
        capabilities=RulesetCapabilities(versioned_state=True),
        game_binding=Mock(return_value=binding),
    )
    result = game_creation_phases.bind_ruleset_runtime(transaction, instance, runtime, object(), "en")
    assert result is not None
    assert result["error_code"] == "RULESET_BINDING_FAILED"
    transaction.rollback.assert_called_once_with()
    assert instance.to_dict() == before


async def _legacy_unbound_game(api, registry, character):
    """A pre-#447 D&D save: created, but its versioned runtime was never bound."""
    result = await api.create_game("template_world", rule_id="dnd2024_srd", players=[character])
    assert result["ok"], result
    instance = registry.get(api._parse_key(result["game_key"]))
    ruleset_runtime.binding(instance).clear()
    assert not ruleset_runtime.binding(instance)
    return result["game_key"], instance


@pytest.mark.asyncio
async def test_character_join_cannot_bind_a_legacy_unbound_game(professional_game):
    api, registry, character, _worlds_dir = professional_game
    game_key, instance = await _legacy_unbound_game(api, registry, character)
    before = deepcopy(instance.to_dict())

    rejected = await api.create_player(game_key, character, assign_new_id=True)

    assert rejected["ok"] is False
    assert rejected["error_code"] == "RULESET_BINDING_MISSING"
    assert not ruleset_runtime.binding(instance)
    assert instance.to_dict() == before


@pytest.mark.asyncio
async def test_card_adoption_cannot_bind_a_legacy_unbound_game(professional_game):
    api, registry, character, _worlds_dir = professional_game
    created = await api.create_game("template_world", rule_id="dnd2024_srd", players=[character])
    assert created["ok"], created
    game_key = created["game_key"]
    joined = await api.create_player(game_key, character, assign_new_id=True)
    assert joined["ok"], joined
    user_id = joined["user_id"]
    instance = registry.get(api._parse_key(game_key))
    ruleset_runtime.binding(instance).clear()
    card = api.save_character_card(character)["card"]
    before = deepcopy(instance.to_dict())

    rejected = await api.adopt_ruleset_character_card(
        game_key, user_id, card["id"], gm_authority=True,
    )

    assert rejected["ok"] is False
    assert rejected["error_code"] == "RULESET_BINDING_MISSING"
    assert not ruleset_runtime.binding(instance)
    assert instance.to_dict() == before


def test_binding_match_is_read_only():
    instance = GameInstance(game_key=("web", "legacy", "bot"))
    binding = {"rule_id": "r", "runtime_id": "test:x", "runtime_version": 1, "content_version": "v1", "state_schema_version": 1}
    assert not instance.ruleset_binding_matches(binding)
    assert not ruleset_runtime.binding(instance)
    assert instance.bind_ruleset_runtime(binding)
    assert instance.ruleset_binding_matches(binding)
    assert not instance.ruleset_binding_matches({**binding, "runtime_version": 2})
    assert not instance.ruleset_binding_matches({**binding, "runtime_id": ""})
