"""Shared encounter-readiness ownership for the D&D 2024 runtime."""

from __future__ import annotations

from typing import Any


def required_encounter_player_ids(instance: Any) -> list[str]:
    """Return active human party seats that may be asked to ready.

    AI-hosted, unclaimed, away, and deceased seats have no human Ready action
    to perform. The generic engine already owns that live-seat projection via
    ``active_human_players``; the D&D encounter surface reuses it instead of
    maintaining a second roster interpretation.
    """

    gm_uid = str(getattr(instance, "gm_uid", "") or "")
    active_humans = getattr(instance, "active_human_players", set())
    return sorted(
        str(uid) for uid in active_humans
        if str(uid) and str(uid) != gm_uid
    )


__all__ = ["required_encounter_player_ids"]
