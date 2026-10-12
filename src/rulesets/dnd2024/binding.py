"""Canonical runtime identity shared by new games and derived characters."""

from __future__ import annotations

from typing import Any

from src.rulesets.bundle import LoadedRulesetBundle


def rule_binding(bundle: LoadedRulesetBundle) -> dict[str, Any]:
    return {
        "rule_id": "dnd2024_srd",
        "runtime_id": "core:dnd2024",
        "runtime_version": 1,
        "content_version": bundle.manifest.content_version,
        "state_schema_version": 1,
    }
