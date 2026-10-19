"""Owner-only installed-module resource reads and reviewed native forks."""
from __future__ import annotations

import json
from aiohttp import web
from src.webui.routes._common import _get_api, require_content_owner


async def list_resources(request: web.Request) -> web.Response:
    if (denied := require_content_owner(request)) is not None:
        return denied
    try:
        result = _get_api(request).module_resources(request.match_info["module_id"])
    except (ValueError, TypeError, OSError, KeyError) as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response(result)


async def read_or_fork(request: web.Request) -> web.Response:
    if (denied := require_content_owner(request)) is not None:
        return denied
    try:
        raw = bytearray()
        async for chunk in request.content.iter_chunked(64 * 1024):
            if len(raw) + len(chunk) > 5 * 1024 * 1024:
                raise ValueError("module draft is too large")
            raw.extend(chunk)
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError("module resource body must be an object")
        api, module_id = _get_api(request), request.match_info["module_id"]
        action = request.match_info.get("action", "read")
        if action == "read":
            result = api.module_resource(module_id, body.get("selector"), str(body.get("language") or ""))
        elif action == "preview":
            result = api.preview_module_fork(module_id, body.get("selector"), str(body.get("language") or ""))
        elif action == "review":
            result = api.review_module_fork(module_id, body)
        else:
            result = api.commit_module_fork(module_id, body)
    except (ValueError, TypeError, OSError, KeyError) as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response(result)


async def asset(request: web.Request) -> web.StreamResponse:
    if (denied := require_content_owner(request)) is not None:
        return denied
    try:
        selector = request.query.get("selector", "")
        if len(selector) > 2048:
            raise ValueError("invalid module asset selector")
        path = _get_api(request).module_resource_asset(request.match_info["module_id"], json.loads(selector))
    except (ValueError, TypeError, OSError, KeyError) as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.FileResponse(path)


def register(app: web.Application) -> None:
    root = "/api/modules/{module_id}/resources"
    app.router.add_get(root, list_resources)
    app.router.add_post(root + "/read", read_or_fork)
    app.router.add_get(root + "/asset", asset)
    app.router.add_post(root + "/fork/{action:preview|review|commit}", read_or_fork)
