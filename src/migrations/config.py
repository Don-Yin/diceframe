"""Configuration migrations kept independent from the web bootstrap."""

from __future__ import annotations

from src.generation_limits import DEFAULT_TEXT_GEN_MAX_TOKENS

DEFAULT_NARRATIVE_MAX_TOKENS = 4096
GENERATION_DEFAULTS_VERSION = 7
TOKEN_FIELD_MIGRATIONS = (
    ("narrative_max_tokens", frozenset({1024, 1536, 2048}), DEFAULT_NARRATIVE_MAX_TOKENS),
    ("character_gen_max_tokens", frozenset({2048}), 4096),
    ("analysis_max_tokens", frozenset({512, 1024}), 4096),
    ("summary_max_tokens", frozenset({400, 1024}), 4096),
    ("brief_max_tokens", frozenset({300, 1024}), 4096),
    ("text_gen_max_tokens", frozenset({400, 1024}), 4096),
)


def _migrate_legacy_generation_defaults(config: dict) -> None:
    """Apply the pre-v6 grouped defaults migration once."""
    for field, old_defaults, new_default in TOKEN_FIELD_MIGRATIONS:
        missing = min(old_defaults)
        try:
            current = int(config.get(field, missing) or missing)
        except (TypeError, ValueError):
            current = missing
        if current in old_defaults:
            config[field] = new_default


def _migrate_text_generation_default(config: dict) -> None:
    """Raise the legacy text-generation floor once, before v7 is recorded."""
    try:
        current = int(config.get("text_gen_max_tokens", 4096) or 4096)
    except (TypeError, ValueError):
        current = 4096
    if current < DEFAULT_TEXT_GEN_MAX_TOKENS:
        config["text_gen_max_tokens"] = DEFAULT_TEXT_GEN_MAX_TOKENS


def migrate_generation_defaults(config: dict) -> bool:
    try:
        version = int(config.get("generation_defaults_version", 0) or 0)
    except (TypeError, ValueError):
        version = 0
    if version >= GENERATION_DEFAULTS_VERSION:
        return False
    if version < 6:
        _migrate_legacy_generation_defaults(config)
    if version < 7:
        _migrate_text_generation_default(config)
    config["generation_defaults_version"] = GENERATION_DEFAULTS_VERSION
    return True
