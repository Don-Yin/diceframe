"""Small public routing descriptor; mechanics remain in ProfileService."""

from src.engine.modules import profile_progression, profile_run
from src.game_profiles.registry import resolve


def unconfigured_binding(slot):
    return profile_run.unconfigured(slot)


def routing_descriptor(instance):
    slot = instance.modules.get("profile_run")
    if unconfigured_binding(slot) and profile_progression.accepts_narrative(instance):
        return None
    if (
        isinstance(slot, dict)
        and type(slot.get("schema_version")) is int
        and slot.get("schema_version") == 1
    ):
        try:
            profile = resolve(slot.get("profile_id"), slot.get("profile_version"))
            return {"id": profile.id, "version": profile.version, "mode": profile.mode}
        except ValueError:
            pass
    # An unsupported binding must reach the profile error view, never the
    # legacy narrative composer. Do not expose malformed raw save fields.
    return {"unsupported": True}
