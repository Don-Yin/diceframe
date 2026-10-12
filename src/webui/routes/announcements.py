"""开发者公告路由:公开拉取,失败静默返回空。"""

from __future__ import annotations

from aiohttp import web

from src.webui.routes._common import _get_api


async def api_announcements(request: web.Request) -> web.Response:
    lang = request.query.get("lang") or "zh-CN"
    result = await _get_api(request).get_official_announcement(lang)
    return web.json_response(result, headers={"Cache-Control": "no-store"})


def register_announcements(app: web.Application) -> None:
    app.router.add_get("/api/announcements", api_announcements)
