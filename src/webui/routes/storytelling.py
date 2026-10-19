"""Story mode and current-story speaker portrait routes."""

from __future__ import annotations

from aiohttp import web

from src.webui.routes._common import _get_api
from src.webui.routes.game_route_common import _gm_only_inst


def _status(result: dict) -> int:
    if result.get("ok"):
        return 200
    return {
        "GAME_NOT_FOUND": 404,
        "REWRITE_IN_PROGRESS": 409,
        "STORY_MODE_LOCKED": 409,
        "UNSUPPORTED_STORYTELLING_SCHEMA": 409,
        "UNKNOWN_SPEAKER": 404,
        "SAVE_FAILED": 500,
    }.get(str(result.get("error_code") or ""), 422)


async def _broadcast_story_settings(request: web.Request, game_key: str, result: dict) -> None:
    if not result.get("ok"):
        return
    pool = request.app.get("connection_pool")
    if pool is not None:
        await pool.broadcast(game_key, {"type": "story_settings_changed"})


async def api_set_story_mode(request: web.Request) -> web.Response:
    game_key = request.match_info["game_key"]
    _, denied = _gm_only_inst(request, game_key)
    if denied is not None:
        return denied
    body = await request.json()
    body = body if isinstance(body, dict) else {}
    result = await _get_api(request).set_story_mode(game_key, body.get("mode"))
    await _broadcast_story_settings(request, game_key, result)
    return web.json_response(result, status=_status(result))


async def api_story_speakers(request: web.Request) -> web.Response:
    game_key = request.match_info["game_key"]
    _, denied = _gm_only_inst(request, game_key)
    if denied is not None:
        return denied
    result = _get_api(request).list_story_speakers(game_key)
    return web.json_response(result, status=_status(result))


async def api_merge_story_speakers(request: web.Request) -> web.Response:
    game_key = request.match_info["game_key"]
    _, denied = _gm_only_inst(request, game_key)
    if denied is not None:
        return denied
    body = await request.json()
    body = body if isinstance(body, dict) else {}
    result = await _get_api(request).merge_story_speakers(game_key, body.get("source_id"), body.get("target_id"))
    await _broadcast_story_settings(request, game_key, result)
    return web.json_response(result, status=_status(result))


async def api_set_story_speaker_portrait(request: web.Request) -> web.Response:
    game_key = request.match_info["game_key"]
    _, denied = _gm_only_inst(request, game_key)
    if denied is not None:
        return denied
    body = await request.json()
    body = body if isinstance(body, dict) else {}
    result = await _get_api(request).set_story_speaker_portrait(
        game_key,
        request.match_info["speaker_id"],
        body.get("portrait"),
    )
    await _broadcast_story_settings(request, game_key, result)
    return web.json_response(result, status=_status(result))
