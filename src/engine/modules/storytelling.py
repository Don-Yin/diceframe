"""Persistent settings owned by the character dialogue/story presentation mode."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from src.engine.module_state import (
    ModuleStateError,
    ModuleStateSpec,
    get_module_state,
    register_module_state,
    set_module_state,
)
from src.engine import module_hooks

MODULE_NAME = "storytelling"
SCHEMA_VERSION = 1
MODES = frozenset({"prose", "dialogue"})
DEFAULT_MODE = "prose"
SPEAKER_ID_RE = re.compile(r"^[sg]_[a-f0-9]{20}$")


def fresh() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": DEFAULT_MODE,
        "portraits": {},
        "identity_namespace": "",
    }


def ensure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fresh()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return raw
    if not isinstance(raw.get("mode"), str) or raw.get("mode") not in MODES:
        raw["mode"] = DEFAULT_MODE
    if not isinstance(raw.get("identity_namespace"), str):
        raw["identity_namespace"] = ""
    portraits = raw.get("portraits")
    if not isinstance(portraits, dict):
        raw["portraits"] = {}
    else:
        # Speaker IDs are opaque canonical identities.  A malformed key must
        # never become a second lookup namespace during load or projection.
        raw["portraits"] = {
            str(speaker_id): value
            for speaker_id, value in portraits.items()
            if SPEAKER_ID_RE.fullmatch(str(speaker_id))
            and (value is None or isinstance(value, dict))
        }
    return raw


def require_writable(instance: Any) -> None:
    """Reject a future slot before any in-memory mutation."""
    modules = getattr(instance, "modules", None)
    if not isinstance(modules, dict):
        raise ModuleStateError("instance has no module state container")
    slot = modules.get(MODULE_NAME)
    if not isinstance(slot, dict):
        return
    if slot.get("schema_version") != SCHEMA_VERSION:
        raise ModuleStateError(
            f"unsupported {MODULE_NAME} module schema: {slot.get('schema_version')!r}"
        )


def mode(instance: Any) -> str:
    value = get_module_state(instance, MODULE_NAME).get("mode")
    return value if isinstance(value, str) and value in MODES else DEFAULT_MODE


def _read_slot(instance: Any) -> dict[str, Any]:
    """Read a slot without materializing a missing module container entry."""
    modules = getattr(instance, "modules", None)
    if not isinstance(modules, dict):
        raise ModuleStateError("instance has no module state container")
    slot = modules.get(MODULE_NAME)
    if slot is None:
        return fresh()
    if not isinstance(slot, dict):
        return fresh()
    if slot.get("schema_version") != SCHEMA_VERSION:
        raise ModuleStateError(
            f"unsupported {MODULE_NAME} module schema: {slot.get('schema_version')!r}"
        )
    return slot


def read_mode(instance: Any) -> str:
    value = _read_slot(instance).get("mode")
    return value if isinstance(value, str) and value in MODES else DEFAULT_MODE


def validate_mode(value: Any) -> str:
    """Validate and return a canonical story mode without touching an instance."""
    if not isinstance(value, str) or value not in MODES:
        raise ValueError(f"unsupported storytelling mode: {value!r}")
    return value


def identity_namespace(instance: Any) -> str:
    """Stable namespace for deterministic story speaker identities."""
    value = _read_slot(instance).get("identity_namespace")
    if isinstance(value, str) and value:
        return value
    return str(getattr(instance, "run_id", "") or "")


def replace_mode(instance: Any, value: str) -> None:
    require_writable(instance)
    validate_mode(value)
    get_module_state(instance, MODULE_NAME)["mode"] = value


def portraits(instance: Any) -> dict[str, Any]:
    return get_module_state(instance, MODULE_NAME)["portraits"]


def portrait_overrides(instance: Any) -> dict[str, Any]:
    """Return normalized overrides without creating a missing slot."""
    slot = _read_slot(instance)
    raw = slot.get("portraits")
    if not isinstance(raw, dict):
        return {}
    return {
        str(speaker_id): value
        for speaker_id, value in raw.items()
        if SPEAKER_ID_RE.fullmatch(str(speaker_id))
        and (value is None or isinstance(value, dict))
    }


def speaker_aliases(instance: Any) -> dict[str, str]:
    """Read explicit GM repairs; never infer identities from display names."""
    raw = _read_slot(instance).get("speaker_aliases", {})
    if not isinstance(raw, dict) or len(raw) > 4096:
        raise ModuleStateError("invalid story speaker aliases")
    for source, target in raw.items():
        if (not isinstance(source, str) or not source.startswith("g_")
                or SPEAKER_ID_RE.fullmatch(source) is None
                or not isinstance(target, str) or SPEAKER_ID_RE.fullmatch(target) is None):
            raise ModuleStateError("invalid story speaker identity")
    result: dict[str, str] = {}
    for source in raw:
        target, seen = source, set()
        while target in raw:
            if target in seen:
                raise ModuleStateError("cyclic story speaker aliases")
            seen.add(target)
            target = raw[target]
        result[source] = target
    return result


def merge_speaker(instance: Any, source: str, target: str, portrait: Any) -> None:
    require_writable(instance)
    aliases = speaker_aliases(instance)
    if (not source.startswith("g_") or source == target or source in aliases
            or target in aliases or SPEAKER_ID_RE.fullmatch(source) is None
            or SPEAKER_ID_RE.fullmatch(target) is None or len(aliases) >= 4096):
        raise ValueError("invalid story identity repair")
    aliases = {key: target if value == source else value for key, value in aliases.items()}
    aliases[source] = target
    set_portrait(instance, target, portrait)
    get_module_state(instance, MODULE_NAME)["speaker_aliases"] = aliases


def set_portrait(instance: Any, speaker_id: str, portrait: dict[str, Any] | None) -> None:
    require_writable(instance)
    speaker_key = str(speaker_id or "")
    if SPEAKER_ID_RE.fullmatch(speaker_key) is None:
        raise ValueError("invalid speaker id")
    if portrait is not None and not isinstance(portrait, dict):
        raise ValueError("portrait must be an object or null")
    target = portraits(instance)
    if portrait is None:
        # An explicit null suppresses any generated/default portrait for this
        # speaker; absence means that the normal portrait resolution applies.
        target[speaker_key] = None
    else:
        target[speaker_key] = dict(portrait)


def snapshot(instance: Any) -> dict[str, Any] | None:
    """Take an owner snapshot while retaining absence of this slot."""
    modules = getattr(instance, "modules", None)
    if not isinstance(modules, dict):
        raise ModuleStateError("instance has no module state container")
    slot = modules.get(MODULE_NAME)
    return deepcopy(slot) if isinstance(slot, dict) else None


def restore(instance: Any, value: dict[str, Any] | None) -> None:
    """Restore an owner snapshot, including a previously absent slot."""
    modules = getattr(instance, "modules", None)
    if not isinstance(modules, dict):
        raise ModuleStateError("instance has no module state container")
    if value is None:
        modules.pop(MODULE_NAME, None)
        return
    set_module_state(instance, MODULE_NAME, deepcopy(value))


def preference_snapshot(instance: Any) -> dict[str, Any]:
    """Capture run carrying preferences without reusing guest identities."""
    require_writable(instance)
    return {
        "mode": read_mode(instance),
        "portraits": {
            speaker_id: deepcopy(portrait)
            for speaker_id, portrait in portrait_overrides(instance).items()
            if speaker_id.startswith("s_")
        },
        "identity_namespace": identity_namespace(instance),
    }


def restore_preferences(instance: Any, value: Any) -> None:
    """Restore carried preferences into a supported module slot."""
    require_writable(instance)
    if not isinstance(value, dict):
        raise ValueError("invalid storytelling preference snapshot")
    next_mode = value.get("mode", DEFAULT_MODE)
    if not isinstance(next_mode, str) or next_mode not in MODES:
        raise ValueError("invalid storytelling mode in preference snapshot")
    namespace = value.get("identity_namespace", "")
    if not isinstance(namespace, str):
        raise ValueError("invalid storytelling identity namespace")
    raw_portraits = value.get("portraits", {})
    if not isinstance(raw_portraits, dict):
        raise ValueError("invalid storytelling portrait preferences")
    next_portraits = {
        str(speaker_id): deepcopy(portrait)
        for speaker_id, portrait in raw_portraits.items()
        if SPEAKER_ID_RE.fullmatch(str(speaker_id))
        and str(speaker_id).startswith("s_")
        and (portrait is None or isinstance(portrait, dict))
    }
    slot = get_module_state(instance, MODULE_NAME)
    slot["mode"] = next_mode
    slot["portraits"] = next_portraits
    slot["identity_namespace"] = namespace
    slot.pop("speaker_aliases", None)


def copy_preferences(candidate: Any, source: Any) -> None:
    """Carry mode and stable NPC portraits to a new run.

    Guest speaker identities are scoped to the source run and are therefore
    deliberately omitted.
    """
    require_writable(source)
    require_writable(candidate)
    restore_preferences(candidate, preference_snapshot(source))


SPEC = ModuleStateSpec(
    name=MODULE_NAME,
    schema_version=SCHEMA_VERSION,
    fresh=fresh,
    ensure=ensure,
)
register_module_state(SPEC)


def _prepare_reset(instance: Any) -> None:
    # Freeze the original namespace before reset rotates run_id. Guest cast
    # belongs to the erased run; stable NPC portrait choices remain.
    restore_preferences(instance, preference_snapshot(instance))


def _record_state(instance: Any, kind: str, value: Any) -> None:
    if kind == module_hooks.STORY_MODE:
        replace_mode(instance, value)


def _read_state(instance: Any, kind: str) -> Any:
    if kind == module_hooks.STORY_MODE:
        return read_mode(instance)
    if kind == module_hooks.STORY_PORTRAITS:
        return portrait_overrides(instance)
    if kind == module_hooks.STORY_SPEAKER_ALIASES:
        return speaker_aliases(instance)
    if kind == module_hooks.STORY_IDENTITY_NAMESPACE:
        return identity_namespace(instance)
    if kind == module_hooks.GM_PROMPT_SECTIONS:
        if read_mode(instance) == "dialogue":
            from src.engine.story import story_prompt
            return [story_prompt(instance)]
        return []
    return None


module_hooks.register(module_hooks.INSTANCE_RESET_PREFLIGHT, MODULE_NAME, require_writable)
module_hooks.register(module_hooks.INSTANCE_RESET_BEGIN, MODULE_NAME, _prepare_reset)
module_hooks.register(module_hooks.INSTANCE_NEW_RUN_PREFLIGHT, MODULE_NAME, require_writable)
module_hooks.register(module_hooks.INSTANCE_NEW_RUN, MODULE_NAME, copy_preferences)
module_hooks.register(module_hooks.STATE_RECORD, MODULE_NAME, _record_state)
module_hooks.register(module_hooks.STATE_READ, MODULE_NAME, _read_state)
