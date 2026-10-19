from __future__ import annotations

from pathlib import Path

import pytest

from src.rules.loader import RuleBundleLoader
from src.rules.rule_system import RuleSystem, list_available_rules


@pytest.mark.parametrize("locale", ("zh-CN", "en", "ja"))
def test_gal_narrative_skin_loads_in_all_locales(locale: str) -> None:
    template = RuleBundleLoader().load_rule("templates/rules", "gal_narrative", locale)

    assert template["rule_id"] == "gal_narrative"
    assert template["dice_system"] == "none"
    assert template["mechanics"] == "narrative_only"
    assert template["rule_schema_version"] == 2


def test_gal_narrative_locales_share_mechanics() -> None:
    loader = RuleBundleLoader()
    systems = [
        RuleSystem(loader.load_rule("templates/rules", "gal_narrative", locale))
        for locale in ("zh-CN", "en", "ja")
    ]

    assert len({system.mechanics_snapshot() for system in systems}) == 1


def test_gal_narrative_is_discoverable_as_a_builtin_rule() -> None:
    ids = {str(item.get("rule_id") or "") for item in list_available_rules(Path("templates/rules"))}

    assert "gal_narrative" in ids
