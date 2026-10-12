"""Read-only projection for a party's shared rest proposal."""

from __future__ import annotations

from typing import Any

from src.engine.modules import ruleset_runtime


def saved_rest_session(instance: Any) -> dict[str, Any]:
    state = ruleset_runtime.state(instance)
    if not isinstance(state, dict):
        return {}
    session = state.get("rest_session")
    return session if isinstance(session, dict) else {}


def public_rest_session(instance: Any) -> dict[str, Any]:
    """Return the shared rest proposal without exposing sheets or rolls."""
    session = saved_rest_session(instance)
    status = str(session.get("status") or "idle")
    if status == "idle" and not session.get("participants"):
        return {
            "active": False,
            "status": "idle",
            "rest": None,
            "ready_count": 0,
            "active_count": 0,
            "participants": [],
        }
    required = [
        str(uid)
        for uid in session.get("required_uids", [])
        if str(uid) in instance.players
    ]
    submitted = session.get("participants")
    submitted = submitted if isinstance(submitted, dict) else {}
    rows: list[dict[str, Any]] = []
    for uid in required:
        player = instance.players.get(uid) or {}
        entry = submitted.get(uid)
        rows.append(
            {
                "user_id": uid,
                "character_name": str(player.get("character_name") or uid),
                "status": "submitted" if isinstance(entry, dict) else "waiting",
            }
        )
    ready_count = sum(row["status"] == "submitted" for row in rows)
    return {
        "active": status in {"collecting", "resolving"},
        "status": status,
        "rest": session.get("rest"),
        "ready_count": ready_count,
        "active_count": len(rows),
        "participants": rows,
        "resolved_at": session.get("resolved_at"),
        "error": session.get("error", ""),
    }
