"""Deterministic first-pass classification for narrative actions."""

from __future__ import annotations

import re

from .contracts import DirectorContext, DirectorMode, DirectorProposal
from .encounter_planner import encounter_preset_for

_COMBAT_ENGAGE_RE = re.compile(
    r"(?:攻击|袭击|开火|开战|迎战|冲锋|冲上去|动手|杀过去|拔刀|施法攻击|"
    r"\b(?:fight|attack|ambush|fire|strike|charge|engage)\b)",
    re.I,
)
_COMBAT_READY_RE = re.compile(
    r"(?:准备(?:好)?战斗|进入战斗|摆好战斗姿态|拿起武器|拔出武器|"
    r"\b(?:prepare|ready)\s+(?:for\s+)?(?:battle|combat)\b)",
    re.I,
)
_CHECK_RE = re.compile(r"(?:调查|检查|观察|搜索|追踪|潜行|说服|询问|\b(?:inspect|investigate|search|track|sneak|persuade)\b)", re.I)


def resolve_decision(context: DirectorContext, mode: DirectorMode = "assist") -> DirectorProposal:
    """Classify the next step; this function has no side effects."""

    mode = mode if mode in {"auto", "assist", "manual"} else "assist"
    if context.combat_status == "active":
        return DirectorProposal("combat", 1.0, "combat is already active", mode=mode)
    if context.party_size > 1 and context.campaign_status == "active" and context.tutorial_choice_count > 1:
        return DirectorProposal(
            "party_decision", 0.98, "the active adventure step has multiple choices for a party",
            mode=mode,
        )
    combat_actions = tuple(
        item["id"] for item in context.actions
        if _COMBAT_ENGAGE_RE.search(item["text"]) or _COMBAT_READY_RE.search(item["text"])
    )
    if combat_actions:
        return DirectorProposal(
            "combat", 0.9, "a player action describes hostile engagement",
            action_ids=combat_actions,
            encounter_preset_id=encounter_preset_for(context),
            requires_gm_confirmation=mode != "auto",
            mode=mode,
        )
    check_actions = tuple(item["id"] for item in context.actions if _CHECK_RE.search(item["text"]))
    if check_actions:
        return DirectorProposal("check", 0.65, "a player action requests an uncertain task", action_ids=check_actions, mode=mode)
    return DirectorProposal("narrative", 0.5, "no structured transition was detected", mode=mode)
