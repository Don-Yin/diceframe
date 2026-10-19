"""Thin member/GM transport for authoritative resource recovery."""

from aiohttp import web

from src.webui.routes._common import _get_api
from src.webui.viewer import viewer_for


_GM_ACTIONS = frozenset({"approve", "reject", "reward", "luck"})
_FORBIDDEN_CODES = frozenset({
    "GM_ONLY", "MEMBER_REQUIRED", "ACTOR_FORBIDDEN", "SOURCE_FORBIDDEN",
    "NOT_SOURCE_OWNER", "PREVIEW_READ_ONLY", "RECOVERY_FORBIDDEN", "READ_ONLY",
})


def _error(code: str, status: int, message: str = "") -> web.Response:
    return web.json_response({"ok": False, "code": code, "error": message or code}, status=status)


def _context(request):
    api, key = _get_api(request), request.match_info["game_key"]
    instance = api.get_game_instance(key)
    if instance is None:
        return None, _error("GAME_NOT_FOUND", 404)
    viewer = viewer_for(request, instance)
    if not viewer.is_member:
        return None, _error("MEMBER_REQUIRED", 403)
    return (api.resource_recovery, key, viewer), None


def _response(result: dict) -> web.Response:
    code = result.get("code", "")
    status = 200 if result.get("ok") else 403 if code in _FORBIDDEN_CODES else 409
    if not result.get("ok") and code == "GAME_NOT_FOUND":
        status = 404
    if not result.get("ok") and code == "INVALID_REQUEST":
        status = 400
    if not result.get("ok") and code == "SAVE_FAILED":
        status = 500
    return web.json_response(result, status=status, headers={"Cache-Control": "no-store"})


async def get(request: web.Request) -> web.Response:
    context, error = _context(request)
    if error is not None:
        return error
    service, key, viewer = context
    try:
        return _response(service.get(key, viewer))
    except PermissionError as exc:
        return _error("RECOVERY_FORBIDDEN", 403, str(exc))
    except ValueError as exc:
        return _error("RECOVERY_INVALID_STATE", 409, str(exc))


async def mutate(request: web.Request) -> web.Response:
    context, error = _context(request)
    if error is not None:
        return error
    service, key, viewer = context
    if request.get("player_preview") and not request.get("player_delegate"):
        return _error("PREVIEW_READ_ONLY", 403)
    action = request.match_info["action"]
    if action in _GM_ACTIONS and not viewer.is_gm:
        return _error("GM_ONLY", 403)
    try:
        body = await request.json()
    except (ValueError, TypeError):
        return _error("RECOVERY_INVALID_REQUEST", 400)
    if not isinstance(body, dict):
        return _error("RECOVERY_INVALID_REQUEST", 400)
    if viewer.is_seat and "actor_uid" in body and body["actor_uid"] != viewer.uid:
        return _error("ACTOR_FORBIDDEN", 403)
    try:
        result = await service.mutate(key, viewer, action, body)
    except PermissionError as exc:
        return _error("RECOVERY_FORBIDDEN", 403, str(exc))
    except ValueError as exc:
        return _error("RECOVERY_INVALID_STATE", 409, str(exc))
    pool = request.app.get("connection_pool")
    if pool and result.get("ok") and not result.get("duplicate"):
        # Invalidate role-filtered reads; no source, entropy or result payload.
        await pool.broadcast(key, {"type": "table_settings_changed"})
    return _response(result)


def register(app: web.Application) -> None:
    prefix = "/api/games/{game_key}/recovery"
    app.router.add_get(prefix, get)
    app.router.add_post(prefix + "/{action:request|approve|reject|claim|reward|luck}", mutate)
