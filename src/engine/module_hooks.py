"""Lifecycle hooks capability modules register to join the core game flow (#515).

The core flow calls a hook point; it never names the module behind it.  A
point with no registered handler is a no-op (``run``) or answers with the
caller's default (``ask``), so deleting a capability module leaves a playable
game that only lacks that capability.

Hook points are a closed set: registering an unknown point is an error, so a
typo cannot silently detach a module.  Handlers run in registration order.
This registry must not import GameInstance or any concrete module.
"""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from typing import Any

# reset_round_checks: handler(instance) -> None.  Clear round-scoped state.
ROUND_RESET = "round.reset"
# begin_round_processing: handler(instance) -> None.  Drop the previous
# round's short-lived presentation state.
ROUND_PROCESSING_BEGIN = "round.processing.begin"
# Before an in-place reset touches anything: handler(instance) -> None.
# Raise to refuse (e.g. an unsupported slot schema); nothing has changed yet.
INSTANCE_RESET_PREFLIGHT = "instance.reset.preflight"
# After all reset preflights, before the old run identity is rotated.
INSTANCE_RESET_BEGIN = "instance.reset.begin"
# In-place game reset: handler(instance) -> None.  Clear run-scoped state.
INSTANCE_RESET = "instance.reset"
# Before creating a replacement run: handler(source) -> None.
INSTANCE_NEW_RUN_PREFLIGHT = "instance.new_run.preflight"
# Carry optional preferences to an unpublished new run: handler(candidate, source).
INSTANCE_NEW_RUN = "instance.new_run"
# Before rollback_last_round / abort_round_processing change anything:
# handler(instance) -> None.  Raise to refuse.
ROUND_RECOVERY_PREFLIGHT = "round.recovery.preflight"
# Judgment failed: handler(instance) -> bool.  Restore this round's state as of
# judgment entry; answer whether anything was restored.  Runs after players are
# restored and before the judgment-entry entity snapshot.
ROUND_ABORT = "round.abort"
# A rollback / swipe rewinds to ``target_round``, before economy reversal:
# handler(instance, target_round) -> None.
ROUND_REWIND_BEGIN = "round.rewind.begin"
# After players were restored from ``entry`` (the log entry of
# ``target_round``): handler(instance, entry, target_round, source) -> None,
# ``source`` one of REWIND_SOURCE_*.  Restore module state the entry carries and
# drop live state of the discarded branch.
ROUND_REWIND_RESTORE = "round.rewind.restore"
REWIND_SOURCE_ROLLBACK = "rollback"
REWIND_SOURCE_SWIPE = "swipe"
# finish_judgment built the round's log entry: handler(instance, entry,
# pre_snapshot) -> None.  Add module fields / state_changes to ``entry`` and
# retire live round state.  ``pre_snapshot`` is whatever round processing
# captured as COMBAT_EXTENSION_SNAPSHOT before applying the state update.
ROUND_COMMIT = "round.commit"
# Optional admission policy for narrator NPC state writes. False rejects a new
# authoritative entity; ordinary background narration remains possible.
NPC_ADMISSION = "npc.admission"
# False freezes ordinary run writers; finalization service uses its explicit
# administrative gate for preparing/cancelling/committing the freeze itself.
AUTHORITATIVE_WRITE_ALLOWED = "authority.write.allowed"
# Rule-declared development records from server-settled checks, not LLM tags.
SETTLED_SKILL_USE = "checks.skill_use.settled"
# Before a write that may mark or forget a seat: handler(instance) -> None.
# Raise to refuse; nothing has changed yet.
SEAT_PREFLIGHT = "seat.preflight"
# A seat acted: handler(instance, user_id, source) -> None, ``source`` one of
# SEAT_SOURCE_*.  The owning module decides whether that counts.
SEAT_ACTED = "seat.acted"
# A seat left the roster, or its first mark was undone: handler(instance, user_id).
SEAT_FORGOTTEN = "seat.forgotten"
# Has this seat acted in the current run: handler(instance, user_id) -> bool | None.
# Without a module the answer is False (no seat lock).
SEAT_HAS_ACTED = "seat.has_acted"
SEAT_SOURCE_ACTION = "action"  # declared a round action (queued or deferred)
SEAT_SOURCE_LUCK = "luck"  # spent luck on its own check
SEAT_SOURCE_INTENT = "intent"  # a player-side rules-aware intent was applied for it
# Store module-held state by kind: handler(instance, kind, value) -> None.
STATE_RECORD = "module.state.record"
# Read module-held state by kind: handler(instance, kind) -> value | None.
# ``None`` means "not mine / nothing stored"; the first other answer wins.
STATE_READ = "module.state.read"
STATE_WRITE_PREFLIGHT = "module.state.write.preflight"

