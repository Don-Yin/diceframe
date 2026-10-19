"""Adventure admission, independent of any concrete character ruleset."""
from __future__ import annotations

from typing import Any

from src.adventures.graph_v2 import ADVENTURE_GRAPH_FORMAT_V2

NARRATIVE_RUNTIME_ID = 'core:adventure'
NARRATIVE_RUNTIME_VERSION = 1


def default_runtime_requirement() -> dict[str, int | str]:
    return {'id': NARRATIVE_RUNTIME_ID, 'minimum_version': NARRATIVE_RUNTIME_VERSION}


def narrative_requirement_supported(runtime_id: str, minimum: int) -> bool:
    return runtime_id == NARRATIVE_RUNTIME_ID and type(minimum) is int and 1 <= minimum <= NARRATIVE_RUNTIME_VERSION


def compatibility_reasons(manifest: Any, runtime: Any | None, world_id: str) -> list[str]:
    reasons: list[str] = []
    if runtime is None:
        reasons.append('ruleset_runtime_unavailable')
    else:
        formats = getattr(runtime.capabilities, 'adventure_formats', ()) or ()
        if manifest.format not in formats:
            reasons.append('adventure_format_unsupported')
        if manifest.required_runtime_id == NARRATIVE_RUNTIME_ID:
            if manifest.format != ADVENTURE_GRAPH_FORMAT_V2:
                reasons.append('adventure_format_unsupported')
            if not narrative_requirement_supported(manifest.required_runtime_id, manifest.required_runtime_version):
                reasons.append('runtime_version_too_old')
        else:
            if runtime.runtime_id != manifest.required_runtime_id:
                reasons.append('runtime_id_mismatch')
            if runtime.runtime_version < manifest.required_runtime_version:
                reasons.append('runtime_version_too_old')
    if manifest.world_policy == 'fixed' and str(world_id or '') != manifest.recommended_world_id:
        reasons.append('world_mismatch')
    return list(dict.fromkeys(reasons))
