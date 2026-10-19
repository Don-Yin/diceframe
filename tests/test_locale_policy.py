from src.engine.language import (
    content_locale_candidates, gm_language_instruction, localized_field,
    localized_text, normalize_language,
)
from src.localization import policy


def test_paused_community_text_uses_english_without_changing_game_identity(monkeypatch):
    from src.content.locale import resolve_locale

    monkeypatch.setitem(policy.LOCALES, "de", {"tier": "community", "status": "paused"})
    assert normalize_language("de-DE") == "de"
    assert localized_text("de", {"de": "Alt", "en": "Current"}) == "Current"
    assert localized_field({"name": "中文", "name_de": "Alt", "name_en": "Current"}, "name", "de") == "Current"
    assert content_locale_candidates("de-DE") == ["en"]
    assert resolve_locale({"de": {"name": "Alt"}, "en": {"name": "Current"}}, "de-DE") == {"name": "Current"}
    # The narration request is user data, not a maintained translation catalog.
    assert "Deutsch" in gm_language_instruction("de")


def test_active_regional_overlay_keeps_exact_locale_priority():
    from src.content.locale import resolve_locale

    assert resolve_locale({"en-US": {"name": "Color"}, "en": {"name": "Colour"}}, "en-US") == {"name": "Color"}


def test_official_and_existing_community_languages_remain_known():
    assert set(policy.LOCALES) == {"en", "zh-CN", "de", "ja", "ru"}
    assert {key for key, value in policy.LOCALES.items() if value["tier"] == "core"} == {"en", "zh-CN"}
