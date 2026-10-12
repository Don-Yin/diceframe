"""Format-neutral Lorebook import contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LoreEntryDraft:
    name: str = ""
    content: str = ""
    keys: list[str] = field(default_factory=list)
    secondary_keys: list[str] = field(default_factory=list)
    enabled: bool = True
    constant: bool = False
    # Legacy DiceFrame primary matching (any/all/not_any/not_all). This is a
    # DIFFERENT concept from the SillyTavern selective secondary logic below and
    # must never be derived from it.
    match_mode: str = "any"
    selective_logic: str = "any"
    # Whether ``secondary_keys`` gates activation at all. CCv3/ST express this as
    # the ``selective`` boolean; ``selective=False`` keeps the keys as data but
    # must not filter, so the flag is canonical rather than source-specific.
    selective: bool = True
    use_regex: bool = False
    # Whether ``keys`` may be executed as a regex at all. Adapters reading
    # JavaScript patterns clear it when a pattern is not safely mappable, so the
    # matcher never runs Python ``re`` with silently different semantics.
    regex_executable: bool = True
    case_sensitive: bool = False
    match_whole_words: bool = False
    scan_depth: int = 0
    priority: int = 0
    insertion_order: int = 100
    probability: int = 100
    groups: list[str] = field(default_factory=list)
    group_weight: int = 1
    recursion_flags: dict[str, bool] = field(default_factory=dict)
    timed: dict[str, int] = field(default_factory=dict)
    prompt_slot: str = ""
    external_id: str = ""
    type: str = "other"
    tier: str = "background"
    unreliable: bool = False
    sync_on_enter: bool = False
    visible_to: list[str] = field(default_factory=list)
    connected_to: list[str] = field(default_factory=list)
    triggers_recursive: list[str] = field(default_factory=list)
    prioritize_inclusion: bool = False
    group_scoring: str = ""
    # Canonical default is hybrid: new canonical / ST / CCv3 entries keep the
    # keyword + semantic enhancement behaviour. Only an external format that
    # explicitly requests off / vector_only may narrow it.
    vector_activation: str = "hybrid"
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass
class LorebookDraft:
    name: str = ""
    description: str = ""
    language: str = "zh-CN"
    settings: dict[str, Any] = field(default_factory=dict)
    entries: list[LoreEntryDraft] = field(default_factory=list)
    source: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    preserved_extensions: dict[str, Any] = field(default_factory=dict)
