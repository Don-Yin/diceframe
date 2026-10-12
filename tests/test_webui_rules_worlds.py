"""WebUI 规则/世界模板管理测试（自 test_webui_create_flow 拆分）。"""

from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.commands.game_handler import GameHandler
from src.engine.game_instance import GameRegistry
from src.engine.health import record_health_event
from src.llm.client import LLMResponse
from src.lorebook.matcher import KeywordMatcher
from src.lorebook.store import LorebookStore
from src.webui.api import WebAPI, can_modify_character
from src.webui.session import SessionManager

from webapi_harness import FakeLLMClient, web_api, write_world

def test_game_rule_loading_prefers_saved_rule_and_projects_legacy_save(web_api):
    api, _lorebook, registry, _fake_llm, _worlds_dir = web_api
    (api._rules_dir / "saved_custom.json").write_text(
        json.dumps({
            "rule_id": "saved_custom",
            "rule_name": "存档自带规则",
            "dice_system": "d20",
            "max_check_dc": 17,
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    saved = registry.get_or_create(("web", "saved-rule", "bot"))
    saved.world_id = "template_world"
    saved.rule_id = "saved_custom"

    loaded = api._load_rule_for_game(saved)

    assert loaded is not None
    assert loaded.rule_id == "saved_custom"
    assert loaded.max_check_dc == 17

    legacy = registry.get_or_create(("web", "legacy-rule", "bot"))
    legacy.world_id = "template_world"
    legacy.rule_id = ""

    listed = api.list_games()

    legacy_view = next(
        game for game in listed["games"]
        if game["game_key"] == "web|legacy-rule|bot"
    )
    assert legacy_view["rule_id"] == "freeform_fantasy"
    assert legacy.rule_id == ""
    loaded_legacy = api._load_rule_for_game(legacy)
    assert loaded_legacy is not None
    assert loaded_legacy.rule_id == "freeform_fantasy"


def test_save_custom_rule_copies_existing_rule_template(web_api):
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api

    result = api.save_custom_rule({
        "source_rule_id": "freeform_fantasy",
        "rule_id": "custom_test_rule",
        "rule_name": "测试自定义规则",
        "description": "从自由幻想复制的测试规则",
    })

    assert result["ok"] is True
    rules = api.list_rules()["rules"]
    created = next(rule for rule in rules if rule["rule_id"] == "custom_test_rule")
    assert created["rule_name"] == "测试自定义规则"
    assert created["description"] == "从自由幻想复制的测试规则"
    assert created["custom"] is True
    assert created["ruleset_runtime"]["id"] == "core:legacy"


@pytest.mark.parametrize("language", ["zh-CN", "en", "ja"])
def test_builtin_rule_list_materializes_requested_locale(web_api, language):
    api, *_ = web_api
    core = json.loads((api._rules_dir / "freeform_fantasy.json").read_text(encoding="utf-8"))
    core["rule_schema_version"] = 2
    (api._rules_dir / "freeform_fantasy.json").write_text(json.dumps(core), encoding="utf-8")
    locale_dir = api._rules_dir / "locales" / language
    locale_dir.mkdir(parents=True, exist_ok=True)
    (locale_dir / "freeform_fantasy.json").write_text(json.dumps({
        "locale_schema_version": 1, "locale": language,
        "target": {"kind": "rule", "id": "freeform_fantasy"},
        "fields": {"rule_name": f"Fantasy {language}", "description": f"Description {language}"},
    }), encoding="utf-8")
    payload = api.list_rules(language)
    rule = next(item for item in payload["rules"] if item["rule_id"] == "freeform_fantasy")
    assert rule["rule_id"] == "freeform_fantasy"
    assert rule["rule_name"]
    assert rule["description"]
    assert rule["active_locale"] in {language, "zh-CN"}


@pytest.mark.parametrize("language", ["zh-CN", "en", "ja"])
def test_builtin_world_list_keeps_identity_when_localized(web_api, language):
    api, *_ = web_api
    world = api._worlds_dir / "default_fantasy.json"
    world.write_text(json.dumps({
        "world_schema_version": 2, "world_id": "default_fantasy",
        "world_name": "幻想", "description": "中文", "default_rule": "dnd5e",
    }), encoding="utf-8")
    locale_dir = api._worlds_dir / "locales" / language
    locale_dir.mkdir(parents=True, exist_ok=True)
    (locale_dir / "default_fantasy.json").write_text(json.dumps({
        "locale_schema_version": 1, "locale": language,
        "target": {"kind": "world", "id": "default_fantasy"},
        "fields": {"world_name": f"Fantasy {language}", "description": f"Description {language}"},
    }), encoding="utf-8")
    payload = api.list_world_templates(language)
    world = next(item for item in payload["templates"] if item["world_id"] == "default_fantasy")
    assert world["world_id"] == "default_fantasy"
    assert world["default_rule"] == "dnd5e"
    assert world["world_name"]
    assert world["description"]


def test_save_custom_rule_rejects_unsafe_rule_id(web_api):
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api

    result = api.save_custom_rule({
        "source_rule_id": "freeform_fantasy",
        "rule_id": "../bad",
        "rule_name": "坏规则",
    })

    assert result["ok"] is False
    assert "规则 ID" in result["error"]

    cn_result = api.save_custom_rule({
        "source_rule_id": "freeform_fantasy",
        "rule_id": "中文规则",
        "rule_name": "中文规则",
    })
    assert cn_result["ok"] is False
    assert "规则 ID" in cn_result["error"]


def test_update_custom_rule_json(web_api):
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api

    created = api.save_custom_rule({
        "source_rule_id": "freeform_fantasy",
        "rule_id": "custom_edit_rule",
        "rule_name": "编辑前规则",
        "description": "编辑前说明",
    })
    assert created["ok"] is True

    detail = api.get_rule_template("custom_edit_rule")
    assert detail["ok"] is True
    template = detail["rule"]
    template["rule_name"] = "编辑后规则"
    template["description"] = "编辑后说明"
    template["attribute_points"] = 66

    updated = api.update_custom_rule("custom_edit_rule", template)

    assert updated["ok"] is True
    assert updated["rule"]["rule_name"] == "编辑后规则"
    reloaded = api.get_rule_template("custom_edit_rule")["rule"]
    assert reloaded["description"] == "编辑后说明"
    assert reloaded["attribute_points"] == 66
    assert reloaded["custom"] is True


def test_update_custom_d20_rule_validates_max_check_dc(web_api):
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    created = api.save_custom_rule({
        "source_rule_id": "freeform_fantasy",
        "rule_id": "custom_dc_rule",
        "rule_name": "自定义 DC 规则",
    })
    assert created["ok"] is True
    template = api.get_rule_template("custom_dc_rule")["rule"]
    template["max_check_dc"] = 30
    assert api.update_custom_rule("custom_dc_rule", template)["ok"] is True

    template["max_check_dc"] = 99
    rejected = api.update_custom_rule("custom_dc_rule", template)
    assert rejected["ok"] is False
    assert "max_check_dc" in rejected["error"]

    template["max_check_dc"] = 20
    template["dice_system"] = "2d6"
    rejected = api.update_custom_rule("custom_dc_rule", template)
    assert rejected["ok"] is False
    assert "dice_system" in rejected["error"]


@pytest.mark.asyncio
async def test_generate_rule_from_base_saves_valid_custom_rule(web_api):
    api, _lorebook, _registry, fake_llm, _worlds_dir = web_api

    result = await api.generate_rule("凡人修仙传式低资质散修成长", "freeform_fantasy")

    assert result["ok"] is True
    assert result["rule_id"].startswith("ai_rule_")
    path = api._rules_dir / f"{result['rule_id']}.json"
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["custom"] is True
    assert saved["source_rule_id"] == "freeform_fantasy"
    assert "凡人修仙" in saved["rule_name"]
    assert any("TRPG规则设计师" in c["system_prompt"] for c in fake_llm.calls)


def test_update_builtin_rule_is_rejected(web_api):
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    detail = api.get_rule_template("freeform_fantasy")

    result = api.update_custom_rule("freeform_fantasy", detail["rule"])

    assert result["ok"] is False
    assert "内置规则" in result["error"]


def test_rule_template_detail_includes_computed_ui_schema(web_api):
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api

    detail = api.get_rule_template("freeform_fantasy")

    assert detail["ok"] is True
    rule = detail["rule"]
    assert rule["currency_system"]["units"]
    assert rule["resource_schema"][0]["key"] == "hp"
    assert rule["identity_schema"][0]["legacy_field"] == "race"
    assert rule["progression_schema"]["type"]
    assert rule["ui_schema"]["primary_resources"] == ["hp"]
    assert detail["ruleset_runtime"]["id"] == "core:legacy"
    assert detail["ruleset_runtime"]["capabilities"]["character_builder"] == "legacy"


def test_rule_template_rejects_unavailable_explicit_runtime(web_api):
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    source = json.loads(
        (api._rules_dir / "freeform_fantasy.json").read_text(encoding="utf-8")
    )
    source["rule_id"] = "missing_runtime_rule"
    source["runtime"] = {"id": "missing:runtime", "minimum_version": 1}
    (api._rules_dir / "missing_runtime_rule.json").write_text(
        json.dumps(source), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="ruleset runtime is not available"):
        api.get_rule_template("missing_runtime_rule")
    with pytest.raises(ValueError, match="内容或运行时无效"):
        api.list_rules()


def test_delete_custom_rule_removes_only_custom_rule(web_api):
    api, _lorebook, _registry, _fake_llm, _worlds_dir = web_api
    created = api.save_custom_rule({
        "source_rule_id": "freeform_fantasy",
        "rule_id": "custom_delete_rule",
        "rule_name": "待删除规则",
    })
    assert created["ok"] is True

    deleted = api.delete_custom_rule("custom_delete_rule")

    assert deleted["ok"] is True
    assert api.get_rule_template("custom_delete_rule")["ok"] is False
    assert all(rule["rule_id"] != "custom_delete_rule" for rule in api.list_rules()["rules"])

    builtin = api.delete_custom_rule("freeform_fantasy")
    assert builtin["ok"] is False
    assert "内置规则" in builtin["error"]


def test_cleanup_orphan_legacy_copy_template_preserves_referenced_copy(web_api):
    api, _lorebook, registry, _fake_llm, worlds_dir = web_api
    world_id = "template_world_copy_1785176322339"
    path = worlds_dir / f"{world_id}.json"
    path.write_text(json.dumps({
        "world_id": world_id,
        "world_name": "贝克兰德（复制世界书）",
        "custom": True,
    }, ensure_ascii=False), encoding="utf-8")
    instance = SimpleNamespace(
        game_key=("web", "copy-user", "web_bot"),
        world_id=world_id,
    )
    registry.register(instance)

    assert api.cleanup_orphan_game_templates() == 0
    assert path.exists()

    registry.remove(instance.game_key)
    assert api.cleanup_orphan_game_templates() == 1
    assert not path.exists()


def test_cleanup_does_not_remove_user_template_that_only_looks_like_copy(web_api):
    api, _lorebook, _registry, _fake_llm, worlds_dir = web_api
    world_id = "my_world_copy_1785176322339"
    path = worlds_dir / f"{world_id}.json"
    path.write_text(json.dumps({
        "world_id": world_id,
        "world_name": "我主动保存的世界",
        "custom": True,
    }, ensure_ascii=False), encoding="utf-8")

    assert api.cleanup_orphan_game_templates() == 0
    assert path.exists()


def test_default_quick_actions_by_class():
    assert "攻击" in GameHandler._default_quick_actions_by_class("战士")
    assert "施法" in GameHandler._default_quick_actions_by_class("法师")
    assert "潜行" in GameHandler._default_quick_actions_by_class("盗贼")
    assert "治疗" in GameHandler._default_quick_actions_by_class("牧师")
    assert "射击" in GameHandler._default_quick_actions_by_class("游侠")
    assert "观察" in GameHandler._default_quick_actions_by_class("未知职业")


def test_delete_world_removes_user_template(web_api):
    api, lorebook, _registry, _fake_llm, worlds_dir = web_api
    write_world(worlds_dir, "ai_user_world", starter_lorebook=[{
        "id": "ai_user_world_npc1", "name": "测试NPC", "type": "npc",
        "keywords": ["测试"], "content": "内容", "tier": "core",
    }])
    lorebook.create_world("ai_user_world", "测试世界")
    lorebook.add_entry({
        "id": "ai_user_world_npc1", "world_id": "ai_user_world",
        "name": "测试NPC", "type": "npc", "keywords": ["测试"],
        "content": "内容", "tier": "core",
    })
    assert (worlds_dir / "ai_user_world.json").exists()

    api.delete_world("ai_user_world")

    assert not (worlds_dir / "ai_user_world.json").exists()


def test_delete_world_keeps_builtin_template(web_api):
    api, lorebook, _registry, _fake_llm, worlds_dir = web_api
    write_world(worlds_dir, "coc_horror", starter_lorebook=[{
        "id": "coc_horror_npc1", "name": "NPC", "type": "npc",
        "keywords": ["k"], "content": "c", "tier": "core",
    }])
    lorebook.create_world("coc_horror", "克苏鲁")
    lorebook.add_entry({
        "id": "coc_horror_npc1", "world_id": "coc_horror",
        "name": "NPC", "type": "npc", "keywords": ["k"],
        "content": "c", "tier": "core",
    })

    api.delete_world("coc_horror")

    assert (worlds_dir / "coc_horror.json").exists()


def test_save_entry_syncs_user_template_lorebook(web_api):
    api, lorebook, _registry, _fake_llm, worlds_dir = web_api
    write_world(worlds_dir, "ai_sync_world", starter_lorebook=[{
        "id": "ai_sync_world_old", "name": "旧条目", "type": "npc",
        "keywords": ["旧"], "content": "旧内容", "tier": "core",
    }])
    lorebook.create_world("ai_sync_world", "同步世界")
    lorebook.add_entry({
        "id": "ai_sync_world_old", "world_id": "ai_sync_world",
        "name": "旧条目", "type": "npc", "keywords": ["旧"],
        "content": "旧内容", "tier": "core",
    })

    api.save_entry({
        "id": "ai_sync_world_new", "world_id": "ai_sync_world",
        "name": "新条目", "type": "location", "keywords": ["新"],
        "content": "新内容", "tier": "background",
    })

    data = json.loads((worlds_dir / "ai_sync_world.json").read_text(encoding="utf-8"))
    ids = [e["id"] for e in data["starter_lorebook"]]
    assert "ai_sync_world_new" in ids
    assert "ai_sync_world_old" in ids
    for e in data["starter_lorebook"]:
        assert "world_id" not in e


def test_save_entry_skips_builtin_template(web_api):
    api, lorebook, _registry, _fake_llm, worlds_dir = web_api
    write_world(worlds_dir, "coc_sync", starter_lorebook=[{
        "id": "coc_sync_old", "name": "旧", "type": "npc",
        "keywords": ["k"], "content": "c", "tier": "core",
    }])
    lorebook.create_world("coc_sync", "克苏鲁同步")
    lorebook.add_entry({
        "id": "coc_sync_old", "world_id": "coc_sync",
        "name": "旧", "type": "npc", "keywords": ["k"],
        "content": "c", "tier": "core",
    })
    original = (worlds_dir / "coc_sync.json").read_text(encoding="utf-8")

    api.save_entry({
        "id": "coc_sync_new", "world_id": "coc_sync",
        "name": "新", "type": "location", "keywords": ["n"],
        "content": "new", "tier": "background",
    })

    assert (worlds_dir / "coc_sync.json").read_text(encoding="utf-8") == original


def test_save_entry_generates_id_when_missing(web_api):
    """UI 导入的 body 可能完全不带 id 键（undefined 被 JSON 丢弃），不能 500。"""
    api, lorebook, _registry, _fake_llm, _worlds_dir = web_api
    lorebook.create_world("import_world", "导入世界")

    result = api.save_entry({
        "world_id": "import_world", "name": "无ID条目", "type": "other",
        "keywords": ["k"], "content": "c", "tier": "background",
    })

    assert result.get("ok") is True
    assert result.get("entry_id")
    assert lorebook.get_entry(result["entry_id"]) is not None


def test_save_entry_rejects_bad_target(web_api):
    api, lorebook, _registry, _fake_llm, _worlds_dir = web_api
    lorebook.create_world("import_world2", "导入世界2")

    assert api.save_entry({"world_id": "missing_world", "name": "x"}).get("ok") is False
    assert api.save_entry({"world_id": "import_world2", "name": "   "}).get("ok") is False
    assert api.save_entry({"world_id": "", "name": "x"}).get("ok") is False


def test_import_entries_batches_large_lorebook_in_one_request(web_api):
    """issue #213：50+ 条的批量导入必须一次请求完成，不再逐条撞写频控。"""

    api, lorebook, _registry, _fake_llm, _worlds_dir = web_api
    lorebook.create_world("import_batch_world", "批量导入世界")

    entries = [
        {"name": f"条目{i}", "type": "location", "keywords": [f"关键词{i}"], "content": f"内容{i}"}
        for i in range(60)
    ]
    result = api.import_entries("import_batch_world", entries)

    assert result.get("ok") is True
    assert result.get("imported") == 60
    assert result.get("failed") == []
    assert lorebook.list_entries("import_batch_world").__len__() >= 60
    names = {e["name"] for e in lorebook.list_entries("import_batch_world")}
    assert {"条目0", "条目59"} <= names
    # 批量内同名条目生成不冲突的 id。
    assert len({e["id"] for e in lorebook.list_entries("import_batch_world")}) == len(
        lorebook.list_entries("import_batch_world")
    )


def test_import_entries_reports_per_entry_failures(web_api):
    api, lorebook, _registry, _fake_llm, _worlds_dir = web_api
    lorebook.create_world("import_partial_world", "部分失败世界")

    result = api.import_entries("import_partial_world", [
        {"name": "好条目", "content": "c", "keywords": ["k"]},
        {"name": "   ", "content": "c"},  # 名称为空
        {"name": "超长条目", "content": "x" * 5001},  # 内容超长
        {"name": "另一条", "content": "c"},
    ])

    assert result.get("ok") is True
    assert result.get("imported") == 2
    assert [f["index"] for f in result.get("failed", [])] == [1, 2]
    names = {e["name"] for e in lorebook.list_entries("import_partial_world")}
    assert {"好条目", "另一条"} <= names
    assert "超长条目" not in names


def test_batch_import_deduplicates_ids_within_same_batch(web_api):
    """同一导入文件内的重复 id 不得复用：后条重新生成，先条不被覆盖。"""

    api, lorebook, _registry, _fake_llm, _worlds_dir = web_api
    lorebook.create_world("dup_import_world", "重复ID世界")

    result = api.import_entries("dup_import_world", [
        {"id": "dup_entry", "name": "Village", "content": "村庄"},
        {"id": "dup_entry", "name": "Forest", "content": "森林"},
        {"name": "River", "content": "河流"},
        {"name": "River", "content": "另一条河"},
    ])

    assert result.get("ok") is True
    assert result.get("imported") == 4
    assert result.get("failed") == []
    entries = lorebook.list_entries("dup_import_world")
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids))
    by_name = {e["name"]: e for e in entries}
    assert by_name["Village"]["id"] == "dup_entry"
    assert by_name["Forest"]["id"] != "dup_entry"
    # 同名条目也各自拿到不同 id。
    rivers = [e for e in entries if e["name"] == "River"]
    assert len(rivers) == 2
    assert rivers[0]["id"] != rivers[1]["id"]
    assert by_name["Village"]["content"] == "村庄"


def test_import_entries_rejects_missing_world_and_oversize_batch(web_api):
    api, lorebook, _registry, _fake_llm, _worlds_dir = web_api
    lorebook.create_world("import_guard_world", "限额世界")

    assert api.import_entries("missing_world", [{"name": "x"}]).get("ok") is False
    assert api.import_entries("import_guard_world", []).get("ok") is False
    oversize = [
        {"name": f"条目{i}", "content": "c"} for i in range(501)
    ]
    result = api.import_entries("import_guard_world", oversize)
    assert result.get("ok") is False
    assert "上限" in str(result.get("error"))
