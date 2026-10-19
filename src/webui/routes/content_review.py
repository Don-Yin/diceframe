"""Owner-only bounded prose review HTTP adapter."""
from __future__ import annotations

import json
from aiohttp import web
from src.webui.routes._common import _get_api
from src.webui.routes.auth import ACCESS_PASSWORD_CONFIGURED_KEY
from src.webui.services.content_text_review import MAX_TEXT_BYTES


async def handle(request: web.Request) -> web.Response:
    if not request.get("owner_authenticated") and (request.get(ACCESS_PASSWORD_CONFIGURED_KEY)
            or request.query.get("user") or request.headers.get("X-Bot-Token")):
        return web.json_response({"ok": False, "error_code": "OWNER_REQUIRED"}, status=403)
    try:
        raw = bytearray()
        async for chunk in request.content.iter_chunked(64 * 1024):
            if len(raw) + len(chunk) > MAX_TEXT_BYTES * 4:
                raise ValueError("content draft is too large")
            raw.extend(chunk)
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError("content draft must be an object")
        api = _get_api(request)
        action = request.match_info["action"]
        if action == "preview":
            result = api.preview_content_text(body.get("text"), str(body.get("filename") or "notes.txt"), str(body.get("language") or ""))
        elif action == "review":
            result = api.review_content_text(body)
        else:
            result = api.commit_content_text(body)
    except (ValueError, TypeError) as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response(result)


def register(app: web.Application) -> None:
    app.router.add_post("/api/content-review/{action:preview|review|commit}", handle)
