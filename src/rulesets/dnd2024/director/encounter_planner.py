"""Plan a legal encounter reference without inventing enemy mechanics."""

from __future__ import annotations

from .contracts import DirectorContext


def encounter_preset_for(context: DirectorContext) -> str:
    """Story steps own their preset; free play returns an empty sandbox reference."""

    return context.encounter_preset_id if context.campaign_status == "active" else ""
