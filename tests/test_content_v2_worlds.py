from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.content.rule_locale import materialize_rule
from src.content.worlds import load_world_template, localize_lorebook_entries, materialize_world
from src.plugin_host import PluginHost


ROOT = Path(__file__).resolve().parents[1]


def _world_skeleton(data: dict) -> dict:
    entries = []
    for entry in data.get("starter_lorebook", []):
        entries.append({key: entry.get(key) for key in (
            "id", "type", "tier", "unreliable", "sync_on_enter", "triggers_recursive",
            "visible_to", "match_mode", "sticky", "cooldown", "delay", "order",
            "probability", "group", "group_weight", "connected_to",
        )})
    return {
        key: data.get(key)
        for key in ("world_id", "default_rule", "recommended_rules", "suggested_difficulty")
    } | {"starter_lorebook": entries}


def test_builtin_world_locale_keeps_canonical_identity_and_mechanics():
    worlds = ROOT / "templates" / "worlds"
    for core_path in sorted(worlds.glob("*.json")):
        core = json.loads(core_path.read_text(encoding="utf-8"))
        if int(core.get("world_schema_version", 1) or 1) < 2:
            continue
        canonical = _world_skeleton(core)
        localized = load_world_template(worlds, core["world_id"], "en")
        assert localized is not None
        assert _world_skeleton(localized) == canonical, core_path.name
    default = load_world_template(worlds, "default_fantasy", "en")
    assert [entry["id"] for entry in default["starter_lorebook"]] == [
        entry["id"] for entry in json.loads(
            (worlds / "default_fantasy.json").read_text(encoding="utf-8")
        )["starter_lorebook"]
    ]


def test_world_locale_can_only_overlay_canonical_lore_display_fields():
    core = {
        "world_id": "pack_world",
        "default_rule": "d20",
        "suggested_difficulty": "standard",
        "starter_lorebook": [{
            "id": "npc_guide", "name": "Guide", "type": "npc", "tier": "core",
            "unreliable": False, "content": "core",
        }],
    }
    overlay = {
        "locale_schema_version": 1, "locale": "en",
        "target": {"kind": "world", "id": "pack_world"},
        "fields": {"world_name": "Pack World"},
        "starter_lorebook": {"npc_guide": {"name": "Guide", "content": "localized"}},
    }
    localized = materialize_world(core, overlay)
    assert localized["starter_lorebook"][0]["id"] == "npc_guide"
    assert localized["starter_lorebook"][0]["type"] == "npc"
    assert localized["suggested_difficulty"] == "standard"
    assert localized["starter_lorebook"][0]["content"] == "localized"
    with pytest.raises(ValueError):
        materialize_world(core, {**overlay, "starter_lorebook": {"npc_fake": {"name": "Fake"}}})
    with pytest.raises(ValueError):
        materialize_world(core, {**overlay, "starter_lorebook": {"npc_guide": {"tier": "archived"}}})
    with pytest.raises(ValueError):
        materialize_world(core, {**overlay, "unknown": True})
    with pytest.raises(ValueError):
        materialize_world(core, {**overlay, "fields": "bad"})
    with pytest.raises(ValueError):
        materialize_world(core, {**overlay, "starter_lorebook": []})


def test_rule_locale_nested_mechanics_are_rejected():
    core = {
        "rule_id": "r", "attributes": [{"key": "str", "name": "Strength"}],
        "classes": [{"id": "fighter", "name": "Fighter"}],
        "items": {"sword": {"name": "Sword", "damage_dice": "1d8"}},
        "skills": {"strike": {"name": "Strike"}},
    }
    base = {"locale_schema_version": 1, "locale": "en", "target": {"kind": "rule", "id": "r"}}
    with pytest.raises(ValueError):
        materialize_rule(core, {**base, "items": {"sword": {"damage_dice": "9d99"}}})
    with pytest.raises(ValueError):
        materialize_rule(core, {**base, "classes": {"fighter": {"scripts": []}}})
    with pytest.raises(ValueError):
        materialize_rule(core, {**base, "fields": "bad"})
    with pytest.raises(ValueError):
        materialize_rule(core, {**base, "items": []})
    with pytest.raises(ValueError):
        materialize_rule(core, {**base, "skills": 42})
    with pytest.raises(ValueError):
        materialize_rule(core, {**base, "rule": {"skill_pools": {"fighter": ["cheat"]}}})
    with pytest.raises(ValueError):
        materialize_rule(core, {**base, "rule": {"item_categories": {"weapon": ["anything"]}}})
    with pytest.raises(ValueError):
        materialize_rule(core, {**base, "rule": {"currency": {"name": "gold"}}})
    with pytest.raises(ValueError):
        materialize_rule(core, {**base, "rule": {"difficulty_instructions": ["bad"]}})
    with pytest.raises(ValueError):
        materialize_rule(core, {**base, "skills": {"strike": {"aliases": ["hit", 1]}}})


