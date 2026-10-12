"""Public, read-only access to the legal documents bundled with DiceFrame."""

from __future__ import annotations

from aiohttp import web

from src.webui.routes._common import _get_api
from src.webui.services.legal import LegalContentUnavailable


async def api_legal_document(request: web.Request) -> web.Response:
    try:
        payload = await _get_api(request).legal_document(
            request.match_info["document"],
            request.query.get("lang", "zh-CN"),
        )
    except KeyError:
        raise web.HTTPNotFound(text="legal document not found")
    except LegalContentUnavailable:
        raise web.HTTPServiceUnavailable(text="online legal document unavailable")
    except OSError:
        raise web.HTTPServiceUnavailable(text="legal document unavailable")
    return web.json_response(payload)


def register_legal(app: web.Application) -> None:
    app.router.add_get("/api/legal/{document}", api_legal_document)
