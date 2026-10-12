from __future__ import annotations
import random
import re
from collections.abc import Mapping
from typing import Any, Callable

# SillyTavern ``world_info_logic`` (public/scripts/world-info.js):
#   AND_ANY: 0, NOT_ALL: 1, NOT_ANY: 2, AND_ALL: 3
ST_SELECTIVE_LOGIC: dict[str, str] = {
    "0": "and_any",
    "1": "not_all",
    "2": "not_any",
    "3": "and_all",
}

# Legacy DiceFrame / free-form aliases that historically landed in the same
# column. ``and`` was the canonical column default and behaved as AND_ANY.
SELECTIVE_LOGIC_ALIASES: dict[str, str] = {
    "": "and_any",
    "0": "and_any", "1": "not_all", "2": "not_any", "3": "and_all",
    "and": "and_any", "and_any": "and_any", "any": "and_any", "or": "and_any",
    "and_all": "and_all", "all": "and_all",
    "not_any": "not_any",
    "not_all": "not_all",
}

# Legacy DiceFrame primary ``match_mode`` vocabulary (kept separate from the
# SillyTavern selective secondary logic above).
PRIMARY_MATCH_MODES: frozenset[str] = frozenset({"any", "all", "not_any", "not_all"})

# Canonical entry-level vector activation modes. ``hybrid`` is the default so
# migrated primary world lore keeps the pre-v2 keyword + semantic behaviour
# instead of silently losing semantic retrieval after the book_id migration.
CANONICAL_VECTOR_ACTIVATION: frozenset[str] = frozenset({"off", "hybrid", "vector_only"})
DEFAULT_VECTOR_ACTIVATION = "hybrid"


def normalize_selective_logic(value: Any) -> str:
    """Normalize a SillyTavern secondary-key logic to its canonical name.

    Unknown values fall back to ``and_any`` (the SillyTavern default) instead of
    inventing a new mode: the primary key must still gate activation.
    """

    raw = str(value if value is not None else "").strip().lower()
    return SELECTIVE_LOGIC_ALIASES.get(raw, "and_any")


def normalize_primary_match_mode(value: Any) -> str:
    """Normalize the legacy DiceFrame primary ``match_mode``."""

    mode = str(value if value is not None else "").strip().lower()
    return mode if mode in PRIMARY_MATCH_MODES else "any"


# JS ``\d`` / ``\w`` / ``\s`` / ``\b`` are ASCII-only; Python's ``re`` is
# Unicode-aware by default, so a pattern that compiles can still match
# differently. This is advisory: the pattern is preserved, never rewritten.
_JS_ASCII_CLASS = re.compile(r"\\[dwsbDWSB]")


def python_regex_incompatibility(pattern: Any) -> str:
    """Report why a SillyTavern (JavaScript) regex cannot run as Python ``re``.

    SillyTavern regexes are JavaScript; DiceFrame executes Python ``re``. Only
    the safely-mappable subset may run. This never rewrites or evaluates the
    pattern — it returns a preview warning so the raw source can be preserved
    verbatim and left unexecuted.

    Returns ``""`` when the pattern is compatible.
    """

    text = str(pattern if pattern is not None else "")
    if not text:
        return ""
    try:
        re.compile(text)
    except re.error as exc:
        return (
            f"unsupported regex: JavaScript pattern is not valid in Python "
            f"({exc.msg}); preserved but not executed"
        )
    if _JS_ASCII_CLASS.search(text):
        return (
            "regex mismatch: JavaScript \\d/\\w/\\s/\\b are ASCII-only while "
            "Python's are Unicode-aware; pattern preserved and may match differently"
        )
    return ""

def evaluate_probability(entry: dict[str, Any], *, rng: Callable[[], float] = random.random) -> tuple[bool, dict[str, Any]]:
    configured = max(0, min(100, int(entry.get("probability", 100) or 0)))
    if configured >= 100:
        return True, {"configured": configured, "roll": 0, "accepted": True}
    roll = int(rng() * 100) + 1
    return roll <= configured, {"configured": configured, "roll": roll, "accepted": roll <= configured}

