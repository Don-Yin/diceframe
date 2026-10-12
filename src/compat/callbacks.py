"""Compatibility calls for pre-locale world-loader callbacks."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


def load_world_template(
    callback: Callable[..., dict | None],
    world_id: str,
    language: str,
) -> dict | None:
    """Call the V2 two-argument contract, falling back to the old one-arg form."""
    try:
        inspect.signature(callback).bind(world_id, language)
    except (TypeError, ValueError):
        return callback(world_id)
    return callback(world_id, language)
