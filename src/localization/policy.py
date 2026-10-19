"""Paused community catalogs fall back to English, without rewriting save data."""

from __future__ import annotations

import json
from pathlib import Path

LOCALES: dict[str, dict] = json.loads(
    Path(__file__).with_name("registry.json").read_text(encoding="utf-8"),
)


def display_language(normalized_language: str) -> str:
    entry = LOCALES.get(normalized_language)
    if entry and entry["status"] == "paused":
        return "en"
    return normalized_language
