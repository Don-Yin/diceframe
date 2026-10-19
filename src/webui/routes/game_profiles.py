"""Profiles own their public application contracts; no private API traversal."""

from aiohttp import web

from src.webui.routes._common import _get_api, require_content_owner
from src.webui.viewer import viewer_for


async def catalog(request):
    if (error := require_content_owner(request)) is not None:
        return error
    return web.json_response(_get_api(request).game_profile_catalog())


async def create(request):
    if (error := require_content_owner(request)) is not None:
        return error
    try:
        if request.content_length and request.content_length > 16384:
            raise ValueError("profile creation body is too large")
        body = await request.json()
        return web.json_response(await _get_api(request).create_profile_game(body))
    except (ValueError, TypeError) as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)


async def view(request):
    api = _get_api(request)
    key = request.match_info["game_key"]
    instance = api.get_game_instance(key)
    viewer = viewer_for(request, instance)
    if not viewer.is_member:
        return web.json_response(
            {"ok": False, "error": "GAME_MEMBER_REQUIRED"}, status=403
        )
    try:
        return web.json_response(
            api.game_profile_view(
                key, viewer.uid, viewer.is_gm, request.query.get("actor", "")
            )
        )
    except (ValueError, TypeError) as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)


async def action(request):
    api = _get_api(request)
    key = request.match_info["game_key"]
    instance = api.get_game_instance(key)
    viewer = viewer_for(request, instance)
    if not viewer.is_member:
        return web.json_response(
            {"ok": False, "error": "GAME_MEMBER_REQUIRED"}, status=403
        )
    try:
        if request.content_length and request.content_length > 16384:
            raise ValueError("profile action body is too large")
        return web.json_response(
            await api.submit_profile_action(
                key, viewer.uid, viewer.is_gm, await request.json()
            )
        )
    except (ValueError, TypeError) as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    except Exception:
        return web.json_response(
            {"ok": False, "error": "profile action failed; state restored"}, status=500
        )


def register(app):
    app.router.add_get("/api/game-profiles", catalog)
    app.router.add_post("/api/game-profiles/create", create)
    app.router.add_get("/api/games/{game_key}/profile", view)
    app.router.add_post("/api/games/{game_key}/profile/actions", action)
