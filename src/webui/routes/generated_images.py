"""HTTP routes for the built-in image-generation system."""

from __future__ import annotations

from aiohttp import web

from src.imagegen import IMAGE_PURPOSES, ImageGenerationError, game_image_owner_id
from src.webui.routes._common import _get_api, _require_confirmed_request
from src.webui.viewer import viewer_for
from src.webui.routes.auth import ACCESS_PASSWORD_CONFIGURED_KEY


async def api_image_generation_status(request: web.Request) -> web.Response:
    return web.json_response(_get_api(request).image_generation_status())


async def api_optimize_image_prompt(request: web.Request) -> web.Response:
    denied = _require_confirmed_request(request)
    if denied is not None:
        return denied
    query = getattr(request, "query", {})
    if query.get("user") or query.get("share"):
        return web.json_response(
            {"ok": False, "error": "玩家分享页不可使用 AI 优化提示词"},
            status=403,
        )
    if request.get(ACCESS_PASSWORD_CONFIGURED_KEY, False) and not request.get(
        "owner_authenticated", False,
    ):
        return web.json_response(
            {"ok": False, "error": "仅管理员可以使用 AI 优化提示词"},
            status=403,
        )
    body = await request.json() if request.can_read_body else {}
    if not isinstance(body, dict):
        return web.json_response(
            {"ok": False, "error": "优化请求必须是 JSON 对象"}, status=400,
        )
    try:
        result = await _get_api(request).optimize_image_prompt(
            field=str(body.get("field") or ""),
            text=str(body.get("text") or ""),
            language=str(body.get("language") or ""),
        )
    except ImageGenerationError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response(result)


async def api_generate_image(request: web.Request) -> web.Response:
    body = await request.json() if request.can_read_body else {}
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "生图请求必须是 JSON 对象"}, status=400)
    purpose = str(body.get("purpose") or "freeform").strip().lower()
    if purpose not in IMAGE_PURPOSES:
        return web.json_response({"ok": False, "error": "不支持的图片用途"}, status=400)
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        return web.json_response({"ok": False, "error": "请填写画面描述"}, status=400)
    api = _get_api(request)
    game_key = str(request.match_info.get("game_key") or body.get("game_key") or "").strip()
    owner_type = "library"
    owner_id = str(request.get("user_id", "") or "local")
    if game_key:
        inst = api.get_game_instance(game_key)
        if inst is None:
            return web.json_response({"ok": False, "error": "游戏不存在"}, status=404)
        user_id = str(request.get("user_id", "") or "")
        is_gm = bool(user_id and user_id == inst.gm_uid)
        is_member = bool(is_gm or user_id in inst.players)
        if not is_member:
            return web.json_response({"ok": False, "error": "未加入本局，无法生成图片"}, status=403)
        if purpose in {"scene", "map", "item"} and not is_gm:
            return web.json_response({"ok": False, "error": "仅 GM 可生成该类型图片"}, status=403)
        owner_type = "game"
        owner_id = game_image_owner_id(inst.game_key)
    elif request.get(ACCESS_PASSWORD_CONFIGURED_KEY, False) and not request.get("owner_authenticated", False):
        return web.json_response({"ok": False, "error": "仅管理员可以生成系统图片"}, status=403)
    try:
        result = await api.generate_generated_image(
            prompt=prompt,
            purpose=purpose,
            owner_type=owner_type,
            owner_id=owner_id,
            aspect_ratio=str(body.get("aspect_ratio") or ""),
            style=str(body.get("style") or ""),
            context=body.get("context") if isinstance(body.get("context"), dict) else {},
        )
    except ImageGenerationError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response(result)


async def api_generated_image_file(request: web.Request) -> web.StreamResponse:
    api = _get_api(request)
    game_key = str(request.match_info.get("game_key") or "").strip()
    if game_key:
        inst = api.get_game_instance(game_key)
        if inst is None:
            return web.json_response({"error": "游戏不存在"}, status=404)
        user_id = str(request.get("user_id", "") or "")
        if not user_id or (user_id != inst.gm_uid and user_id not in inst.players):
            return web.json_response({"error": "未加入本局，无法查看生成图片"}, status=403)
    path = api.generated_image_file(request.match_info["asset_id"])
    if path is None:
        return web.json_response({"error": "生成图片不存在"}, status=404)
    return web.FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})