def matched_key_score(entry: dict[str, Any], *, primary_hits: list[bool], secondary_hits: list[bool] | None = None) -> int:
    """SillyTavern-compatible group score for one entry (world-info ``getScore``).

    Every matched primary key counts; secondary keys only contribute for the
    positive logics, and never for NOT_ANY / NOT_ALL.
    """

    if not primary_hits:
        return 0
    score = sum(1 for hit in primary_hits if hit)
    secondary_hits = secondary_hits or []
    if secondary_hits:
        logic = normalize_selective_logic(entry.get("selective_logic"))
        if logic == "and_any":
            score += sum(1 for hit in secondary_hits if hit)
        elif logic == "and_all" and all(secondary_hits):
            score += sum(1 for hit in secondary_hits if hit)
    return score

def eligible_for_recursion(entry: dict[str, Any], depth: int, *, recursive_pass: bool) -> bool:
    if not bool(entry.get("enabled", True)) or (bool(entry.get("delay_until_recursion", False)) and not recursive_pass):
        return False
    level = int(entry.get("recursion_level", 0) or 0)
    return level <= 0 or depth >= level

def next_recursion_buffer(entry: dict[str, Any]) -> str:
    if bool(entry.get("prevent_further_recursion", False)) or bool(entry.get("non_recursable", False)):
        return ""
    return str(entry.get("content", "") or "")

TIMED_COUNTER_KEYS: tuple[str, ...] = (
    "sticky_remaining", "cooldown_remaining", "delay_remaining", "pending_cooldown",
)


