"""Facade for the D&D 2024 GM Director proposal pipeline."""

from __future__ import annotations

from typing import Any

from .context import build_director_context
from .contracts import DirectorMode, DirectorProposal
from .decision_resolver import resolve_decision


class Dnd2024Director:
    """Read-only Director used by the D&D runtime composition root."""

    def __init__(self, mode: DirectorMode = "assist") -> None:
        self.mode = mode if mode in {"auto", "assist", "manual"} else "assist"

    def propose(self, instance: Any, campaign: dict[str, Any] | None = None) -> DirectorProposal:
        context = build_director_context(instance, campaign)
        return resolve_decision(context, self.mode)

    def propose_dict(self, instance: Any, campaign: dict[str, Any] | None = None) -> dict[str, Any]:
        context = build_director_context(instance, campaign)
        proposal = resolve_decision(context, self.mode)
        return {"context": context.to_dict(), "proposal": proposal.to_dict()}
