from __future__ import annotations

import pytest

from src.rulesets.dnd2024.progression import Dnd2024ProgressionCatalog
from src.rulesets.dnd2024.runtime import Dnd2024Runtime
from src.rulesets.dnd2024.spells import (
    Dnd2024SpellCatalog,
    Dnd2024SpellSelection,
    SpellCatalogError,
)


@pytest.fixture(scope="module")
def runtime() -> Dnd2024Runtime:
    return Dnd2024Runtime()


def test_spell_catalog_matches_srd_inventory_and_mechanics(runtime: Dnd2024Runtime) -> None:
    catalog = Dnd2024SpellCatalog.from_bundle(runtime.load_bundle("en"))

    assert len(catalog.spells) == 339
    assert {
        level: sum(spell["level"] == level for spell in catalog.spells.values())
        for level in range(10)
    } == {0: 27, 1: 57, 2: 57, 3: 42, 4: 34, 5: 38, 6: 31, 7: 20, 8: 17, 9: 16}
    fireball = catalog.get("spell:fireball")
    assert fireball is not None
    assert fireball["level"] == 3
    assert fireball["school"] == "evocation"
    assert fireball["class_refs"] == ["class:sorcerer", "class:wizard"]
    assert fireball["components"] == ["V", "S", "M"]
    assert fireball["concentration"] is False
    assert fireball["source_ref"] == "srd-5.2.1:p131:fireball"


def test_spell_catalog_locale_changes_labels_not_mechanics(runtime: Dnd2024Runtime) -> None:
    english = Dnd2024SpellCatalog.from_bundle(runtime.load_bundle("en"))
    chinese = Dnd2024SpellCatalog.from_bundle(runtime.load_bundle("zh-CN"))

    assert english.spells == chinese.spells
    assert english.get("spell:magic_missile")["name"] == "Magic Missile"
    assert chinese.get("spell:magic_missile")["name"] == "魔法飞弹"
    assert chinese.get("spell:fireball")["name"] == "火球术"
    assert all(
        any(ord(character) > 127 for character in label)
        for label in chinese.labels.values()
    )


def test_initial_wizard_spellbook_and_preparation_are_constrained(runtime: Dnd2024Runtime) -> None:
    bundle = runtime.load_bundle("en")
    selection = Dnd2024SpellSelection(bundle)
    recommended = bundle.get("class", "wizard")["recommended_spell_choices"]
    choices = {
        "cantrip_refs": [f"spell:{item}" for item in recommended["cantrip_ids"]],
        "prepared_spell_refs": [f"spell:{item}" for item in recommended["prepared_spell_ids"]],
        "spellbook_refs": [f"spell:{item}" for item in recommended["spellbook_ids"]],
    }

    parsed, errors = selection.validate("class:wizard", 1, choices)

    assert errors == []
    assert len(parsed["spellbook_refs"]) == 6
    assert set(parsed["prepared_spell_refs"]).issubset(parsed["spellbook_refs"])


def test_spell_selection_rejects_wrong_list_level_duplicates_and_missing_book(
    runtime: Dnd2024Runtime,
) -> None:
    selection = Dnd2024SpellSelection(runtime.load_bundle("en"))
    choices = {
        "cantrip_refs": ["spell:eldritch_blast"] * 3,
        "prepared_spell_refs": ["spell:fireball"] * 4,
        "spellbook_refs": ["spell:detect_magic"] * 6,
    }

    _parsed, errors = selection.validate("class:wizard", 1, choices)

    assert any("duplicate" in error for error in errors)
    assert any("not on the class:wizard" in error for error in errors)
    assert any("not eligible" in error for error in errors)
    assert any("must be in spellbook" in error for error in errors)


def test_non_spellcasting_class_rejects_spell_choices(runtime: Dnd2024Runtime) -> None:
    selection = Dnd2024SpellSelection(runtime.load_bundle("en"))
    _parsed, errors = selection.validate(
        "class:fighter", 1, {"cantrip_refs": ["spell:light"]}
    )
    assert errors == ["this class does not have class spellcasting"]


def test_spell_slot_profiles_align_with_progression(runtime: Dnd2024Runtime) -> None:
    bundle = runtime.load_bundle("en")
    selection = Dnd2024SpellSelection(bundle)
    progression = Dnd2024ProgressionCatalog.from_bundle(bundle)

    assert selection.requirements("class:cleric", 5)["spell_slots"] == progression.snapshot(
        "class:cleric", 5
    )["spell_slots"]
    with pytest.raises(SpellCatalogError):
        selection.configure({}, {})
