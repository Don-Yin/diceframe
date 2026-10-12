from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any

@dataclass
class ActivationTrace:
    entry_id: str
    book_id: str = ""
    candidate_sources: list[str] | None = None
    matched_keys: list[str] | None = None
    secondary_matches: list[str] | None = None
    primary_result: bool | None = None
    secondary_result: bool | None = None
    semantic_score: float | None = None
    recursion_parent: str | None = None
    recursion_depth: int = 0
    probability: dict[str, Any] | None = None
    group: str | None = None
    timed: dict[str, Any] | None = None
    visibility: str = "visible"
    budget: str = "included"
    final_state: str = "candidate"
    reason_code: str = ""

    def to_dict(self, *, safe: bool = False) -> dict[str, Any]:
        """Serialize one trace row; ``safe`` is the player-facing projection.

        A hidden entry yields **no row at all** (empty dict) rather than a
        redacted placeholder: emitting one row per hidden entry would leak the
        hidden count and its classification, which the visibility contract
        forbids just as much as leaking ids or names. Callers must drop empty
        results (see ``LoreRetriever._build_trace``).
        """

        if safe and self.visibility != "visible":
            return {}
        return asdict(self)