def test_persisted_lorebook_gets_a_per_game_localized_view():
    persisted = [{
        "id": "default_fantasy_tavern_keeper", "world_id": "default_fantasy",
        "name": "酒馆老板", "keywords": ["酒馆"], "content": "中文内容",
        "type": "npc", "tier": "core", "match_mode": "all",
    }]
    world = {
        "world_id": "default_fantasy",
        "starter_lorebook": [{
            "id": "tavern_keeper", "name": "Innkeeper", "keywords": ["inn"],
            "content": "English content", "type": "npc", "tier": "archived",
        }],
    }

    localized = localize_lorebook_entries(persisted, world)

    assert localized[0]["id"] == "default_fantasy_tavern_keeper"
    assert localized[0]["name"] == "Innkeeper"
    assert localized[0]["keywords"] == ["inn"]
    assert localized[0]["content"] == "English content"
    assert localized[0]["type"] == "npc"
    assert localized[0]["tier"] == "core"
    assert localized[0]["match_mode"] == "all"
    assert persisted[0]["name"] == "酒馆老板"


@pytest.mark.asyncio
async def test_v1_plugin_rule_uses_rule_system_compatibility_loader(tmp_path):
    plugins = tmp_path / "plugins" / "legacy"
    plugins.mkdir(parents=True)
    (plugins / "plugin.json").write_text(json.dumps({
        "schema_version": 1, "id": "legacy", "name": "Legacy", "version": "1",
        "plugin_type": "content-pack", "contributes": {"rules": ["rules/*.json"]},
    }), encoding="utf-8")
    (plugins / "config.schema.json").write_text(json.dumps({
        "type": "object", "properties": {"enabled": {"type": "boolean", "default": False}},
    }), encoding="utf-8")
    rule_dir = plugins / "rules"
    rule_dir.mkdir()
    rule = {"rule_id": "legacy_rule", "extends": "base_d20", "rule_name": "Legacy", "attributes": []}
    rule_path = rule_dir / "legacy_rule.json"
    rule_path.write_text(json.dumps(rule), encoding="utf-8")
    host = PluginHost(tmp_path / "plugins", tmp_path / "data")
    host.discover()
    await host.update_config("legacy", {"enabled": True})
    expected = host.load_rule_template("legacy_rule")
    from src.rules.rule_system import RuleSystem
    assert expected == RuleSystem.load(rule_path).template


@pytest.mark.asyncio
async def test_plugin_world_locale_preserves_canonical_starter_lore(tmp_path):
    plugin = tmp_path / "plugins" / "pack"
    (plugin / "content" / "worlds").mkdir(parents=True)
    (plugin / "locales" / "en" / "worlds").mkdir(parents=True)
    (plugin / "config.schema.json").write_text(json.dumps({
        "type": "object", "properties": {"enabled": {"type": "boolean", "default": False}},
    }), encoding="utf-8")
    (plugin / "plugin.json").write_text(json.dumps({
        "schema_version": 1, "content_schema_version": 2, "locale_schema_version": 1,
        "default_locale": "en", "id": "pack", "name": "Pack", "version": "1",
        "plugin_type": "content-pack", "contributes": {"world_templates": ["content/worlds/*.json"]},
    }), encoding="utf-8")
    core = {
        "world_id": "plugin_world", "world_name": "世界", "default_rule": "d20",
        "suggested_difficulty": "standard", "starter_lorebook": [{
            "id": "npc_guide", "name": "向导", "type": "npc", "tier": "core", "content": "core",
        }],
    }
    (plugin / "content" / "worlds" / "plugin_world.json").write_text(json.dumps(core), encoding="utf-8")
    (plugin / "locales" / "en" / "worlds" / "plugin_world.json").write_text(json.dumps({
        "locale_schema_version": 1, "locale": "en", "target": {"kind": "world", "id": "plugin_world"},
        "fields": {"world_name": "Plugin World"},
        "starter_lorebook": {"npc_guide": {"name": "Guide", "content": "localized"}},
    }), encoding="utf-8")
    host = PluginHost(tmp_path / "plugins", tmp_path / "data")
    host.discover()
    await host.update_config("pack", {"enabled": True})
    world = host.load_world_template("plugin_world", "en")
    assert world["world_name"] == "Plugin World"
    assert world["starter_lorebook"][0]["id"] == "npc_guide"
    assert world["starter_lorebook"][0]["type"] == "npc"
    assert world["suggested_difficulty"] == "standard"
