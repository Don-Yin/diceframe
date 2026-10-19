"""Capture the game projection needed by an asynchronous storyboard job."""

from src.engine import module_hooks

from copy import deepcopy
from typing import Any




def capture_storyboard_context(instance: Any) -> dict[str, Any]:
    """Copy inputs while the caller owns the run/entry fence.

    The storyboard inference owner applies its public appearance projection
    before making a model request; this snapshot is never a client response.
    """
    return {
        "current_scene": str(module_hooks.narrative_view(instance)["scene"] or ""),
        "players": deepcopy(getattr(instance, "players", {}) or {}),
    }
