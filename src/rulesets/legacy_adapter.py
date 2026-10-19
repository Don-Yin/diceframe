"""Adapter that preserves the pre-runtime DiceFrame rule pipeline."""

from __future__ import annotations
from src.engine.modules import progression_state

from copy import deepcopy
from typing import Any

from src.engine.legacy_game_projection import project_legacy_game_context
from src.rulesets.contracts import RulesetCapabilities
from src.adventures.graph_v2 import ADVENTURE_GRAPH_FORMAT_V2


class LegacyRulesetAdapter:
    """Expose existing RuleSystem behavior through the runtime contract.

    Structured intents are deliberately unsupported here. Existing rules keep
    using RoundProcessor, CombatResolver and ProgressionResolver exactly as
    before; callers must check the advertised capability before invoking the
    professional intent path.
    """

    runtime_id = "core:legacy"
    runtime_version = 1
    capabilities = RulesetCapabilities(adventure_formats=(ADVENTURE_GRAPH_FORMAT_V2,))

    def check_mode_policy(self, instance: Any, rule: Any, uid: str) -> dict[str, Any]:
        del uid
        kind = str(rule.advantage_mechanic.get("type") or "")
        supported = kind in {"coc_bonus_penalty", "d20_keep_high_low"}
        return {"kind": kind if supported else "", "context_id": f"round:{progression_state.round_value(instance)}",
                "scope": "narrative_round", "blocked_reason": "" if supported else "unsupported", "previews": []}

    def describe_experience(self, rule: Any, locale: str) -> dict[str, Any]:
        del locale
        return {
            "profile": "generic",
            "rule_id": str(getattr(rule, "rule_id", "") or ""),
            "builder_mode": "legacy",
        }

    def builder_choices(self, rule: Any, draft: dict[str, Any]) -> dict[str, Any]:
        del rule, draft
        raise NotImplementedError("legacy rules use the existing character schema endpoint")

    def validate_character(self, rule: Any, draft: dict[str, Any]) -> list[str]:
        return list(rule.validate_character(draft))

    def derive_character(self, rule: Any, draft: dict[str, Any]) -> dict[str, Any]:
        del rule
        return deepcopy(draft)

    def finalize_character(self, rule: Any, draft: dict[str, Any]) -> dict[str, Any]:
        errors = self.validate_character(rule, draft)
        if errors:
            raise ValueError("; ".join(errors))
        return self.derive_character(rule, draft)

    def normalize_character_submission(
        self, rule: Any, character: dict[str, Any], locale: str = "",
    ) -> dict[str, Any]:
        del rule, locale
        return deepcopy(character)

    def available_intents(self, instance: Any, actor_id: str) -> list[dict[str, Any]]:
        del instance, actor_id
        return []

    def validate_intent(self, instance: Any, intent: dict[str, Any]) -> dict[str, Any]:
        del instance, intent
        return {
            "ok": False,
            "code": "LEGACY_PIPELINE_REQUIRED",
            "error": "This rule uses the legacy free-form round pipeline.",
        }

    def resolve_intent(self, instance: Any, intent: dict[str, Any], rng: Any) -> dict[str, Any]:
        del instance, intent, rng
        raise NotImplementedError("legacy rules do not support authoritative structured intents")

    def apply_event_batch(self, instance: Any, batch: dict[str, Any]) -> dict[str, Any]:
        del instance, batch
        raise NotImplementedError("legacy rules do not support authoritative event batches")

    def gameplay_view(
        self, instance: Any, viewer_id: str = "", viewer_is_gm: bool = False,
    ) -> dict[str, Any]:
        del instance, viewer_id, viewer_is_gm
        return {}

    def build_llm_view(self, instance: Any) -> dict[str, Any]:
        return project_legacy_game_context(instance)

    def project_legacy_character(self, character: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(character)

    def migrate_state(self, payload: dict[str, Any], from_version: int) -> dict[str, Any]:
        del from_version
        return deepcopy(payload)
