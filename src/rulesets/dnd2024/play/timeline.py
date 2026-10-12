"""D&D-owned projection of authoritative batches into the public story feed."""

from __future__ import annotations

from typing import Any


PUBLIC_STORY_EVENTS = frozenset({
    "dnd2024.tutorial.started",
    "dnd2024.tutorial.choice_applied",
    "dnd2024.tutorial.completed",
    "dnd2024.party_decision.resolved",
    "dnd2024.combat.started",
    "dnd2024.combat.ended",
})


def _event_types(batch: dict[str, Any]) -> set[str]:
    return {
        str(event.get("type") or "")
        for event in batch.get("events", [])
        if isinstance(event, dict)
    }


def is_public_story_milestone(batch: dict[str, Any]) -> bool:
    """Keep turn-by-turn mechanics out of the shared narrative timeline."""

    return bool(_event_types(batch).intersection(PUBLIC_STORY_EVENTS))


def public_timeline_projection(
    batch: dict[str, Any], locale: str,
) -> dict[str, str]:
    """Return localized D&D action and narration labels for one public milestone."""

    intent_type = str(batch.get("intent_type") or "")
    event_types = _event_types(batch)
    chinese = not str(locale or "").lower().startswith("en")
    action_labels = {
        "tutorial.choose": ("推进当前剧情", "Advance the current story"),
        "party_decision.submit": ("提交队伍决策意图", "Submit a party decision intent"),
        "party_decision.resolve": ("结算队伍决定", "Resolve the party decision"),
        "tutorial.start": ("开始教学冒险", "Start the guided adventure"),
        "combat.start": ("进入剧情遭遇战", "Enter the story encounter"),
        "combat.end": ("结束遭遇战", "End the encounter"),
        "attack": ("进行攻击", "Make an attack"),
        "cast_spell": ("施放法术", "Cast a spell"),
        "move": ("移动位置", "Move position"),
        "end_turn": ("结束回合", "End the turn"),
    }
    if "dnd2024.combat.started" in event_types:
        action = ("进入剧情遭遇战", "Enter the story encounter")
        response = (
            "遭遇战开始：当前剧情已进入战斗。",
            "Encounter started: the current story has entered combat.",
        )
    elif "dnd2024.combat.ended" in event_types:
        action = ("结束剧情遭遇战", "Finish the story encounter")
        response = (
            "遭遇战结束：可以回到当前冒险继续剧情。",
            "Encounter ended: return to the current adventure.",
        )
    else:
        action = action_labels.get(
            intent_type, ("推进高级规则剧情", "Advance the rules story"),
        )
        if intent_type == "tutorial.choose":
            response = (
                "剧情选择已记录，当前冒险已推进。",
                "Story choice recorded; the current adventure advanced.",
            )
        elif intent_type == "party_decision.submit":
            response = (
                "已收到队伍成员的行动意图，等待队伍决策。",
                "A party intent was received; waiting for the group decision.",
            )
        elif intent_type == "party_decision.resolve":
            response = (
                "队伍决定已记录，当前冒险已推进。",
                "The party decision was recorded; the current adventure advanced.",
            )
        elif intent_type.startswith("session_zero."):
            response = ("开团约定已更新。", "Session agreement updated.")
        elif intent_type.startswith("campaign."):
            response = ("战役记录状态已更新。", "Campaign record state updated.")
        else:
            response = (
                "规则行动已由服务器结算。",
                "Rules action resolved by the server.",
            )
    index = 0 if chinese else 1
    return {"action_text": action[index], "gm_response": response[index]}
