import json
from pathlib import Path

from src.compat.aliases import canonical_class_id, canonical_item_id
from src.engine.character_utils import build_starter_items
from src.rules.loader import RuleBundleLoader
from src.rules.rule_system import RuleSystem

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "templates" / "rules"
LEGACY_RULES = ROOT / "tests" / "fixtures" / "legacy_rules"


def test_dnd5e_v2_locale_views_share_exact_mechanics():
    loader = RuleBundleLoader()
    views = [RuleSystem(loader.load_rule(RULES, "dnd5e", locale)) for locale in ("zh-CN", "en", "ja")]
    assert len({view.mechanics_snapshot() for view in views}) == 1
    assert [view.classes[4]["id"] for view in views] == ["fighter"] * 3


def test_dnd5e_v2_localizes_display_but_starter_uses_ids():
    loader = RuleBundleLoader()
    zh = RuleSystem(loader.load_rule(RULES, "dnd5e", "zh-CN"))
    en = RuleSystem(loader.load_rule(RULES, "dnd5e", "en"))
    zh_equipment, _ = build_starter_items(zh, "战士")
    en_equipment, _ = build_starter_items(en, "Fighter")
    assert [item["item_key"] for item in zh_equipment] == ["longsword", "shield", "chain_mail"]
    assert [item["item_key"] for item in en_equipment] == ["longsword", "shield", "chain_mail"]
    assert zh_equipment[0]["name"] == "长剑"
    assert en_equipment[0]["name"] == "Longsword"


def test_dnd5e_v2_aliases_are_compat_boundary_only():
    assert canonical_class_id("战士") == "fighter"
    assert canonical_class_id("ファイター") == "fighter"
    assert canonical_item_id("秘術焦点") == "arcane_focus"
    assert canonical_item_id("Arcane Focus") == "arcane_focus"


def test_legacy_full_localized_copies_remain_loadable():
    for path in (RULES / "dnd5e.json", LEGACY_RULES / "dnd5e_en.json", LEGACY_RULES / "dnd5e_ja.json"):
        rule = RuleSystem.load(path)
        assert rule.rule_id == "dnd5e"


def test_dnd5e_core_has_canonical_mechanics_and_no_locale_overlay_fields():
    core = json.loads((RULES / "dnd5e.json").read_text(encoding="utf-8"))
    assert core["rule_schema_version"] == 2
    assert core["items"]["arcane_focus"] == {"type": "focus"}
    assert core["items"]["chain_mail"]["ac_base"] == 16
    assert all(item.get("id") for item in core["classes"])


def test_dnd5e_v2_starter_items_do_not_depend_on_legacy_damage_tables(monkeypatch):
    from src.engine import constants

    monkeypatch.setattr(constants, "WEAPON_DAMAGE", {})
    monkeypatch.setattr(constants, "WEAPON_DAMAGE_DICE", {})
    rule = RuleSystem(RuleBundleLoader().load_rule(RULES, "dnd5e", "en"))

    equipment, _ = build_starter_items(rule, "Fighter")

    longsword = next(item for item in equipment if item["item_key"] == "longsword")
    assert longsword["type"] == "weapon"
    assert longsword["damage_dice"] == "1d8"
