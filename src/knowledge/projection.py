"""视角投影：对一批世界书条目批量计算指定视角的可见性结果。"""

from __future__ import annotations

from dataclasses import dataclass

from src.knowledge.visibility import (
    PUBLIC_VISIBILITY_MARKERS,
    classify_audience,
    entry_visible_to_viewer,
    visibility_values,
)


@dataclass(frozen=True)
class Viewer:
    """投影视角。``kind`` 取 ``gm`` / ``party`` / ``character``。

    ``character`` 视角必须携带 canonical ``uid``；``name`` 仅作次级匹配令牌。
    """

    kind: str
    uid: str = ""
    name: str = ""


def project_entries(entries: list[dict], viewer: Viewer) -> dict[str, dict]:
    """返回 ``entry_id -> {"visible", "audience", "subjects"}``。

    - ``visible``：该视角能否看到此条目（判定见 ``visibility.entry_visible_to_viewer``）。
    - ``audience``：条目初始受众（``public`` / ``character`` / ``gm``），与视角无关。
    - ``subjects``：``visible_to`` 中非公开标记的原始值，仅用于界面展示。

    无 ``id`` 或非字典的条目跳过。
    """
    public = {marker.casefold() for marker in PUBLIC_VISIBILITY_MARKERS}
    projections: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id") or "").strip()
        if not entry_id:
            continue
        subjects = [
            item
            for item in visibility_values(entry.get("visible_to"))
            if item.casefold() not in public
        ]
        projections[entry_id] = {
            "visible": entry_visible_to_viewer(
                entry, viewer.kind, viewer.uid, viewer.name
            ),
            "audience": classify_audience(entry),
            "subjects": subjects,
        }
    return projections
