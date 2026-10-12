"""Adapter exposing legacy rule templates to the canonical loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

def load_v1_template(path: str | Path) -> dict[str, Any]:
    from src.rules.rule_system import _resolve_rule_template

    template = _resolve_rule_template(Path(path))
    if not str(template.get("rule_id") or "").strip():
        raise ValueError("V1 rule template requires rule_id")
    return template
