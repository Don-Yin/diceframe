"""Round recovery / judgment bookkeeping helpers for :class:`GameInstance`.

本模块负责：

- 历史回滚 detail（``rollback_last_round_locked``）；
- 判定失败恢复 detail（``abort_round_processing_locked``）；
- 判定日志构造（``finish_judgment_locked``）；
- swipe 记账（``finish_judgment_with_swipe_locked`` / ``switch_swipe``）。

边界：

- 它**不是** Aggregate，也不拥有锁；所有 ``*_locked`` 函数的前置条件是调用方
  已经持有 ``GameInstance`` 的 ``_lock``。锁与 authority 仍由 GameInstance 持有。
- 历史回滚（rollback_last_round）与判定失败 abort（abort_round_processing）是
  **两个不同 contract**：前者撤销一个已提交的历史回合，后者只把当前判定阶段
  退回行动阶段。本模块保持它们分开，不合成"大一统 reset"。
- 不 runtime import ``src.engine.game_instance``（仅 ``TYPE_CHECKING`` 类型引用），
  依赖方向保持 ``game_instance → round_recovery``。
- 与 economy 的复用沿用既有 lazy import 位置，不引入新的 import-time 依赖。
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from src.engine import module_hooks, progression
from src.engine.contracts import RoundLogEntry
from src.engine.game_state import GameState
from src.engine.modules import progression_state, resource_recovery, skill_growth
from src.engine.round_snapshots import restore_players, snapshot_players
from src.engine.world_state import ensure_world_state

if TYPE_CHECKING:
    from src.engine.game_instance import GameInstance

logger = logging.getLogger("trpg")


# ---------- 历史回滚（已提交回合）---------------------------


def rollback_last_round_locked(instance: GameInstance) -> int | None:
    """``rollback_last_round`` 的持锁实现（调用方必须已持有 ``_lock``）。

    迁移自基线 ``main`` 的 ``rollback_last_round`` 函数体；撤销/恢复的执行顺序
    （经济逆结算 → 玩家恢复 → 战斗扩展恢复 → 实体/世界恢复 → 清理回合状态）
    与基线逐句一致，不得调整。
    """
    if not instance.log:
        return None
    from src.engine.modules import adventure_runtime_state, checks, round_safety, session_stats

    session_stats.require_writable(instance)
    checks.require_writable(instance)
    round_safety.require_writable(instance)
    adventure_runtime_state.require_writable(instance)
    last = instance.log[-1]
    target = int(last.get('round', progression_state.round_value(instance)) or progression_state.round_value(instance))
    skill_growth.rewind_preflight(instance, target)
    resource_recovery.rewind_preflight(instance, target)
    instance.log.pop()
    from src.engine.economy import reconcile_rollback_snapshot, reverse_round_economy

    rolled_back_round = int(last.get("round", progression_state.round_value(instance)) or progression_state.round_value(instance))
    module_hooks.run(module_hooks.ROUND_REWIND_BEGIN, instance, rolled_back_round)
    reverse_round_economy(instance, rolled_back_round)
    snapshot = last.get("round_start_snapshot") or last.get("pre_state_snapshot", {})
    if isinstance(snapshot, dict) and snapshot:
        restore_players(instance, reconcile_rollback_snapshot(instance, snapshot, rolled_back_round))
    # Module state the entry carries (e.g. combat-extension source fields) is
    # restored after the players so it is not overwritten by them.
    module_hooks.run(
        module_hooks.ROUND_REWIND_RESTORE, instance, last, rolled_back_round,
        module_hooks.REWIND_SOURCE_ROLLBACK,
    )
    # 世界真相同样是"这一轮结算出来的东西"：回滚到第 N 轮时，第 N 轮及
    # 之后写入的 world ops 必须一起撤销，否则世界会记住一个被丢弃的分支。
    if isinstance(last.get("pre_world_state"), dict) and last["pre_world_state"]:
        instance.world_state = ensure_world_state(last["pre_world_state"])
    # FIX-07 §10 步骤 23：Adventure 进度与世界真相由同一次权威事务写入
    # （FIX-04 §6.7），整轮回滚必须一起撤销，否则会出现"世界退回去了、进度还
    # 留在被丢弃的分支上"的半回滚。
    if isinstance(last.get("pre_adventure_progress"), dict):
        adventure_runtime_state.replace_progress(instance, copy.deepcopy(last["pre_adventure_progress"]))
    progression.rewind_after_rollback(instance, rolled_back_round)
    instance.action_queue.clear()
    instance.pending_actions.clear()
    instance.ready_players.clear()
    # ``reverse_round_economy`` restores still-valid proposals whose
    # settlement happened in the rolled-back round.  Do not clear the
    # compatibility projection after that restoration.
    instance.reset_round_checks()
    # Explicit rollback starts a fresh attempt for that round; do not
    # let a discarded outcome affect the replay or a later round.
    round_safety.discard_round(instance)
    instance.state = GameState.ACTIVE_ACTION
    session_stats.touch(instance)
    return progression_state.round_value(instance)


# ---------- 判定失败恢复（未提交回合）-----------------------


def abort_round_processing_locked(instance: GameInstance) -> bool:
    """``abort_round_processing`` 的持锁实现（调用方必须已持有 ``_lock``）。

    迁移自基线 ``main`` 的 ``abort_round_processing`` 函数体；仅 ``ACTIVE_JUDGMENT``
    可 abort，恢复顺序（玩家 → 战斗扩展 → 旧版实体）与基线逐句一致。
    """
    if instance.state != GameState.ACTIVE_JUDGMENT:
        return False
    from src.engine.modules import (
        adventure_runtime_state, checks, round_safety, ruleset_runtime, session_stats,
    )

    session_stats.require_writable(instance)
    checks.require_writable(instance)
    round_safety.require_writable(instance)
    adventure_runtime_state.require_writable(instance)
    ruleset_runtime.require_writable(instance)
    restored = False
    if round_safety.round_start_snapshot(instance):
        restore_players(instance, round_safety.round_start_snapshot(instance))
        restored = True
    if module_hooks.run_any(module_hooks.ROUND_ABORT, instance):
        restored = True
    # 旧版战斗路径直接改写的实体（npcs/world_state/adventure 进度）。
    entities_restored = instance.restore_round_entity_snapshot()
    restored = restored or entities_restored
    if restored:
        instance._drop_stale_combat_caches(all_targets=entities_restored)
    for check_id in list(instance._luck_timers):
        instance._cancel_luck_timer(check_id)
    instance.reset_round_checks()
    round_safety.discard_round(instance)
    instance.state = GameState.ACTIVE_ACTION
    session_stats.touch(instance)
    return True


# ---------- 判定完成记账 -----------------------------------


def finish_judgment_locked(
    instance: GameInstance,
    gm_response: str,
    pre_state_snapshot: dict | None = None,
    state_changes: list[str] | None = None,
    pre_combat_extension_snapshot: dict[str, Any] | None = None,
    story: dict[str, Any] | None = None,
    adventure_completion_candidate: Any = None,
) -> None:
    """构造并写入本轮判定 log entry（``finish_judgment`` 的持锁部分）。

    GameInstance wrapper 先校验推进与经济模块，再在同一段状态锁内依次
    调用本函数和 ``start_round_locked``，使日志提交与下一轮开启不可交错。
    """
    from src.engine.modules import adventure_runtime_state, checks, round_safety, session_stats

    session_stats.require_writable(instance)
    checks.require_writable(instance)
    round_safety.require_writable(instance)
    adventure_runtime_state.require_writable(instance)
    entry: RoundLogEntry = {
        "round": progression_state.round_value(instance),
        "actions": list(instance.action_queue),
        "gm_response": gm_response,
        "state_changes": list(state_changes or []),
        "check_results": [dict(item) for item in checks.last_checks(instance)],
        "round_start_snapshot": (
            copy.deepcopy(round_safety.round_start_snapshot(instance))
            if round_safety.round_start_snapshot(instance) else snapshot_players(instance)
        ),
        "swipes": [],
        "current_swipe": 0,
        "pre_state_snapshot": pre_state_snapshot if pre_state_snapshot is not None else snapshot_players(instance),
        # 判定入口的世界真相：整轮回滚 / swipe 分支切换时一起撤销本轮
        # 写入的 world ops（与玩家、战斗扩展快照同一语义）。
        "pre_world_state": copy.deepcopy(
            round_safety.round_entity_snapshot(instance).get("world_state", instance.world_state)
        ),
        # FIX-07 §10 步骤 23：Adventure 进度与世界真相同属"本轮结算出来的东西"，
        # 回滚必须一起撤销（否则世界退回去了、进度还留在被丢弃的分支上）。
        "pre_adventure_progress": copy.deepcopy(
            round_safety.round_entity_snapshot(instance).get(
                "adventure_progress", adventure_runtime_state.progress(instance),
            )
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if story is not None:
        entry["story"] = copy.deepcopy(story)
    # Module fields (e.g. combat-extension snapshots, pending combat summaries
    # merged into state_changes) are added before the entry is committed.
    module_hooks.run(module_hooks.ROUND_COMMIT, instance, entry, pre_combat_extension_snapshot)
    instance.log.append(entry)
    adventure_runtime_state.record_completion_suggestion(
        instance, adventure_completion_candidate,
    )
    session_stats.record_llm_usage(instance, 0, calls=1)
    session_stats.touch(instance)


def finish_judgment_with_swipe_locked(
    instance: GameInstance,
    gm_response: str,
    original_round: int,
    state_changes: list[str] | None = None,
    story: dict[str, Any] | None = None,
    adventure_completion_candidate: Any = None,
) -> None:
    """为已有轮次添加 swipe 的持锁 detail（不推进回合）。"""
    from src.engine.modules import adventure_runtime_state, session_stats

    session_stats.require_writable(instance)
    for entry in instance.log:
        if entry.get("round") == original_round:
            swipes = entry.setdefault("swipes", [])
            if not swipes:
                swipes.append(entry.get("gm_response", ""))
            # Keep every story beside the exact text revision it describes.
            if story is not None or "story" in entry or "swipe_stories" in entry:
                stories = entry.setdefault("swipe_stories", [])
                while len(stories) < len(swipes):
                    stories.append(copy.deepcopy(entry.get("story")) if not stories else None)
                stories.append(copy.deepcopy(story))
            swipes.append(gm_response)
            entry["current_swipe"] = len(swipes) - 1
            entry["gm_response"] = gm_response
            if story is None:
                entry.pop("story", None)
            else:
                entry["story"] = copy.deepcopy(story)
            if state_changes is not None:
                entry["state_changes"] = list(state_changes)
            adventure_runtime_state.clear_completion_suggestions_for_round(
                instance, original_round,
            )
            adventure_runtime_state.record_completion_suggestion(
                instance, adventure_completion_candidate,
            )
            break
    session_stats.record_llm_usage(instance, 0, calls=1)
    session_stats.touch(instance)


def switch_swipe(instance: GameInstance, round_num: int, swipe_idx: int) -> bool:
    """切换指定轮次的 swipe 展示。

    与基线一致：该方法当前**不持有** ``_lock``，本函数是纯 detail 迁移，
    不顺手改变它的并发语义。
    """
    from src.engine.modules import adventure_runtime_state

    for entry in instance.log:
        if entry.get("round") == round_num:
            swipes = entry.get("swipes", [])
            if not swipes or swipe_idx >= len(swipes):
                return False
            entry["current_swipe"] = swipe_idx
            entry["gm_response"] = swipes[swipe_idx]
            adventure_runtime_state.clear_completion_suggestions_for_round(
                instance, round_num,
            )
            stories = entry.get("swipe_stories")
            if isinstance(stories, list) and swipe_idx < len(stories) and isinstance(stories[swipe_idx], dict):
                entry["story"] = copy.deepcopy(stories[swipe_idx])
            else:
                entry.pop("story", None)
            panel_history = entry.get("swipe_scene_panels")
            if isinstance(panel_history, list) and swipe_idx < len(panel_history):
                entry["scene_panels"] = copy.deepcopy(panel_history[swipe_idx])
            prompt_history = entry.get("swipe_scene_image_prompts")
            if isinstance(prompt_history, list) and swipe_idx < len(prompt_history):
                entry["scene_image_prompt"] = str(prompt_history[swipe_idx] or "")
            logger.info("Swipe 切换: round=%d → %d/%d", round_num, swipe_idx, len(swipes))
            return True
    return False
