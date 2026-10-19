"""Parser for optional, non-authoritative Adventure suggestions."""

from __future__ import annotations

import json
from typing import Any


def parse_adventure_tag(tag: str, value: str, result: dict[str, Any]) -> None:
    if tag != "ADVENTURE_COMPLETE" or len(value) > 2000:
        return
    try:
        candidate = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return
    if isinstance(candidate, dict):
        result["plot_update"]["adventure_completion"] = candidate
