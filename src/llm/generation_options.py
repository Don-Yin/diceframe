"""Validated, optional sampling overrides at the provider request boundary."""
from __future__ import annotations

import math
from typing import Any

GENERATION_OPTION_RANGES = {
    "temperature": (0, 2), "top_p": (0, 1),
    "frequency_penalty": (-2, 2), "presence_penalty": (-2, 2),
}


def validate_generation_options(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise ValueError("llm_generation_options must be an object")
    validated = {}
    for key, value in raw.items():
        if key not in GENERATION_OPTION_RANGES:
            raise ValueError(f"Unsupported generation option: {key}")
        low, high = GENERATION_OPTION_RANGES[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key} must be a finite number between {low} and {high}")
        validated[key] = float(value)
    return validated


def validate_recent_rounds(raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw <= 100:
        raise ValueError("context_recent_rounds must be an integer from 0 to 100")
    return raw


def apply_anthropic_options(body: dict[str, Any], options: dict[str, float]) -> None:
    unsupported = set(options) - {"temperature", "top_p"}
    if unsupported:
        raise ValueError("Anthropic Messages does not support configured options: " + ", ".join(sorted(unsupported)))
    body.update(options)
