"""世界书条目可见性规则 —— ``visible_to`` 解析与视角判定的单一事实来源。

所有消费者（问 GM/KP 安全上下文、世界书视角预览等）必须复用这里的谓词，
不得各自复制解析或匹配逻辑。判定对缺失/空 ``visible_to`` 一律 fail-closed（GM-only）。
"""

from __future__ import annotations

import json

# 规范的"全队可见"标记（大小写不敏感；中英文写法均见于历史数据）。
PUBLIC_VISIBILITY_MARKERS = frozenset({
    "*", "all", "everyone", "public", "party", "players",
    "公开", "所有人", "全体玩家",
})


def visibility_values(value: object) -> list[str]:
    """把 ``visible_to`` 归一化为非空字符串列表。

    兼容列表/元组/集合、JSON 字符串与逗号分隔字符串三种历史形状；
    其余输入（含 None）返回空列表。
    """
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            decoded = [part.strip() for part in raw.split(",")]
        value = decoded
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def classify_audience(entry: object) -> str:
    """按初始 ``visible_to`` 归类条目受众：``public`` / ``character`` / ``gm``。

    空或缺失的 ``visible_to`` 归为 ``gm``（GM 秘密），与判定的 fail-closed 语义一致。
    """
    if not isinstance(entry, dict):
        return "gm"
    values = visibility_values(entry.get("visible_to"))
    if not values:
        return "gm"
    public = {marker.casefold() for marker in PUBLIC_VISIBILITY_MARKERS}
    if any(item.casefold() in public for item in values):
        return "public"
    return "character"


def entry_visible_to_viewer(
    entry: object,
    viewer_kind: str,
    uid: str = "",
    name: str = "",
) -> bool:
    """条目对指定视角是否可见的唯一共享谓词。

    - ``gm``：全部可见。
    - ``party``：仅公开标记条目可见（与问 GM 公开回答的过滤语义一致）。
    - ``character``：公开标记，或 ``visible_to`` 按 casefold 命中 uid / 角色名。

    ``uid`` 是 canonical identity；``name`` 只是兼容自由文本 ``visible_to`` 的
    次级匹配令牌，显示名本身不作为身份。未知视角一律不可见。
    """
    if viewer_kind == "gm":
        return True
    if not isinstance(entry, dict):
        return False
    visible = {item.casefold() for item in visibility_values(entry.get("visible_to"))}
    if not visible:
        return False
    public = {marker.casefold() for marker in PUBLIC_VISIBILITY_MARKERS}
    if viewer_kind == "party":
        return bool(visible & public)
    if viewer_kind != "character":
        return False
    allowed = set(public)
    if uid:
        allowed.add(str(uid).strip().casefold())
    if name:
        allowed.add(str(name).strip().casefold())
    return bool(visible & allowed)
