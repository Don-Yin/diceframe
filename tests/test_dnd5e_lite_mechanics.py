"""D&D 5e Lite 规则化整改回归：伤害/护甲/暴击/DC 均按规则 capability 驱动。

通用 d20（base_d20/freeform_fantasy）保持旧版 hp_based 语义；
dnd5e 三语模板 mechanics 必须一致。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.commands.combat_resolver import CombatResolver
from src.engine.character_utils import build_starter_items
from src.engine.checks import _attack_target_dc, resolve_check_request
from src.engine.combat import calc_hp_based_damage, resolve_attack
from src.engine.dice import d20_dc_cap
from src.engine.game_instance import GameInstance
from src.rules.rule_system import RuleSystem
from src.engine.modules import checks

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "templates" / "rules"
LEGACY_RULES = ROOT / "tests" / "fixtures" / "legacy_rules"


def _rule(name: str) -> RuleSystem:
    path = Path(name)
    return RuleSystem.load(path if path.is_absolute() else (ROOT / path if path.parts[0] == "tests" else RULES / path))


def test_dnd5e_declares_lite_mechanics_and_base_d20_keeps_legacy() -> None:
    dnd = _rule("dnd5e.json")
    assert dnd.damage_mechanic == {
        "armor_reduces_damage": False,
        "degree_affects_damage": False,
        "critical_damage": "double_damage_dice",
        "minimum_damage": 0,
    }
    assert dnd.armor_model == "category_lite"
    assert d20_dc_cap(dnd) == 30

    base = _rule("base_d20.json")
    assert base.damage_mechanic == {
        "armor_reduces_damage": True,
        "degree_affects_damage": True,
        "critical_damage": "double_total",
        "minimum_damage": 1,
    }
    assert base.armor_model == "sum"
    assert d20_dc_cap(base) == 20


def test_dnd5e_mechanics_identical_across_languages() -> None:
    zh = json.loads((RULES / "dnd5e.json").read_text(encoding="utf-8"))
    en = json.loads((LEGACY_RULES / "dnd5e_en.json").read_text(encoding="utf-8"))
    ja = json.loads((LEGACY_RULES / "dnd5e_ja.json").read_text(encoding="utf-8"))
    keys = ["check_mechanic", "armor_model", "max_check_dc", "dc_table", "death_mechanic"]
    for other in (en, ja):
        for key in keys:
            assert zh[key] == other[key], key
        # V1 full copies retain their historical 1-point floor; every other
        # D&D mechanic remains compatible.
        assert {
            key: value for key, value in zh["damage_mechanic"].items()
            if key != "minimum_damage"
        } == other["damage_mechanic"]


def test_legacy_fixed_damage_path_unchanged() -> None:
    check = {"verdict": "成功", "is_critical": True, "dice_system": "d20", "total": 20}
    # 旧版：总值×2（含修正），再减护甲
    assert calc_hp_based_damage(7, 1, 2, check) == (7 + 1) * 2 - 2
    # 程度成功追加
    normal = {"verdict": "成功", "is_critical": False, "dice_system": "d20", "total": 19}
    assert calc_hp_based_damage(7, 1, 2, normal) == 7 + 1 + (19 - 10) // 3 - 2


def test_dnd5e_armor_does_not_reduce_and_degree_does_not_add() -> None:
    dnd = _rule("dnd5e.json")
    mech = dnd.damage_mechanic
    normal = {"verdict": "成功", "is_critical": False, "dice_system": "d20", "total": 25}
    # 高总值不追加伤害；护甲不减伤
    assert calc_hp_based_damage(7, 1, 5, normal, mechanic=mech) == 8


def test_dnd5e_allows_zero_damage_after_negative_modifier() -> None:
    dnd = _rule("dnd5e.json")
    normal = {"verdict": "成功", "is_critical": False, "dice_system": "d20", "total": 12}

    assert calc_hp_based_damage(1, -3, 0, normal, mechanic=dnd.damage_mechanic) == 0
    assert calc_hp_based_damage(1, -3, 0, normal) == 1


def test_dnd5e_critical_doubles_damage_dice_only(monkeypatch) -> None:
    dnd = _rule("dnd5e.json")
    target = {
        "character_name": "靶子",
        "attributes": {"dex": 10},
        "equipment": [{"name": "皮甲", "armor": 2}],
        "hp": 50,
        "max_hp": 50,
    }
    weapon = {"name": "长剑", "damage": 7, "damage_dice": "1d8"}
    check = {"check_id": "c1", "verdict": "成功", "is_critical": True, "dice_system": "d20"}
    rolls = iter([5, 7])
    monkeypatch.setattr("random.randint", lambda _a, _b: next(rolls))

    result = resolve_attack(
        "攻击者", target, weapon, attr_value=12, check_result=check, rule=dnd
    )

    # 5+7 伤害骰 + 1 属性修正；护甲不再减伤；固定修正不翻倍
    assert result.actual_damage == 13


def test_dnd5e_non_critical_rolls_single_damage_die(monkeypatch) -> None:
    dnd = _rule("dnd5e.json")
    target = {"character_name": "靶子", "attributes": {"dex": 10}, "hp": 50, "max_hp": 50}
    weapon = {"name": "长剑", "damage": 7, "damage_dice": "1d8"}
    check = {"check_id": "c2", "verdict": "成功", "is_critical": False, "dice_system": "d20"}
    rolls = iter([5])
    monkeypatch.setattr("random.randint", lambda _a, _b: next(rolls))

    result = resolve_attack(
        "攻击者", target, weapon, attr_value=12, check_result=check, rule=dnd
    )

    assert result.actual_damage == 6


def test_category_lite_ac_by_armor_category() -> None:
    dnd = _rule("dnd5e.json")
    dex18 = {"dex": 18}  # 修正 +4
    dex8 = {"dex": 8}  # 修正 -1

    unarmored = _attack_target_dc(dnd, {"attributes": dex18, "equipment": []})
    assert unarmored == 14  # 10 + 4

    light = _attack_target_dc(
        dnd, {"attributes": dex18, "equipment": [{"name": "皮甲"}, {"name": "盾牌"}]}
    )
    assert light == 11 + 4 + 2

    chain_mail = _attack_target_dc(
        dnd, {"attributes": dex18, "equipment": [{"name": "链甲"}, {"name": "盾牌"}]}
    )
    assert chain_mail == 16 + 2  # Chain Mail is heavy armor; DEX is ignored

    heavy = _attack_target_dc(dnd, {"attributes": dex18, "equipment": [{"name": "板甲"}]})
    assert heavy == 18  # 重甲不吃 DEX

    assert _attack_target_dc(dnd, {"attributes": dex8, "equipment": []}) == 9
    assert _attack_target_dc(dnd, {"attributes": dex8, "equipment": [{"name": "皮甲"}]}) == 10
    assert _attack_target_dc(dnd, {"attributes": dex8, "equipment": [{"name": "链甲"}]}) == 16
    assert _attack_target_dc(
        dnd, {"attributes": dex8, "equipment": [{"name": "链甲"}, {"name": "盾牌"}]}
    ) == 18


def test_v2_dnd_armor_uses_canonical_equipment_not_legacy_table(monkeypatch) -> None:
    """V2 starter items retain AC mechanics after the legacy lookup is gone."""
    dnd = _rule("dnd5e.json")
    equipment, _ = build_starter_items(dnd, "战士")
    monkeypatch.setattr("src.engine.constants.ARMOR_LITE", {})

    chain_mail = next(item for item in equipment if item["item_key"] == "chain_mail")
    shield = next(item for item in equipment if item["item_key"] == "shield")
    assert chain_mail == {
        "name": "链甲", "type": "armor", "slot": "armor", "quality": "common",
        "item_key": "chain_mail", "armor_category": "heavy", "ac_base": 16, "dex_cap": 0,
    }
    assert shield["ac_bonus"] == 2
    assert _attack_target_dc(dnd, {"attributes": {"dex": 8}, "equipment": equipment}) == 18


def test_category_lite_keeps_name_only_armor_as_legacy_fallback() -> None:
    dnd = _rule("dnd5e.json")
    # Old saves predate canonical armor fields and must retain their old AC.
    assert _attack_target_dc(
        dnd, {"attributes": {"dex": 18}, "equipment": [{"name": "链甲"}, {"name": "盾牌"}]}
    ) == 18


def test_legacy_rules_keep_sum_armor_ac(tmp_path) -> None:
    rule_file = tmp_path / "sum_armor.json"
    rule_file.write_text(
        json.dumps(
            {
                "rule_id": "sum_armor",
                "dice_system": "d20",
                "attributes": [{"key": "dex", "name": "敏捷", "min": 3, "max": 20}],
                "check_mechanic": {
                    "dice": "d20",
                    "comparison": "roll_plus_modifier_gte_target",
                    "critical": {},
                    "attack_target": {"type": "armor_class", "base": 10, "attribute": "dex"},
                },
            }
        ),
        encoding="utf-8",
    )
    rule = RuleSystem.load(rule_file)
    total = _attack_target_dc(
        rule, {"attributes": {"dex": 18}, "equipment": [{"name": "皮甲", "armor": 2}]}
    )
    assert total == 10 + 4 + 2


def test_starter_items_carry_damage_dice_for_known_weapons() -> None:
    dnd = _rule("dnd5e.json")
    equip, _inv = build_starter_items(dnd, "战士")
    sword = next(item for item in equip if item["name"] == "长剑")
    assert sword["damage_dice"] == "1d8"


@pytest.mark.parametrize("locale", ["zh-CN", "en", "ja"])
def test_every_dnd_class_starter_item_has_a_canonical_identity(locale: str) -> None:
    from src.rules.loader import RuleBundleLoader

    rule = RuleSystem(RuleBundleLoader().load_rule(RULES, "dnd5e", locale))
    for class_data in rule.classes:
        equipment, inventory = build_starter_items(rule, str(class_data["id"]))
        assert equipment or inventory, class_data["id"]
        for item in equipment + inventory:
            assert item.get("item_key"), (locale, class_data["id"], item)
            assert item["name"] != item["item_key"]


@pytest.mark.parametrize(
    ("locale", "class_name", "sword_name", "armor_name", "spellbook_name"),
    [
        ("zh-CN", "战士", "铁剑", "皮甲", "法术书"),
        ("en", "Warrior", "Iron Sword", "Leather Armor", "Spellbook"),
        ("ja", "戦士", "鉄の剣", "革鎧", "魔法書"),
    ],
)
def test_freeform_fantasy_starter_items_use_declared_types(
    locale: str, class_name: str, sword_name: str, armor_name: str, spellbook_name: str,
) -> None:
    """Built-in Fantasy equipment must not use the legacy damage-name fallback."""
    rule_path = RULES / "freeform_fantasy.json" if locale == "zh-CN" else RULES / "locales" / locale / "freeform_fantasy.json"
    rule = RuleSystem.load(rule_path)
    equipment, inventory = build_starter_items(rule, class_name)

    sword = next(item for item in equipment if item["name"] == sword_name)
    armor = next(item for item in equipment if item["name"] == armor_name)
    assert sword["type"] == "weapon"
    assert sword["item_key"] == "iron_sword"
    assert armor["type"] == "armor"
    assert armor["item_key"] == "leather_armor"
    assert armor["armor"] == 2
    assert all(item["name"] != armor_name for item in inventory)

    mage_rule = RuleSystem.load(rule_path)
    _mage_equipment, mage_inventory = build_starter_items(
        mage_rule, {"zh-CN": "法师", "en": "Mage", "ja": "魔術師"}[locale]
    )
    assert any(item["name"] == spellbook_name for item in mage_inventory)


@pytest.mark.parametrize(
    ("rule_file", "class_name", "weapon_name", "shield_name", "armor_name"),
    [
        ("dnd5e.json", "战士", "长剑", "盾牌", "链甲"),
        (str(LEGACY_RULES / "dnd5e_en.json"), "Fighter", "Longsword", "Shield", "Chain Mail"),
        (str(LEGACY_RULES / "dnd5e_ja.json"), "ファイター", "ロングソード", "盾", "チェインメイル"),
    ],
)
def test_dnd_fighter_starter_equipment_is_equipped_in_all_languages(
    rule_file: str,
    class_name: str,
    weapon_name: str,
    shield_name: str,
    armor_name: str,
) -> None:
    rule = RuleSystem.load(Path(rule_file) if "/" in rule_file or "\\" in rule_file else RULES / rule_file)
    equipment, inventory = build_starter_items(rule, class_name)

    assert not inventory
    assert next(item for item in equipment if item["name"] == weapon_name)["slot"] == "main_hand"
    assert next(item for item in equipment if item["name"] == shield_name)["slot"] == "off_hand"
    assert next(item for item in equipment if item["name"] == armor_name)["slot"] == "armor"
    assert _attack_target_dc(rule, {"attributes": {"dex": 18}, "equipment": equipment}) == 18
    assert next(item for item in equipment if item["name"] == weapon_name)["item_key"] == "longsword"
    assert next(item for item in equipment if item["name"] == armor_name)["item_key"] == "chain_mail"


@pytest.mark.parametrize(
    ("rule_file", "class_name", "focus_name"),
    [
        ("dnd5e.json", "术士", "法器"),
        (str(LEGACY_RULES / "dnd5e_en.json"), "Sorcerer", "Arcane Focus"),
        (str(LEGACY_RULES / "dnd5e_ja.json"), "ソーサラー", "秘術焦点"),
    ],
)
def test_dnd_sorcerer_dict_starter_focus_is_canonical_and_nonweapon(
    rule_file: str, class_name: str, focus_name: str
) -> None:
    equipment, inventory = build_starter_items(_rule(rule_file), class_name)
    names = [str(item.get("name")) for item in equipment + inventory]

    assert names.count(focus_name) == 1
    assert "name" not in names and "description" not in names
    focus = next(item for item in equipment if item["name"] == focus_name)
    assert focus["item_key"] == "arcane_focus"
    assert focus["type"] != "weapon"
    assert "damage_dice" not in focus


def test_legacy_sum_rule_keeps_arcane_focus_name_compatibility(tmp_path) -> None:
    rule_file = tmp_path / "legacy_focus.json"
    rule_file.write_text(
        json.dumps({
            "rule_id": "legacy_focus",
            "dice_system": "d20",
            "armor_model": "sum",
            "item_categories": {"equipment": ["法器"]},
            "classes": [{"name": "施法者", "starter_equipment": ["法器"]}],
        }),
        encoding="utf-8",
    )
    equipment, inventory = build_starter_items(RuleSystem.load(rule_file), "施法者")
    assert not inventory
    assert equipment[0]["name"] == "法器"
    assert equipment[0]["type"] == "weapon"
    assert equipment[0]["damage"] == 3


def _combat_instance(*, weapon: dict, attributes: dict[str, int], check: dict) -> GameInstance:
    instance = GameInstance(game_key=("test", "dnd-combat", "bot"), rule_id="dnd5e")
    instance.players["fighter"] = {
        "character_name": "Fighter",
        "character_sheet": {
            "attributes": attributes,
            "equipment": [weapon],
            "hp": 20,
            "max_hp": 20,
        },
    }
    instance.npcs["target"] = {"name": "Target", "hp": 50, "max_hp": 50, "attributes": {"dex": 10}}
    request = {
        "check_id": check["check_id"],
        "actor_uid": "fighter",
        "kind": "attack",
        "opponent": "npc:target",
        "attribute": check.get("attribute_key", "str"),
    }
    instance.action_queue = [{"user_id": "fighter", "text": "I attack Target.", "check_request": request}]
    checks.replace_last_checks(instance, [check])
    return instance


def test_combat_resolver_preserves_equipped_damage_dice(monkeypatch) -> None:
    rule = _rule("dnd5e.json")
    check = {
        "check_id": "real-damage-die", "actor_uid": "fighter", "kind": "attack",
        "opponent": "npc:target", "attribute_key": "str", "verdict": "成功",
        "dice": "d20", "roll": 16, "total": 19, "is_critical": False, "is_fumble": False,
    }
    instance = _combat_instance(
        weapon={"name": "长剑", "damage": 7, "damage_dice": "1d8", "slot": "main_hand"},
        attributes={"str": 16},
        check=check,
    )
    monkeypatch.setattr("random.randint", lambda _a, _b: 5)

    CombatResolver().resolve_combat(instance, "", "hp_based", rule)

    assert instance.npcs["target"]["hp"] == 42  # 1d8(5) + STR(3), not fixed 7


def test_combat_resolver_critical_doubles_only_equipped_damage_dice(monkeypatch) -> None:
    rule = _rule("dnd5e.json")
    check = {
        "check_id": "real-critical-die", "actor_uid": "fighter", "kind": "attack",
        "opponent": "npc:target", "attribute_key": "str", "verdict": "成功",
        "dice": "d20", "roll": 20, "total": 23, "is_critical": True, "is_fumble": False,
    }
    instance = _combat_instance(
        weapon={"name": "长剑", "damage": 7, "damage_dice": "1d8", "slot": "main_hand"},
        attributes={"str": 16},
        check=check,
    )
    rolls = iter([5, 7])
    monkeypatch.setattr("random.randint", lambda _a, _b: next(rolls))

    CombatResolver().resolve_combat(instance, "", "hp_based", rule)

    assert instance.npcs["target"]["hp"] == 35  # 2d8(12) + STR(3)


def test_dnd_critical_without_damage_dice_keeps_fixed_damage_single() -> None:
    dnd = _rule("dnd5e.json")
    target = {"hp": 50, "max_hp": 50}
    result = resolve_attack(
        "Fighter", target, {"name": "legacy sword", "damage": 7}, attr_value=12,
        check_result={"check_id": "legacy-critical", "verdict": "成功", "is_critical": True}, rule=dnd,
    )
    assert result.actual_damage == 8


def test_dnd_invalid_damage_dice_uses_fixed_compatibility_fallback() -> None:
    dnd = _rule("dnd5e.json")
    result = resolve_attack(
        "Fighter", {"hp": 50, "max_hp": 50},
        {"name": "legacy sword", "damage": 7, "damage_dice": "not-a-die"}, attr_value=12,
        check_result={"check_id": "invalid-die", "verdict": "成功", "is_critical": True}, rule=dnd,
    )
    assert result.actual_damage == 8


def test_combat_resolver_uses_attack_check_attribute_for_damage(monkeypatch) -> None:
    rule = _rule("dnd5e.json")
    check = {
        "check_id": "longbow-dex", "actor_uid": "fighter", "kind": "attack",
        "opponent": "npc:target", "attribute_key": "dex", "verdict": "成功",
        "dice": "d20", "roll": 15, "total": 18, "is_critical": False, "is_fumble": False,
    }
    instance = _combat_instance(
        weapon={"name": "Longbow", "damage": 6, "damage_dice": "1d8", "slot": "main_hand"},
        attributes={"str": 8, "dex": 16},
        check=check,
    )
    monkeypatch.setattr("random.randint", lambda _a, _b: 4)

    CombatResolver().resolve_combat(instance, "", "hp_based", rule)

    assert instance.npcs["target"]["hp"] == 43  # 1d8(4) + DEX(3), never STR(-1)


def test_combat_weapon_selection_uses_only_server_equipment() -> None:
    resolver = CombatResolver()
    no_weapon, no_weapon_name = resolver._weapon({"equipment": []}, "我用巨剑攻击")
    assert no_weapon is None and no_weapon_name == "徒手"

    sheet = {
        "equipment": [
            {"name": "Longsword", "type": "weapon", "slot": "main_hand", "damage": 7},
            {"name": "Longbow", "type": "weapon", "damage": 6},
        ]
    }
    selected, name = resolver._weapon(sheet, "I shoot with my Longbow")
    assert selected is not None and name == "Longbow"
    selected, name = resolver._weapon(sheet, "I attack.")
    assert selected is not None and name == "Longsword"


@pytest.mark.parametrize("item_type", ["focus", "shield", "armor"])
def test_combat_weapon_type_is_authoritative_for_localized_equipment(item_type: str) -> None:
    weapon, name = CombatResolver._weapon(
        {"equipment": [{"name": "法器" if item_type == "focus" else ("盾牌" if item_type == "shield" else "链甲"), "type": item_type}]},
        "普通攻击",
    )
    assert weapon is None
    assert name == "徒手"


def test_dnd_sorcerer_with_only_arcane_focus_attacks_unarmed() -> None:
    rule = _rule("dnd5e.json")
    equipment, _inventory = build_starter_items(rule, "术士")
    weapon, name = CombatResolver._weapon({"equipment": equipment}, "普通攻击")
    assert weapon is None
    assert name == "徒手"


def test_dnd_weapon_attack_gets_proficiency_without_a_skill() -> None:
    dnd = _rule("dnd5e.json")
    instance = GameInstance(game_key=("test", "dnd-proficiency", "bot"), rule_id="dnd5e")
    instance.players["fighter"] = {
        "character_name": "Fighter",
        "character_sheet": {"attributes": {"str": 14}, "skills": [], "level": 1},
    }
    instance.npcs["target"] = {"name": "Target", "hp": 10, "max_hp": 10, "attributes": {"dex": 10}}
    request = {
        "check_id": "attack-proficiency", "actor_uid": "fighter", "kind": "attack",
        "opponent": "npc:target", "dice_system": "d20", "attribute": "str", "target": 10,
    }
    result = resolve_check_request(
        instance,
        {"user_id": "fighter", "text": "I attack Target.", "check_request": request, "dice_value": 10},
        dnd,
    )

    assert result is not None
    assert result["modifier"] == 4  # STR +2 and level-1 proficiency +2
    assert result["attribute_key"] == "str"
