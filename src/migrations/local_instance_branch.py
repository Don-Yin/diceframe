"""Explicit adapter for the pre-integration local v36-v38 save sequence.

Those readers added AI policy and check grants at numbers that main used for
content references and room credentials. Only the known local shape may replay
main's v35-v38 transformations; the additional module slots remain untouched.
"""

from typing import Any


def main_sequence_version(payload: dict[str, Any], version: int) -> int:
    if version not in (36, 37, 38):
        return version
    modules = payload.get("modules")
    if not isinstance(modules, dict):
        return version
    room = modules.get("room_access")
    if not isinstance(room, dict) or room.get("schema_version") != 1:
        return version
    if not any(name in modules for name in ("ai_seats", "check_modes")):
        return version
    required = {
        "ai_seats": {"revision", "defaults_revision", "seat_revisions", "defaults", "seats", "outcomes"},
    }
    if version >= 37 or "check_modes" in modules:
        required["check_modes"] = {"revision", "seats"}
    for name, fields in required.items():
        slot = modules.get(name)
        if not isinstance(slot, dict) or slot.get("schema_version") != 1 or not fields <= slot.keys():
            raise ValueError(f"unsupported local instance schema variant: {name}")
    if "room_password_hash" in room or "seat_credentials" in room:
        raise ValueError("ambiguous local room_access schema variant")
    # Existing slots take precedence in main's additive transformations.
    return 35