def migrate_timed_state(state: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    """Convert legacy timers to the persisted independent-counter shape.

    The operation is idempotent so the codec can normalize both old saves and
    already-migrated saves at every load/save boundary.

    It also repairs the pre-fix shape where a single activation armed
    ``sticky_remaining`` and ``cooldown_remaining`` at the same time: the
    cooldown is moved back to ``pending_cooldown`` so the sticky window is not
    blocked by the entry's own cooldown. Without this, saves written by the
    buggy runtime would keep their inverted lifecycle forever.
    """
    result: dict[str, dict[str, int]] = {}
    for entry_id, raw in (state or {}).items():
        if not isinstance(raw, Mapping):
            continue
        if any(key in raw for key in TIMED_COUNTER_KEYS):
            sticky = max(0, int(raw.get("sticky_remaining", 0) or 0))
            cooldown = max(0, int(raw.get("cooldown_remaining", 0) or 0))
            pending = max(0, int(raw.get("pending_cooldown", 0) or 0))
            if sticky > 0 and cooldown > 0:
                pending, cooldown = max(pending, cooldown), 0
            result[str(entry_id)] = {
                "sticky_remaining": sticky,
                "cooldown_remaining": cooldown,
                "delay_remaining": max(0, int(raw.get("delay_remaining", 0) or 0)),
                "pending_cooldown": pending,
                "activated_tick": int(raw.get("activated_tick", 0) or 0),
            }
            continue
        remaining = max(0, int(raw.get("remaining", 0) or 0))
        status = str(raw.get("status", ""))
        if status in ("delayed", "delay"):
            # 施工包 C7：旧 delayed 记的是「还剩几轮」，新语义是「第 N 回合之前不
            # 激活」，两者无法精确等价。安全迁成「无 active state」——条目之后由
            # 自己的 ``delay`` 字段配合 authoritative tick 重新判定，而不是继续
            # 倒计时一个语义已经变了的计数器。
            continue
        result[str(entry_id)] = {
            "sticky_remaining": remaining if status == "active" else 0,
            "cooldown_remaining": remaining if status == "cooldown" else 0,
            "delay_remaining": 0,
            "pending_cooldown": 0,
            "activated_tick": int(raw.get("activated_tick", 0) or 0),
        }
    return result


def arm_timed_activation(
    state: dict[str, Any], *, sticky: int, cooldown: int, activated_tick: int = 0,
) -> None:
    """Record one activation's timers on ``state``.

    Lifecycle (SillyTavern-compatible)::

        inactive → activated → sticky_active → cooldown → inactive

    ``cooldown`` is therefore only *armed* while the entry is sticky-active; it
    starts counting down once the sticky window closes (see
    :func:`advance_timed_state`). Re-triggering an entry whose sticky or
    cooldown window is still running does **not** refresh either timer.
    """

    sticky = max(0, int(sticky or 0))
    cooldown = max(0, int(cooldown or 0))
    if sticky <= 0 and cooldown <= 0:
        return
    if max(0, int(state.get("sticky_remaining", 0) or 0)) > 0:
        return
    if max(0, int(state.get("cooldown_remaining", 0) or 0)) > 0:
        return
    if sticky > 0:
        state["sticky_remaining"] = sticky
        state["pending_cooldown"] = cooldown
    else:
        state["cooldown_remaining"] = cooldown
        state["pending_cooldown"] = 0
    state["activated_tick"] = int(activated_tick or 0)


def advance_timed_state(state: dict[str, Any]) -> bool:
    """Advance one authoritative turn tick for one entry; True when expired.

    Sticky runs to zero first and only then is the pending cooldown armed, so an
    entry can never be blocked by its own cooldown during its sticky window.
    ``delay_remaining`` is drained for legacy saves only — canonical runtime
    treats ``delay`` as a pre-activation gate against the turn tick and never
    writes this counter (see :func:`delay_gate_blocked`).
    """

    sticky = max(0, int(state.get("sticky_remaining", 0) or 0))
    cooldown = max(0, int(state.get("cooldown_remaining", 0) or 0))
    delay = max(0, int(state.get("delay_remaining", 0) or 0))
    pending = max(0, int(state.get("pending_cooldown", 0) or 0))

    if sticky > 0:
        sticky -= 1
        if sticky == 0 and pending > 0:
            cooldown, pending = pending, 0
    elif cooldown > 0:
        cooldown -= 1
    if delay > 0:
        delay -= 1

    state["sticky_remaining"] = sticky
    state["cooldown_remaining"] = cooldown
    state["delay_remaining"] = delay
    state["pending_cooldown"] = pending
    return sticky <= 0 and cooldown <= 0 and delay <= 0 and pending <= 0


def sticky_active(state: dict[str, Any] | None) -> bool:
    """True while the entry is inside its sticky window."""

    if not isinstance(state, dict):
        return False
    if str(state.get("status", "")) == "active" and int(state.get("remaining", 0) or 0) > 0:
        return True
    return max(0, int(state.get("sticky_remaining", 0) or 0)) > 0


def timed_gate_blocked(state: dict[str, Any] | None) -> bool:
    """The single cooldown / legacy-delay gate for one entry.

    Shared by every candidate channel (keyword, fuzzy, semantic, recursion) so
    the gate cannot be applied to initial seeds only. A sticky-active entry is
    never blocked: its cooldown has not started yet.
    """

    if not isinstance(state, dict):
        return False
    if sticky_active(state):
        return False
    if str(state.get("status", "")) in ("cooldown", "delayed", "delay"):
        if int(state.get("remaining", 0) or 0) > 0:
            return True
    return (
        max(0, int(state.get("cooldown_remaining", 0) or 0)) > 0
        or max(0, int(state.get("delay_remaining", 0) or 0)) > 0
    )


def delay_gate_blocked(entry: dict[str, Any], *, current_tick: int | None) -> bool:
    """SillyTavern ``delay``: stay inert until the turn counter reaches it.

    ``delay`` is a *pre-activation* gate on the authoritative turn tick, not a
    post-activation countdown — an entry with ``delay=5`` must not fire before
    turn 5, rather than firing immediately and then blocking itself for five
    turns. ``current_tick=None`` means the caller has no tick authority (world /
    NPC projections); the gate is then skipped instead of inventing a tick.
    """

    if current_tick is None:
        return False
    delay = max(0, int(entry.get("delay", 0) or 0))
    return delay > 0 and int(current_tick) < delay
