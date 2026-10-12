"""内置世界书内容迁移：老安装升级路径、幂等与用户编辑保护。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.lorebook.bootstrap import ensure_world_from_template, seed_builtin_worlds
from src.lorebook.store import LorebookStore
from src.migrations.lorebook_content import (
    LEGACY_BUNDLED_ENTRIES,
    LEGACY_BUNDLED_UPDATES,
    PROTECTED_FIELDS,
    _canonical_entry,
    maybe_upgrade_bundled_entry,
)

TEMPLATE = {
    "world_id": "demo_world",
    "world_name": "测试世界",
    "language": "zh-CN",
    "starter_lorebook": [
        {
            "id": "npc_pub", "name": "酒馆老板", "type": "npc", "keywords": ["老板"],
            "content": "新版本公开正文", "tier": "core", "visible_to": ["*"],
        },
        {
            "id": "loc_secret", "name": "暗巷", "type": "location", "keywords": ["暗巷"],
            "content": "秘密现场线索", "tier": "background", "visible_to": [],
        },
    ],
}

TEMPLATE_EN = {
    "world_id": "demo_world_en",
    "world_name": "Test World",
    "language": "en-US",
    "starter_lorebook": [
        {
            "id": "npc_pub", "name": "Innkeeper", "type": "npc", "keywords": ["innkeeper"],
            "content": "new public content", "tier": "core", "visible_to": ["*"],
        },
        {
            "id": "loc_en_secret", "name": "Dark Alley", "type": "location", "keywords": ["alley"],
            "content": "secret scene clue", "tier": "background", "visible_to": [],
        },
    ],
}

OLD_PUB_CONTENT = "旧版官方正文（重审计前）"

# 旧官方默认快照（demo_world / npc_pub）：除列出的字段外均为 schema 默认值
LEGACY_PUB_SNAPSHOT = {
    "name": "酒馆老板",
    "type": "npc",
    "keywords": ["老板"],
    "content": OLD_PUB_CONTENT,
    "tier": "core",
}

# #170 发布时冻结的 after payload：只含当时有意改变的字段，与实时模板无关
DEMO_PUB_UPDATE = {"content": "新版本公开正文", "visible_to": ["*"]}

# 用户可能只改一个非 content / visible_to 字段，迁移同样必须让路
USER_EDITS = {
    "name": "老板娘",
    "type": "location",
    "keywords": ["老板", "店长"],
    "tier": "background",
    "unreliable": True,
    "sync_on_enter": True,
    "triggers_recursive": ["老板"],
    "is_constant": True,
    "match_mode": "all",
    "sticky": 2,
    "cooldown": 3,
    "delay": 1,
    "order": 50,
    "probability": 80,
    "group": "inn",
    "group_weight": 3,
    "connected_to": ["loc_secret"],
}


def _register_legacy(world_id: str, entry_id: str, snapshot: dict) -> None:
    LEGACY_BUNDLED_ENTRIES.setdefault(world_id, {})[entry_id] = dict(snapshot)


def _register_update(world_id: str, entry_id: str, payload: dict) -> None:
    LEGACY_BUNDLED_UPDATES.setdefault(world_id, {})[entry_id] = dict(payload)


@pytest.fixture()
def store(tmp_path):
    store = LorebookStore(tmp_path / "lorebook.db")
    store.open()
    yield store
    store.close()


@pytest.fixture(autouse=True)
def clean_legacy_registry():
    """测试注入的 demo 快照不污染真实清单；真实清单在用例间保持只读。"""
    saved_entries = {k: v for k, v in LEGACY_BUNDLED_ENTRIES.items() if k.startswith("demo")}
    saved_updates = {k: v for k, v in LEGACY_BUNDLED_UPDATES.items() if k.startswith("demo")}
    for key in saved_entries:
        LEGACY_BUNDLED_ENTRIES.pop(key, None)
    for key in saved_updates:
        LEGACY_BUNDLED_UPDATES.pop(key, None)
    yield
    for key in list(LEGACY_BUNDLED_ENTRIES):
        if key.startswith("demo"):
            LEGACY_BUNDLED_ENTRIES.pop(key, None)
    for key in list(LEGACY_BUNDLED_UPDATES):
        if key.startswith("demo"):
            LEGACY_BUNDLED_UPDATES.pop(key, None)
    LEGACY_BUNDLED_ENTRIES.update(saved_entries)
    LEGACY_BUNDLED_UPDATES.update(saved_updates)


def _seed_old_state(store: LorebookStore) -> None:
    store.create_world("demo_world", "测试世界")
    store.add_entry({
        "id": "npc_pub", "world_id": "demo_world", "name": "酒馆老板",
        "type": "npc", "keywords": ["老板"], "content": OLD_PUB_CONTENT,
        "tier": "core", "visible_to": [],
    })


def _entry_of(store: LorebookStore, entry_id: str) -> dict:
    entry = store.get_entry(entry_id)
    assert entry is not None, f"entry {entry_id} missing"
    return entry


def _old_entry_from_snapshot(world_id: str, entry_id: str) -> dict:
    """按真实旧官方快照构造老安装条目（缺省字段即 schema 默认值）。"""
    from src.migrations.lorebook_content import _canonical_entry

    canonical = _canonical_entry(LEGACY_BUNDLED_ENTRIES[world_id][entry_id])
    return {"id": entry_id, "world_id": world_id, **canonical}


def test_unchanged_old_entry_upgrades_and_new_secret_entry_is_added(store):
    _register_legacy("demo_world", "npc_pub", LEGACY_PUB_SNAPSHOT)
    _register_update("demo_world", "npc_pub", DEMO_PUB_UPDATE)
    _seed_old_state(store)

    inserted = ensure_world_from_template(store, "demo_world", TEMPLATE)

    upgraded = _entry_of(store, "npc_pub")
    assert upgraded["content"] == "新版本公开正文"
    assert upgraded["visible_to"] == ["*"]
    # 新拆出的秘密条目按新 id 正常新增
    assert inserted == 1
    assert _entry_of(store, "loc_secret")["visible_to"] == []


def test_user_edited_content_is_never_touched(store):
    _register_legacy("demo_world", "npc_pub", LEGACY_PUB_SNAPSHOT)
    _register_update("demo_world", "npc_pub", DEMO_PUB_UPDATE)
    store.create_world("demo_world", "测试世界")
    store.add_entry({
        "id": "npc_pub", "world_id": "demo_world", "name": "酒馆老板",
        "type": "npc", "keywords": ["老板"], "content": "用户自己重写的正文",
        "tier": "core", "visible_to": [],
    })

    ensure_world_from_template(store, "demo_world", TEMPLATE)

    upgraded = _entry_of(store, "npc_pub")
    assert upgraded["content"] == "用户自己重写的正文"
    assert upgraded["visible_to"] == []


def test_user_visibility_decision_is_respected(store):
    _register_legacy("demo_world", "npc_pub", LEGACY_PUB_SNAPSHOT)
    _register_update("demo_world", "npc_pub", DEMO_PUB_UPDATE)
    store.create_world("demo_world", "测试世界")
    store.add_entry({
        "id": "npc_pub", "world_id": "demo_world", "name": "酒馆老板",
        "type": "npc", "keywords": ["老板"], "content": OLD_PUB_CONTENT,
        "tier": "core", "visible_to": ["莱拉"],
    })

    ensure_world_from_template(store, "demo_world", TEMPLATE)

    upgraded = _entry_of(store, "npc_pub")
    assert upgraded["content"] == OLD_PUB_CONTENT
    assert upgraded["visible_to"] == ["莱拉"]


@pytest.mark.parametrize(("field", "value"), sorted(USER_EDITS.items()), ids=sorted(USER_EDITS))
def test_user_edited_metadata_field_is_never_touched(store, field, value):
    """只改 name / keywords / type / tier / 触发元数据等任意一个字段 → 迁移让路。"""
    _register_legacy("demo_world", "npc_pub", LEGACY_PUB_SNAPSHOT)
    _register_update("demo_world", "npc_pub", DEMO_PUB_UPDATE)
    store.create_world("demo_world", "测试世界")
    entry = {
        "id": "npc_pub", "world_id": "demo_world", "name": "酒馆老板",
        "type": "npc", "keywords": ["老板"], "content": OLD_PUB_CONTENT,
        "tier": "core", "visible_to": [],
    }
    entry[field] = value
    store.add_entry(entry)

    ensure_world_from_template(store, "demo_world", TEMPLATE)

    upgraded = _entry_of(store, "npc_pub")
    assert upgraded["content"] == OLD_PUB_CONTENT
    assert upgraded["visible_to"] == []
    assert upgraded[field] == value


def test_migration_is_idempotent(store):
    _register_legacy("demo_world", "npc_pub", LEGACY_PUB_SNAPSHOT)
    _register_update("demo_world", "npc_pub", DEMO_PUB_UPDATE)
    _seed_old_state(store)

    ensure_world_from_template(store, "demo_world", TEMPLATE)
    first = _entry_of(store, "npc_pub")
    assert first["visible_to"] == ["*"]

    ensure_world_from_template(store, "demo_world", TEMPLATE)
    assert _entry_of(store, "npc_pub") == first


def test_fresh_install_seeds_current_template(store):
    inserted = ensure_world_from_template(store, "demo_world", TEMPLATE)

    assert inserted == 2
    pub = _entry_of(store, "npc_pub")
    assert pub["content"] == "新版本公开正文"
    assert pub["visible_to"] == ["*"]
    assert _entry_of(store, "loc_secret")["visible_to"] == []


def test_renamed_cross_language_copy_is_upgraded(store):
    """zh/en 模板共享条目 id 时，后 seed 的一方被改名前缀存储，迁移也要覆盖。"""
    _register_legacy("demo_world", "npc_pub", LEGACY_PUB_SNAPSHOT)
    _register_update("demo_world", "npc_pub", DEMO_PUB_UPDATE)
    _register_legacy("demo_world_en", "npc_pub", {
        "name": "Innkeeper", "type": "npc", "keywords": ["innkeeper"],
        "content": "old public content", "tier": "core",
    })
    _register_update("demo_world_en", "npc_pub", {
        "content": "new public content", "visible_to": ["*"],
    })
    store.create_world("demo_world", "测试世界")
    store.add_entry({
        "id": "npc_pub", "world_id": "demo_world", "name": "酒馆老板",
        "type": "npc", "keywords": ["老板"], "content": OLD_PUB_CONTENT,
        "tier": "core", "visible_to": [],
    })
    store.create_world("demo_world_en", "Test World")
    store.add_entry({
        "id": "demo_world_en_npc_pub", "world_id": "demo_world_en", "name": "Innkeeper",
        "type": "npc", "keywords": ["innkeeper"], "content": "old public content",
        "tier": "core", "visible_to": [],
    })

    ensure_world_from_template(store, "demo_world", TEMPLATE)
    ensure_world_from_template(store, "demo_world_en", TEMPLATE_EN)

    assert _entry_of(store, "npc_pub")["content"] == "新版本公开正文"
    en_copy = _entry_of(store, "demo_world_en_npc_pub")
    assert en_copy["content"] == "new public content"
    assert en_copy["visible_to"] == ["*"]


def test_real_template_migration_on_coc_horror(store):
    """真实模板 + 真实清单：内容未变的公开条目升级后仅可见性翻转。"""
    template_path = Path("templates/worlds/coc_horror.json")
    template = json.loads(template_path.read_text(encoding="utf-8"))
    target = next(e for e in template["starter_lorebook"] if e["id"] == "loc_arkham")

    store.create_world("coc_horror", "克苏鲁恐怖·阿卡姆疑云")
    store.add_entry({
        "id": "loc_arkham", "world_id": "coc_horror", "name": target["name"],
        "type": "location", "keywords": target["keywords"], "content": target["content"],
        "tier": target.get("tier", "background"), "visible_to": [],
    })

    ensure_world_from_template(store, "coc_horror", template)

    upgraded = _entry_of(store, "loc_arkham")
    assert upgraded["visible_to"] == ["*"]
    assert upgraded["content"] == target["content"]


def test_real_template_skips_user_renamed_entry(store):
    """真实数据保护：用户改过名字的旧官方条目绝不被升级。"""
    template_path = Path("templates/worlds/coc_horror.json")
    template = json.loads(template_path.read_text(encoding="utf-8"))
    old_entry = _old_entry_from_snapshot("coc_horror", "loc_howard_house")
    old_entry["name"] = "我改过的宅子"

    store.create_world("coc_horror", "克苏鲁恐怖·阿卡姆疑云")
    store.add_entry(old_entry)

    ensure_world_from_template(store, "coc_horror", template)

    upgraded = _entry_of(store, "loc_howard_house")
    assert upgraded["name"] == "我改过的宅子"
    assert upgraded["content"] == old_entry["content"]
    assert upgraded["visible_to"] == []


def test_real_seed_builtin_worlds_upgrades_old_install(store, tmp_path):
    """端到端：seed_builtin_worlds 在老安装上同时完成升级与新秘密条目新增。"""
    template_path = Path("templates/worlds/coc_horror.json")
    template = json.loads(template_path.read_text(encoding="utf-8"))
    # 老安装里存的是拆分前的原始全文（清单里记录的正是这份原文）
    legacy_content = LEGACY_BUNDLED_ENTRIES["coc_horror"]["loc_howard_house"]["content"]

    worlds_dir = tmp_path / "worlds"
    worlds_dir.mkdir()
    (worlds_dir / "coc_horror.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")

    store.create_world("coc_horror", "克苏鲁恐怖·阿卡姆疑云")
    store.add_entry(_old_entry_from_snapshot("coc_horror", "loc_howard_house"))
    assert store.get_entry("loc_howard_house")["content"] == legacy_content

    seed_builtin_worlds(store, worlds_dir)

    upgraded = _entry_of(store, "loc_howard_house")
    assert upgraded["visible_to"] == ["*"]
    assert "上了锁的工具棚" not in upgraded["content"]
    oddities = _entry_of(store, "loc_howard_house_oddities")
    assert oddities and oddities["visible_to"] == []


def test_real_template_upgrades_missed_tavern_entries(store):
    """回归：tavern 的公开化曾漏出迁移清单。

    tavern 模板是 deprecated 世界（seed_builtin_worlds 会跳过），但按模板
    创建游戏时 game_factory 仍会走 ensure_world_from_template，老官方条目
    在这条路径上升级。
    """
    template = json.loads(
        Path("templates/worlds/tavern_generic.json").read_text(encoding="utf-8"))
    target = next(e for e in template["starter_lorebook"] if e["id"] == "tavern_place")

    store.create_world("tavern_generic", "十字路口酒馆")
    store.add_entry(_old_entry_from_snapshot("tavern_generic", "tavern_place"))

    ensure_world_from_template(store, "tavern_generic", template)

    upgraded = _entry_of(store, "tavern_place")
    assert upgraded["visible_to"] == ["*"]
    assert upgraded["content"] == target["content"]


def test_legacy_snapshot_registry_matches_current_templates():
    """清单与模板的防漂移约束：快照必须能对上现行模板，且确有升级要做。"""
    for world_id, entries in LEGACY_BUNDLED_ENTRIES.items():
        template_path = Path(f"templates/worlds/{world_id}.json")
        assert template_path.is_file(), f"missing template for {world_id}"
        template = json.loads(template_path.read_text(encoding="utf-8"))
        assert template.get("world_id") == world_id
        current = {e["id"]: e for e in template.get("starter_lorebook", []) if e.get("id")}
        for entry_id, snapshot in entries.items():
            assert entry_id in current, f"{world_id}/{entry_id} not in current template"
            bundled = current[entry_id]
            recorded = _canonical_entry(snapshot)
            target = _canonical_entry(bundled)
            assert any(recorded[f] != target[f] for f in PROTECTED_FIELDS), (
                f"{world_id}/{entry_id}: snapshot equals current template, migration is dead weight"
            )


def test_frozen_update_registry_pairs_with_before_snapshots():
    """冻结 payload 与 before 快照一一配对，且每个字段都确实改变目标状态。"""
    assert set(LEGACY_BUNDLED_UPDATES) == set(LEGACY_BUNDLED_ENTRIES)
    for world_id, entries in LEGACY_BUNDLED_UPDATES.items():
        assert set(entries) == set(LEGACY_BUNDLED_ENTRIES[world_id]), world_id
        for entry_id, payload in entries.items():
            assert payload, f"{world_id}/{entry_id}: empty payload"
            recorded = _canonical_entry(LEGACY_BUNDLED_ENTRIES[world_id][entry_id])
            for field, value in payload.items():
                assert field in PROTECTED_FIELDS, f"{world_id}/{entry_id}: unknown field {field}"
                canonical = _canonical_entry({field: value})[field]
                assert canonical != recorded[field], (
                    f"{world_id}/{entry_id}: payload {field} would be a no-op"
                )


def test_frozen_target_ignores_future_template_changes(store):
    """回归：未来模板演进不得追溯改写已发布迁移的结果。

    即使传入模板把 name / keywords / order / content 改成未来版本，旧官方
    条目也必须迁移到迁移发布时冻结的 after 状态，而不是未来模板状态。
    """
    _register_legacy("demo_world", "npc_pub", LEGACY_PUB_SNAPSHOT)
    _register_update("demo_world", "npc_pub", DEMO_PUB_UPDATE)
    _register_legacy("demo_world", "loc_future", {
        "name": "旧地点", "type": "location", "keywords": ["旧地点"],
        "content": "旧版官方地点正文", "tier": "core",
    })
    _register_update("demo_world", "loc_future", {"visible_to": ["*"]})

    store.create_world("demo_world", "测试世界")
    store.add_entry({
        "id": "npc_pub", "world_id": "demo_world", "name": "酒馆老板",
        "type": "npc", "keywords": ["老板"], "content": OLD_PUB_CONTENT,
        "tier": "core", "visible_to": [],
    })
    store.add_entry({
        "id": "loc_future", "world_id": "demo_world", "name": "旧地点",
        "type": "location", "keywords": ["旧地点"], "content": "旧版官方地点正文",
        "tier": "core", "visible_to": [],
    })

    future_template = {
        "world_id": "demo_world",
        "world_name": "测试世界",
        "language": "zh-CN",
        "starter_lorebook": [
            {
                "id": "npc_pub", "name": "未来模板改名", "type": "npc",
                "keywords": ["未来关键词"], "content": "未来模板的新正文",
                "tier": "core", "order": 7, "visible_to": ["*"],
            },
            {
                "id": "loc_future", "name": "未来模板地点", "type": "location",
                "keywords": ["未来"], "content": "未来模板地点正文",
                "tier": "background", "visible_to": ["*"],
            },
        ],
    }

    ensure_world_from_template(store, "demo_world", future_template)

    pub = _entry_of(store, "npc_pub")
    assert pub["visible_to"] == ["*"]
    # 冻结 after 状态：内容来自 payload，不是未来模板的重写正文
    assert pub["content"] == "新版本公开正文"
    # payload 未涉及的字段不被未来模板牵动
    assert pub["name"] == "酒馆老板"
    assert pub["keywords"] == ["老板"]
    assert pub["order"] == 100

    loc = _entry_of(store, "loc_future")
    assert loc["visible_to"] == ["*"]
    # visibility-only payload：未来模板的新正文不得覆盖存量官方正文
    assert loc["content"] == "旧版官方地点正文"


def test_maybe_upgrade_ignores_unknown_and_foreign_entries(store):
    """不在清单内 / 属于别的世界的条目一律不动。"""
    _register_legacy("demo_world", "npc_pub", LEGACY_PUB_SNAPSHOT)
    _register_update("demo_world", "npc_pub", DEMO_PUB_UPDATE)
    store.create_world("other_world", "别的世界")
    store.add_entry({
        "id": "npc_pub", "world_id": "other_world", "name": "酒馆老板",
        "type": "npc", "keywords": ["老板"], "content": OLD_PUB_CONTENT,
        "tier": "core", "visible_to": [],
    })

    maybe_upgrade_bundled_entry(store, "demo_world", "npc_pub", {
        "id": "npc_pub", "name": "酒馆老板", "type": "npc", "keywords": ["老板"],
        "content": "新版本公开正文", "tier": "core", "visible_to": ["*"],
    })

    upgraded = _entry_of(store, "npc_pub")
    assert upgraded["world_id"] == "other_world"
    assert upgraded["content"] == OLD_PUB_CONTENT
