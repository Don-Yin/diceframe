"""Live-game advancement policy and one-shot level entitlements for D&D 2024."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from src.engine import progression


XP_THRESHOLDS = (
    0, 300, 900, 2_700, 6_500, 14_000, 23_000, 34_000, 48_000, 64_000,
    85_000, 100_000, 120_000, 140_000, 165_000, 195_000, 225_000, 265_000,
    305_000, 355_000,
)
VALID_MODES = frozenset({"milestone", "xp"})
VALID_AUTHORITIES = frozenset({"ai_gm", "gm"})


def _level(character: dict[str, Any]) -> int:
    canonical = character.get("ruleset_character")
    if not isinstance(canonical, dict):
        canonical = character
    build = canonical.get("build") if isinstance(canonical.get("build"), dict) else {}
    levels = build.get("class_levels") if isinstance(build.get("class_levels"), list) else []
    first = levels[0] if levels and isinstance(levels[0], dict) else {}
    try:
        return max(1, min(20, int(first.get("level") or build.get("level") or character.get("level") or 1)))
    except (TypeError, ValueError):
        return 1


def _state(instance: Any, *, for_write: bool = False) -> dict[str, Any]:
    from src.engine.modules import ruleset_runtime

    ruleset_runtime.require_writable(instance)
    if for_write:
        ruleset_runtime.require_binding(instance, "core:dnd2024")
    ruleset_state = ruleset_runtime.state(instance)
    if not isinstance(ruleset_state, dict):
        ruleset_state = {}
        ruleset_runtime.replace_state(instance, ruleset_state)
    raw = ruleset_state.get("advancement")
    state = raw if isinstance(raw, dict) else {}
    mode = str(state.get("mode") or "milestone")
    authority = str(state.get("authority") or "ai_gm")
    state.update({
        "schema_version": 1,
        "mode": mode if mode in VALID_MODES else "milestone",
        "authority": authority if authority in VALID_AUTHORITIES else "ai_gm",
    })
    if not isinstance(state.get("xp"), dict):
        state["xp"] = {}
    if not isinstance(state.get("entitlements"), dict):
        state["entitlements"] = {}
    if not isinstance(state.get("history"), list):
        state["history"] = []
    ruleset_state["advancement"] = state
    return state


def configure(instance: Any, mode: str, authority: str) -> dict[str, Any]:
    normalized_mode = str(mode or "milestone").strip().casefold()
    normalized_authority = str(authority or "ai_gm").strip().casefold()
    if normalized_mode not in VALID_MODES:
        raise ValueError("升级方式必须是 milestone 或 xp")
    if normalized_authority not in VALID_AUTHORITIES:
        raise ValueError("升级发放方必须是 ai_gm 或 gm")
    state = _state(instance, for_write=True)
    state["mode"] = normalized_mode
    state["authority"] = normalized_authority
    return view(instance)


def _history(state: dict[str, Any], event: dict[str, Any]) -> None:
    state["history"] = [*(state.get("history") or []), event][-64:]


def grant(instance: Any, user_id: str, *, source: str) -> bool:
    if user_id not in instance.players:
        raise ValueError("角色不存在")
    character = instance.get_character_sheet(user_id)
    level = _level(character)
    if level >= 20:
        raise ValueError("20 级角色不能继续升级")
    state = _state(instance, for_write=True)
    entitlements = state["entitlements"]
    current = entitlements.get(user_id)
    if isinstance(current, dict) and int(current.get("target_level", 0) or 0) == level + 1:
        return False
    entitlements[user_id] = {
        "target_level": level + 1,
        "source": str(source or "gm"),
        "granted_round": progression.current_round(instance),
    }
    _history(state, {
        "type": "granted", "user_id": user_id, "target_level": level + 1,
        "source": str(source or "gm"), "round": progression.current_round(instance),
    })
    return True


def award_xp(instance: Any, user_id: str, amount: int, *, source: str) -> dict[str, Any]:
    if user_id not in instance.players:
        raise ValueError("角色不存在")
    if isinstance(amount, bool) or not 1 <= int(amount) <= 1_000_000:
        raise ValueError("XP 奖励必须是 1 到 1000000 的整数")
    state = _state(instance, for_write=True)
    xp = state["xp"]
    xp[user_id] = max(0, int(xp.get(user_id, 0) or 0)) + int(amount)
    level = _level(instance.get_character_sheet(user_id))
    granted = False
    if level < 20 and xp[user_id] >= XP_THRESHOLDS[level]:
        granted = grant(instance, user_id, source=source)
    _history(state, {
        "type": "xp_awarded", "user_id": user_id, "amount": int(amount),
        "total": xp[user_id], "source": str(source or "gm"),
        "round": progression.current_round(instance),
    })
    return {"total": xp[user_id], "granted": granted}


def require_entitlement(instance: Any, user_id: str, target_level: int) -> dict[str, Any]:
    entitlement = _state(instance)["entitlements"].get(user_id)
    if not isinstance(entitlement, dict) or int(entitlement.get("target_level", 0) or 0) != int(target_level):
        raise ValueError("本局尚未向该角色发放本级升级资格")
    return entitlement


def consume(instance: Any, user_id: str, target_level: int) -> None:
    state = _state(instance, for_write=True)
    entitlement = require_entitlement(instance, user_id, target_level)
    del state["entitlements"][user_id]
    _history(state, {
        "type": "consumed", "user_id": user_id, "target_level": int(target_level),
        "source": str(entitlement.get("source") or ""),
        "round": progression.current_round(instance),
    })


def reconcile_after_level_up(instance: Any, user_id: str) -> bool:
    """Issue the next XP entitlement when stored XP already crossed it."""

    state = _state(instance, for_write=True)
    if state["mode"] != "xp" or user_id not in instance.players:
        return False
    if user_id in state["entitlements"]:
        return False
    level = _level(instance.get_character_sheet(user_id))
    if level >= 20:
        return False
    current_xp = max(0, int(state["xp"].get(user_id, 0) or 0))
    if current_xp < XP_THRESHOLDS[level]:
        return False
    return grant(instance, user_id, source="xp")


def view(instance: Any) -> dict[str, Any]:
    state = _state(instance)
    return _project(instance, state)


def project(instance: Any) -> dict[str, Any]:
    """Return the public advancement view without normalizing stored state in place."""

    from src.engine.modules import ruleset_runtime

    ruleset_state = ruleset_runtime.state(instance)
    raw = ruleset_state.get("advancement") if isinstance(ruleset_state, dict) else None
    saved = raw if isinstance(raw, dict) else {}
    mode = str(saved.get("mode") or "milestone")
    authority = str(saved.get("authority") or "ai_gm")
    state = {
        "mode": mode if mode in VALID_MODES else "milestone",
        "authority": authority if authority in VALID_AUTHORITIES else "ai_gm",
        "xp": saved.get("xp") if isinstance(saved.get("xp"), dict) else {},
        "entitlements": (
            saved.get("entitlements")
            if isinstance(saved.get("entitlements"), dict)
            else {}
        ),
    }
    return _project(instance, state)


def _project(instance: Any, state: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for user_id, player in instance.players.items():
        character = player.get("character_sheet") if isinstance(player, dict) else {}
        character = character if isinstance(character, dict) else {}
        level = _level(character)
        entitlement = state["entitlements"].get(user_id)
        current_xp = max(0, int(state["xp"].get(user_id, 0) or 0))
        next_xp = XP_THRESHOLDS[level] if level < 20 else XP_THRESHOLDS[-1]
        rows.append({
            "user_id": user_id,
            "character_name": str(player.get("character_name") or user_id),
            "level": level,
            "xp": current_xp,
            "next_level_xp": next_xp,
            "entitled": isinstance(entitlement, dict),
            "target_level": int(entitlement.get("target_level", 0) or 0) if isinstance(entitlement, dict) else 0,
            "source": str(entitlement.get("source") or "") if isinstance(entitlement, dict) else "",
        })
    return {
        "mode": state["mode"],
        "authority": state["authority"],
        "players": rows,
    }


def apply_ai_rewards(instance: Any, data: dict[str, Any]) -> list[str]:
    state = _state(instance, for_write=True)
    if state["authority"] != "ai_gm":
        return []
    messages: list[str] = []
    if state["mode"] == "milestone":
        requested = data.get("milestone_grants")
        targets = requested if isinstance(requested, list) else []
        if "all" in targets:
            targets = list(instance.alive_players)
        for user_id in dict.fromkeys(str(item) for item in targets):
            if user_id not in instance.players:
                continue
            if grant(instance, user_id, source="ai_gm"):
                name = instance.players[user_id].get("character_name", user_id)
                messages.append(f"{name}获得了升级资格。")
    elif state["mode"] == "xp":
        rewards = data.get("xp_rewards")
        for user_id, raw_amount in (rewards.items() if isinstance(rewards, dict) else []):
            try:
                result = award_xp(instance, str(user_id), int(raw_amount), source="ai_gm")
            except (TypeError, ValueError):
                continue
            name = instance.players[str(user_id)].get("character_name", user_id)
            messages.append(f"{name}获得 {int(raw_amount)} XP（累计 {result['total']}）。")
            if result["granted"]:
                messages.append(f"{name}已达到下一级门槛，获得升级资格。")
    return messages


def prompt_instruction(instance: Any, language: str) -> str:
    state = _state(instance)
    english = str(language or "").strip().casefold().startswith("en")
    if state["authority"] != "ai_gm":
        return (
            "A human GM grants advancement in this game. Do not emit XP or MILESTONE tags."
            if english
            else "本局升级资格由真人 GM 发放；不要输出 XP 或 MILESTONE 标签。"
        )
    if state["mode"] == "xp":
        if english:
            return (
                "This game uses XP advancement. Only after a concrete objective, quest, or encounter is completed, "
                "emit XP: <uid>: <positive integer> in the state tag section. Never award fixed XP per round or "
                "for ordinary conversation. The server grants one advancement entitlement at the threshold."
            )
        return (
            "本局使用 XP 升级。只有在完成明确目标、任务或遭遇后，才在状态标签区按角色输出 "
            "XP: <uid>: <正整数>；不要按普通对话或每回合固定发 XP，服务器会在达到门槛时发放一次升级资格。"
        )
    if english:
        return (
            "This game uses milestone advancement. Only after the party completes a major chapter, primary objective, "
            "or equivalent milestone, emit MILESTONE: all or MILESTONE: <uid> in the state tag section. "
            "Never grant it repeatedly for ordinary scene progress."
        )
    return (
        "本局使用里程碑升级。只有当队伍完成重要章节、主目标或足以升级的剧情里程碑时，才在状态标签区输出 "
        "MILESTONE: all（全队）或 MILESTONE: <uid>（单个角色）；不要为普通场景推进重复发放。"
    )


def snapshot(instance: Any) -> dict[str, Any]:
    """Copy the private state for transactional rollback."""

    return deepcopy(_state(instance))


def restore(instance: Any, saved: Any) -> None:
    """Restore a transaction snapshot without retaining mutable aliases."""
    from src.engine.modules import ruleset_runtime

    ruleset_runtime.require_writable(instance)
    ruleset_runtime.require_binding(instance, "core:dnd2024")
    ruleset_state = ruleset_runtime.state(instance)
    if not isinstance(ruleset_state, dict):
        ruleset_state = {}
        ruleset_runtime.replace_state(instance, ruleset_state)
    ruleset_state["advancement"] = deepcopy(saved) if isinstance(saved, dict) else {}


def control(instance: Any, command: dict[str, Any]) -> dict[str, Any]:
    """Apply one GM advancement command and return a transport-neutral result."""
    from src.engine.modules import ruleset_runtime

    ruleset_runtime.require_writable(instance)
    ruleset_runtime.require_binding(instance, "core:dnd2024")
    action = str(command.get("action") or "").strip().casefold()
    try:
        if action == "configure":
            configure(
                instance,
                str(command.get("mode") or ""),
                str(command.get("authority") or ""),
            )
        elif action == "grant":
            user_id = str(command.get("user_id") or "").strip()
            targets = list(instance.alive_players) if user_id == "all" else [user_id]
            if not targets:
                return {
                    "ok": False,
                    "code": "CHARACTER_NOT_FOUND",
                    "error": "没有可发放升级资格的角色",
                }
            for target in targets:
                grant(instance, target, source="gm")
        elif action == "award_xp":
            if view(instance)["mode"] != "xp":
                return {
                    "ok": False,
                    "code": "INVALID_ADVANCEMENT_MODE",
                    "error": "当前不是 XP 升级模式",
                }
            user_id = str(command.get("user_id") or "").strip()
            targets = list(instance.alive_players) if user_id == "all" else [user_id]
            try:
                amount = int(command.get("amount"))
            except (TypeError, ValueError):
                return {
                    "ok": False,
                    "code": "INVALID_XP_REWARD",
                    "error": "请填写有效的 XP 奖励",
                }
            for target in targets:
                award_xp(instance, target, amount, source="gm")
        else:
            return {
                "ok": False,
                "code": "INVALID_ADVANCEMENT_ACTION",
                "error": "未知升级控制操作",
            }
    except ValueError as exc:
        return {
            "ok": False,
            "code": "INVALID_ADVANCEMENT_ACTION",
            "error": str(exc),
        }
    return {"ok": True, "advancement": view(instance)}
