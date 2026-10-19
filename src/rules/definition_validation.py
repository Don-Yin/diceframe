"""Editor admission diagnostics for the generic rule resource contract."""
from __future__ import annotations

from typing import Any

_RESERVED_SHEET_KEYS = frozenset({
    "hp", "max_hp", "resources", "attributes", "skills", "inventory", "equipment",
    "currency", "gold", "character_name", "race", "class", "level", "background",
    "deceased", "conditions", "key_items", "attr_points_max",
})


def validate_special_stats(template: dict[str, Any]) -> list[dict[str, str]]:
    """Validate fields actually consumed by character resource initialization.

    Extra extension metadata is opaque. No parser guess turns an arbitrary
    top-level field into an executable resource or changes existing characters.
    """
    if "special_stats" not in template:
        return []
    stats = template["special_stats"]
    if not isinstance(stats, list):
        return [{"path": "special_stats", "message": "必须是资源声明数组，例如 [{key: mp, name: 魔力, max: 20}]"}]
    diagnostics = []
    seen = set()
    for index, stat in enumerate(stats):
        path = f"special_stats[{index}]"
        if not isinstance(stat, dict):
            diagnostics.append({"path": path, "message": "每项必须是资源声明对象"})
            continue
        key = stat.get("key")
        if not isinstance(key, str) or not key.strip() or key != key.strip() or key in _RESERVED_SHEET_KEYS or key in seen:
            diagnostics.append({"path": f"{path}.key", "message": "需要唯一的资源标识，且不可覆盖角色内置字段（如 hp、attributes）"})
        else:
            seen.add(key)
        maximum = stat.get("max", 99)
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
            diagnostics.append({"path": f"{path}.max", "message": "资源上限必须是大于 0 的整数"})
        elif "initial" in stat:
            initial = stat["initial"]
            if isinstance(initial, bool) or not isinstance(initial, int) or not 0 <= initial <= maximum:
                diagnostics.append({"path": f"{path}.initial", "message": "初始值必须是 0 到 max 之间的整数"})
    return diagnostics
