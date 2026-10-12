"""世界模板 recommended_rules：可选字段透传、清洗与兼容。"""

from __future__ import annotations

from src.webui.services.worlds import _world_template_summary
from src.content.worlds import load_world_template


def test_recommended_rules_passthrough_and_sanitization() -> None:
    summary = _world_template_summary(
        {"world_id": "w", "recommended_rules": ["freeform_fantasy", "", "dnd5e", "freeform_fantasy", 3]},
        "w",
    )
    assert summary["recommended_rules"] == ["freeform_fantasy", "dnd5e"]


def test_recommended_rules_missing_is_empty_list() -> None:
    summary = _world_template_summary({"world_id": "w"}, "w")
    assert summary["recommended_rules"] == []
    assert summary["default_rule"] == "freeform_fantasy"


def test_world_v2_locale_changes_display_but_keeps_identity_and_rules() -> None:
    zh = load_world_template("templates/worlds", "default_fantasy", "zh-CN")
    en = load_world_template("templates/worlds", "default_fantasy", "en-US")

    assert zh and en
    assert zh["world_id"] == en["world_id"] == "default_fantasy"
    assert en["active_locale"] == "en"
    assert en["default_rule"] == zh["default_rule"]
    assert en["recommended_rules"] == zh["recommended_rules"]
    assert en["world_name"] == "Classic Fantasy Adventure"