# State kinds.  List-valued unless noted; the owning module answers for its kinds.
OVERREACH = "overreach"
WORLD_LEGALITY = "world_legality"
WORLD_EVENTS = "world_events"
QUICK_ACTIONS = "quick_actions"
GM_DIRECTIVES = "gm_directives"
COMBAT_RESULTS = "combat_results"
STATE_UPDATE = "state_update"  # dict | None
TOKEN_BUDGET_BUMP = "token_budget_bump"  # dict | None
# Live Lorebook timer dict (entry id -> timer); callers may mutate it.
LOREBOOK_TIMERS = "lorebook_timers"  # dict | None
# GM-visible degradation events and per-component status (not round-scoped).
HEALTH_EVENTS = "health_events"
HEALTH_STATUS = "health_status"  # dict | None
# Check reveal records (check id -> record).
CHECK_REVEALS = "check_reveals"  # dict | None
# Room away-control policy; read with ``ask(STATE_READ, ..., default=...)``.
AWAY_CONTROL_POLICY = "away_control_policy"  # str | None
# Live private messages (uid -> list) and public table talk; callers may mutate.
PRIVATE_LOG = "private_log"  # dict | None
TABLE_TALK = "table_talk"
# Read-only combat turn view (combat_state / combat_active / initiative_order /
# initiative_current); read with ``combat_view``.
COMBAT_VIEW = "combat_view"  # dict | None
# Portable adventure scene-image reference and the map-background selection.
SCENE_IMAGE = "scene_image"  # dict | None
MAP_BACKGROUND = "map_background"  # dict | None
# Live generic combat-extension payload (scheduler + narration queue); callers
# may mutate it.
COMBAT_EXTENSION = "combat_extension"  # dict | None
# Combat-extension state with this round's tracked entity fields, for a log
# entry's pre-state; computed on read.
COMBAT_EXTENSION_SNAPSHOT = "combat_extension_snapshot"  # dict | None
# Public narration presentation preferences and optional GM prompt sections.
STORY_MODE = "story_mode"  # str | None; absent owner means prose
STORY_PORTRAITS = "story_portraits"  # dict | None
STORY_SPEAKER_ALIASES = "story_speaker_aliases"  # dict | None
STORY_IDENTITY_NAMESPACE = "story_identity_namespace"  # str | None
GM_PROMPT_SECTIONS = "gm_prompt_sections"  # list[str]
NARRATIVE_VIEW = "narrative_view"  # dict, including verbatim legacy scene values
NARRATIVE_SCENE = "narrative_scene"
NARRATIVE_TIME = "narrative_time"
NARRATIVE_SUMMARY = "narrative_summary"
NARRATIVE_KEY_FACTS = "narrative_key_facts"
NARRATIVE_CONFIRMED_ITEMS = "narrative_confirmed_items"
NARRATION_PREFERENCES = "narration_preferences"  # dict, preserving None versus explicit empty style
CHECK_PRESENTATION = "check_presentation"  # dict, neutral auto / 60
NARRATIVE_PERSPECTIVE = "narrative_perspective"
GM_STYLE_OVERRIDE = "gm_style_override"
DICE_REVEAL_MODE = "dice_reveal_mode"
LUCK_TIMEOUT_SECONDS = "luck_timeout_seconds"
PUSH_ENABLED = "push_enabled"
QUICK_ACTIONS_ENABLED = "quick_actions_enabled"
RUN_LIFECYCLE_VIEW = "run_lifecycle_view"  # public status/id/revision only
# handler(instance, revisions) contributes its own GM-only invalidation value.
# No module's private data is returned to clients by this contract.
GM_WORKSPACE_REVISIONS = "gm.workspace.revisions"

HOOK_POINTS = frozenset({
    GM_WORKSPACE_REVISIONS,
    NPC_ADMISSION,
    AUTHORITATIVE_WRITE_ALLOWED,
    SETTLED_SKILL_USE,
    ROUND_RESET, ROUND_PROCESSING_BEGIN, INSTANCE_RESET_PREFLIGHT, INSTANCE_RESET_BEGIN, INSTANCE_RESET,
    INSTANCE_NEW_RUN_PREFLIGHT, INSTANCE_NEW_RUN,
    ROUND_RECOVERY_PREFLIGHT, ROUND_ABORT, ROUND_REWIND_BEGIN, ROUND_REWIND_RESTORE, ROUND_COMMIT,
    SEAT_PREFLIGHT, SEAT_ACTED, SEAT_FORGOTTEN, SEAT_HAS_ACTED,
    STATE_RECORD, STATE_READ, STATE_WRITE_PREFLIGHT,
})

