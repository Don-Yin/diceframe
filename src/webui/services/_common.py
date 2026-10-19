"""WebUI services 共享的常量与工具。"""

from typing import Any

_GAME_KEY_SEP = "|"
_INVALID_GAME_KEY = ("__invalid_game_key__", "", "")

# 跨 HTTP、SSE 与 service 共用的输入边界。业务限制放在 service 层，
# routes 仅重新导入，避免不同入口各自维护一份数值。
MAX_LOREBOOK_CHARS = 5000
MAX_ACTION_CHARS = 1000
MAX_ACTIONS_PER_TURN = 3
MAX_SEED_CHARS = 2000


def professional_character_validation_error(exc: ValueError) -> tuple[str, str]:
    """Return a stable API error while keeping professional validation fail-closed."""

    code = str(getattr(exc, "error_code", "") or "")
    if code == "PROFESSIONAL_CHARACTER_BLUEPRINT_REQUIRED":
        return code, (
            "专业角色缺少可重建的规则数据，请使用当前规则的专业建卡器完成后再创建或加入。"
            "旧角色卡不能仅凭展示属性安全转换。"
        )
    return "INVALID_PROFESSIONAL_CHARACTER", str(exc)


def _is_safe_game_key_part(s: str) -> bool:
    """校验 game_key 片段不可影响存档路径结构。"""
    return "/" not in s and "\\" not in s and ".." not in s and "#" not in s and ":" not in s


def _parse_game_key(game_key: str) -> tuple[str, str, str]:
    """解析公开 game_key，并拒绝路径穿越片段。

    A game key has at most three ``|`` parts. Extra parts used to be dropped,
    which let ``a|b|c|anything`` alias the same game under a different key
    (and slip past per-game state keyed by the raw string); they are refused.
    """
    raw = str(game_key or "")
    parts = raw.split(_GAME_KEY_SEP)
    if len(parts) > 3:
        return _INVALID_GAME_KEY
    parsed = tuple(parts) if len(parts) == 3 else (raw, "", "")
    if not all(_is_safe_game_key_part(part) for part in parsed):
        return _INVALID_GAME_KEY
    return parsed


def canonical_game_key(game_key: str) -> str:
    """The one spelling of a public game key, for keying per-game state."""
    return _GAME_KEY_SEP.join(_parse_game_key(game_key))


def _is_safe_world_id(s: str) -> bool:
    """校验 world_id 不含路径遍历字符（允许中文等正常字符）。"""
    return bool(s) and "/" not in s and "\\" not in s and ".." not in s


def resolve_default_scene_image(
    resolver: Any,
    world_id: str,
    rule_id: str,
    selection_key: str = "",
) -> dict[str, Any]:
    """Call the optional keyed default-image resolver without breaking old adapters.

    Third-party lifecycle test adapters and older integrations still expose the
    original two-argument callable. The keyed call is used by the built-in API
    so each new save can select a stable member from its ruleset/world pool;
    the fallback keeps those adapters source-compatible.
    """

    if selection_key:
        try:
            return resolver(world_id, rule_id, selection_key)
        except TypeError:
            pass
    return resolver(world_id, rule_id)


def is_game_gm(inst: Any, user_id: str, owner_authenticated: bool = False) -> bool:
    """GM 判定统一入口：该局主 GM，或已登录 owner（多人共用管理员账号都算 GM）。

    所有 GM 门控必须走这里，避免散落的 ``== gm_uid`` 各自为政；
    后续多 GM（co_gm_uids）也只需扩展这一个函数。
    """
    if inst is None or not user_id:
        return False
    if user_id == getattr(inst, "gm_uid", ""):
        return True
    return bool(owner_authenticated)
