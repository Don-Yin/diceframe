"""Stable data contracts for the D&D GM Director boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

DirectorMode = Literal["auto", "assist", "manual"]
ProposalKind = Literal["narrative", "check", "party_decision", "combat", "adventure_choice"]


@dataclass(frozen=True, slots=True)
class DirectorContext:
    """Read-only facts used to make a proposal for one narrative turn."""

    scene: str = ""
    world_id: str = ""
    actions: tuple[dict[str, str], ...] = ()
    combat_status: str = "none"
    campaign_status: str = ""
    tutorial_step_id: str = ""
    tutorial_choice_count: int = 0
    party_size: int = 0
    encounter_preset_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DirectorProposal:
    """A suggestion for the host loop; never an authoritative state change."""

    kind: ProposalKind
    confidence: float
    rationale: str
    action_ids: tuple[str, ...] = ()
    encounter_preset_id: str = ""
    requires_gm_confirmation: bool = True
    mode: DirectorMode = "assist"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