Handler = Callable[..., Any]
_HANDLERS: dict[str, list[tuple[str, Handler]]] = {point: [] for point in HOOK_POINTS}


def register(point: str, owner: str, handler: Handler) -> None:
    """Register ``handler`` for ``point`` on behalf of module ``owner``.

    Re-registering the same owner on the same point replaces its handler.
    """
    if point not in HOOK_POINTS:
        raise ValueError(f"unknown module hook point: {point!r}")
    if not owner:
        raise ValueError("module hook requires an owner")
    if not callable(handler):
        raise TypeError("module hook handler must be callable")
    handlers = _HANDLERS[point]
    handlers[:] = [(name, fn) for name, fn in handlers if name != owner]
    handlers.append((owner, handler))


def unregister_owner(owner: str) -> dict[str, Handler]:
    """Detach every handler of ``owner``; returns them by point for re-registration."""
    removed: dict[str, Handler] = {}
    for point, handlers in _HANDLERS.items():
        for name, fn in handlers:
            if name == owner:
                removed[point] = fn
        handlers[:] = [(name, fn) for name, fn in handlers if name != owner]
    return removed


def owners(point: str) -> tuple[str, ...]:
    return tuple(name for name, _ in _HANDLERS[point])


def run(point: str, *args: Any) -> None:
    """Call every handler for ``point``."""
    for _, handler in tuple(_HANDLERS[point]):
        handler(*args)


def run_any(point: str, *args: Any) -> bool:
    """Call every handler for ``point``; True when any answered truthy."""
    answered = False
    for _, handler in tuple(_HANDLERS[point]):
        if handler(*args):
            answered = True
    return answered


def ask(point: str, *args: Any, default: Any) -> Any:
    """Return the first non-``None`` handler answer, or ``default``."""
    for _, handler in tuple(_HANDLERS[point]):
        answer = handler(*args)
        if answer is not None:
            return answer
    return default


def record(instance: Any, kind: str, value: Any) -> None:
    """Store ``kind``; dropped when no module keeps it."""
    run(STATE_RECORD, instance, kind, value)


def preflight(instance: Any, kind: str) -> None:
    """Validate an optional state owner before any part of a transaction writes."""
    run(STATE_WRITE_PREFLIGHT, instance, kind)


def narrative_view(instance: Any) -> dict[str, Any]:
    """Narrative state projection, neutral when its optional owner is absent."""
    neutral = {"summary": {}, "key_facts": [], "confirmed_items": [], "game_time": "", "scene": ""}
    view = read_value(instance, NARRATIVE_VIEW)
    return {**neutral, **view} if view is not None else neutral


def narration_preferences(instance: Any) -> dict[str, Any]:
    neutral = {"narrative_perspective": "auto", "gm_style_override": None}
    view = read_value(instance, NARRATION_PREFERENCES)
    return {**neutral, **view} if view is not None else neutral


def check_presentation(instance: Any) -> dict[str, Any]:
    neutral = {"dice_reveal_mode": "auto", "luck_timeout_seconds": 60}
    view = read_value(instance, CHECK_PRESENTATION)
    return {**neutral, **view} if view is not None else neutral


def read(instance: Any, kind: str) -> list:
    """List-valued state of ``kind``; empty when no module keeps it."""
    answer = ask(STATE_READ, instance, kind, default=[])
    return answer if isinstance(answer, list) else []


def read_value(instance: Any, kind: str) -> dict | None:
    """Dict-valued state of ``kind``; ``None`` when absent or no module keeps it."""
    answer = ask(STATE_READ, instance, kind, default=None)
    return answer if isinstance(answer, dict) else None


def gm_workspace_revision(instance: Any) -> str:
    """Opaque GM-only token for optional same-round workspace resources."""
    revisions: dict[str, Any] = {}
    run(GM_WORKSPACE_REVISIONS, instance, revisions)
    if not revisions:
        return ''
    return hashlib.sha256(json.dumps(revisions, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def seat_has_acted(instance: Any, user_id: str) -> bool:
    """Has this seat acted in the current run; False when no module tracks seats."""
    return bool(ask(SEAT_HAS_ACTED, instance, user_id, default=False))


def neutral_combat_view() -> dict[str, Any]:
    """The combat view of a game nothing projects combat for."""
    return {
        "combat_state": "none",
        "combat_active": False,
        "initiative_order": [],
        "initiative_current": 0,
    }


def combat_view(instance: Any) -> dict[str, Any]:
    """A fresh combat turn view; neutral when no module projects one."""
    view = read_value(instance, COMBAT_VIEW)
    return {**neutral_combat_view(), **view} if view is not None else neutral_combat_view()