async def api_game_generated_images(request: web.Request) -> web.Response:
    api = _get_api(request)
    game_key = request.match_info["game_key"]
    viewer = viewer_for(request, api.get_game_instance(game_key))
    try:
        images = api.list_game_generated_images(
            game_key,
            str(request.get("user_id", "") or ""),
            purpose=str(request.query.get("purpose") or "").strip().lower(),
            viewer_is_gm=viewer.is_gm,
        )
    except KeyError:
        return web.json_response({"error": "游戏不存在"}, status=404)
    except PermissionError:
        return web.json_response({"error": "未加入本局，无法查看生成历史"}, status=403)
    return web.json_response({"images": images})


async def api_generated_image_as_map_background(request: web.Request) -> web.Response:
    result = await _get_api(request).use_generated_image_as_map_background(
        request.match_info["game_key"],
        str(request.get("user_id", "") or ""),
        request.match_info["asset_id"],
    )
    return web.json_response(result, status=200 if result.get("ok") else 400)


async def api_generate_current_round_image(request: web.Request) -> web.Response:
    body = await request.json() if request.can_read_body else {}
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "生图请求必须是 JSON 对象"}, status=400)
    try:
        round_number = int(body.get("round") or 0)
    except (TypeError, ValueError):
        round_number = 0
    try:
        panel_count = int(body["panel_count"]) if "panel_count" in body else None
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "分镜格数必须是 1 到 6 的整数"}, status=400)
    if panel_count is not None and not 1 <= panel_count <= 6:
        return web.json_response({"ok": False, "error": "分镜格数必须在 1 到 6 之间"}, status=400)
    result = await _get_api(request).generate_current_round_image(
        str(request.match_info.get("game_key") or ""),
        str(request.get("user_id", "") or ""),
        str(body.get("prompt") or ""), round_number,
        body.get("panels"), bool(body.get("use_avatar_references", False)), panel_count,
    )
    return web.json_response(result, status=200 if result.get("ok") else 400)

async def api_storyboard_draft(request: web.Request) -> web.Response:
    result = _get_api(request).storyboard_draft(str(request.match_info["game_key"]), str(request.get("user_id", "") or ""), int(request.query.get("round") or 0))
    return web.json_response(result, status=200 if result.get("ok") else 400)

async def api_analyze_storyboard(request: web.Request) -> web.Response:
    body = await request.json() if request.can_read_body else {}
    requested_count = (body or {}).get("panel_count")
    try:
        requested_count = int(requested_count) if requested_count is not None else None
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "分镜格数必须是 1 到 6 的整数"}, status=400)
    if requested_count is not None and not 1 <= requested_count <= 6:
        return web.json_response({"ok": False, "error": "分镜格数必须在 1 到 6 之间"}, status=400)
    result = await _get_api(request).analyze_storyboard(str(request.match_info["game_key"]), str(request.get("user_id", "") or ""), int((body or {}).get("round") or 0), requested_count)
    return web.json_response(result, status=200 if result.get("ok") else 400)

async def api_preview_image_prompt(request: web.Request) -> web.Response:
    body = await request.json() if request.can_read_body else {}
    body = body if isinstance(body, dict) else {}
    result = _get_api(request).preview_image_prompt(str(request.match_info["game_key"]), str(request.get("user_id", "") or ""), str(body.get("prompt") or ""), body.get("panels"))
    return web.json_response(result, status=200 if result.get("ok") else 400)


def register_generated_images(app: web.Application) -> None:
    app.router.add_get("/api/image-generation", api_image_generation_status)
    app.router.add_post("/api/image-prompts/optimize", api_optimize_image_prompt)
    app.router.add_post("/api/generated-images", api_generate_image)
    app.router.add_get("/api/generated-images/{asset_id}", api_generated_image_file)
    app.router.add_get("/api/games/{game_key}/generated-images", api_game_generated_images)
    app.router.add_post("/api/games/{game_key}/generated-images", api_generate_image)
    app.router.add_post("/api/games/{game_key}/generated-images/current-round", api_generate_current_round_image)
    app.router.add_get("/api/games/{game_key}/generated-images/storyboard", api_storyboard_draft)
    app.router.add_post("/api/games/{game_key}/generated-images/storyboard/analyze", api_analyze_storyboard)
    app.router.add_post("/api/games/{game_key}/generated-images/prompt/preview", api_preview_image_prompt)
    app.router.add_get(
        "/api/games/{game_key}/generated-images/{asset_id}",
        api_generated_image_file,
    )
    app.router.add_post(
        "/api/games/{game_key}/generated-images/{asset_id}/map-background",
        api_generated_image_as_map_background,
    )
