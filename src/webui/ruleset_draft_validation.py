"""Shared request-shape limits for professional ruleset operations."""

from __future__ import annotations

import json
from typing import Any


MAX_BUILDER_DRAFT_BYTES = 256 * 1024
MAX_BUILDER_DRAFT_DEPTH = 32
MAX_BUILDER_DRAFT_NODES = 5000


def _measure(value: Any, depth: int = 0) -> tuple[int, int]:
    if depth > MAX_BUILDER_DRAFT_DEPTH:
        raise ValueError("builder draft nesting is too deep")
    nodes = 1
    max_depth = depth
    children = (
        value.values()
        if isinstance(value, dict)
        else value
        if isinstance(value, list)
        else ()
    )
    for child in children:
        child_nodes, child_depth = _measure(child, depth + 1)
        nodes += child_nodes
        max_depth = max(max_depth, child_depth)
        if nodes > MAX_BUILDER_DRAFT_NODES:
            raise ValueError("builder draft contains too many values")
    return nodes, max_depth


def validate_draft_shape(draft: Any) -> dict[str, Any]:
    if not isinstance(draft, dict):
        raise ValueError("builder draft must be a JSON object")
    try:
        encoded = json.dumps(
            draft,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("builder draft must contain JSON-compatible values") from exc
    if len(encoded) > MAX_BUILDER_DRAFT_BYTES:
        raise ValueError("builder draft is too large")
    _measure(draft)
    return draft
