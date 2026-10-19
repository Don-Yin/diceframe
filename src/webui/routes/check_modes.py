"""Authenticated transport for check-mode requests and GM adjudication."""
from aiohttp import web

from src.webui.routes._common import _get_api
from src.webui.viewer import viewer_for


async def read(request: web.Request) -> web.Response:
    api, key = _get_api(request), request.match_info["game_key"]
    inst = api.get_game_instance(key)
    if inst is None:
        return web.json_response({"ok": False, "error_code": "game_missing"}, status=404)
    result = api.check_mode_settings(key, viewer_for(request, inst))
    return web.json_response(result, status=200 if result.get("ok") else 403)


async def update(request: web.Request) -> web.Response:
    api, key = _get_api(request), request.match_info["game_key"]
    inst = api.get_game_instance(key)
    if inst is None:
        return web.json_response({"ok": False, "error_code": "game_missing"}, status=404)
    if request.get("player_preview") and not request.get("player_delegate"):
        return web.json_response({"ok": False, "error_code": "preview_read_only"}, status=403)
    try:
        body = await request.json()
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error_code": "invalid_request"}, status=400)
    result = await api.update_check_mode_settings(key, viewer_for(request, inst),
        request.match_info["user_id"], request.match_info["operation"], body)
    if result.get("ok"):
        pool = request.app.get("connection_pool")
        if pool:
            await pool.broadcast(key, {"type": "table_settings_changed"})
    return web.json_response(result, status=200 if result.get("ok") else 403 if result.get("error_code") == "forbidden" else 409)


def register(app: web.Application) -> None:
    app.router.add_get("/api/games/{game_key}/check-modes", read)
    app.router.add_post("/api/games/{game_key}/check-modes/seats/{user_id}/{operation:request|grant|reject|clear}", update)
