"""Adventure catalogue and owner-managed package routes."""

from __future__ import annotations

from aiohttp import web

from src.webui.services.adventures import MAX_ADVENTURE_PACKAGE_BYTES


def _get_api(request: web.Request):
    return request.app["api"]


async def api_adventures(request: web.Request) -> web.Response:
    result = _get_api(request).list_adventures(
        rule_id=request.query.get("rule_id", ""),
        world_id=request.query.get("world_id", ""),
        language=request.query.get("language", ""),
    )
    return web.json_response(result)


def _status_for_error(exc: Exception) -> int:
    if isinstance(exc, PermissionError):
        return 409
    return 400


async def api_adventure_detail(request: web.Request) -> web.Response:
    try:
        result = _get_api(request).adventure_detail(
            request.match_info["adventure_id"], request.query.get("language", ""),
        )
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=404)
    return web.json_response(result)


async def api_adventure_copy(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("request body must be an object")
        result = _get_api(request).copy_adventure(
            request.match_info["adventure_id"], body,
            str(body.get("language") or ""),
        )
    except (ValueError, PermissionError) as exc:
        return web.json_response(
            {"ok": False, "error": str(exc)}, status=_status_for_error(exc),
        )
    return web.json_response(result, status=201)


async def api_adventure_create(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("request body must be an object")
        result = _get_api(request).create_adventure(
            body, str(body.get("language") or ""),
        )
    except (ValueError, PermissionError) as exc:
        return web.json_response(
            {"ok": False, "error": str(exc)}, status=_status_for_error(exc),
        )
    return web.json_response(result, status=201)


async def api_adventure_update(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("request body must be an object")
        result = _get_api(request).update_adventure(
            request.match_info["adventure_id"], body,
            str(body.get("language") or ""),
        )
    except (ValueError, PermissionError) as exc:
        return web.json_response(
            {"ok": False, "error": str(exc)}, status=_status_for_error(exc),
        )
    return web.json_response(result)


async def api_adventure_delete(request: web.Request) -> web.Response:
    try:
        result = _get_api(request).delete_adventure(request.match_info["adventure_id"])
    except (ValueError, PermissionError) as exc:
        return web.json_response(
            {"ok": False, "error": str(exc)}, status=_status_for_error(exc),
        )
    return web.json_response(result)


async def api_adventure_export(request: web.Request) -> web.Response:
    try:
        filename, payload = _get_api(request).export_adventure(
            request.match_info["adventure_id"],
        )
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=404)
    return web.Response(
        body=payload,
        content_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def api_adventure_import(request: web.Request) -> web.Response:
    if request.content_type != "multipart/form-data":
        return web.json_response(
            {"ok": False, "error": "adventure import requires multipart/form-data"},
            status=400,
        )
    payload = bytearray()
    directory_id = ""
    try:
        reader = await request.multipart()
        async for part in reader:
            if part.name == "directory_id":
                directory_id = (await part.text()).strip()
                continue
            if part.name not in {"file", "adventure"}:
                continue
            while True:
                chunk = await part.read_chunk()
                if not chunk:
                    break
                if len(payload) + len(chunk) > MAX_ADVENTURE_PACKAGE_BYTES:
                    raise ValueError("adventure package is too large")
                payload.extend(chunk)
        result = _get_api(request).import_adventure(bytes(payload), directory_id)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response(result, status=201)


def register_adventures(app: web.Application) -> None:
    app.router.add_get("/api/adventures", api_adventures)
    app.router.add_post("/api/adventures", api_adventure_create)
    app.router.add_post("/api/adventures/import", api_adventure_import)
    app.router.add_get("/api/adventures/{adventure_id}/export", api_adventure_export)
    app.router.add_post("/api/adventures/{adventure_id}/copy", api_adventure_copy)
    app.router.add_get("/api/adventures/{adventure_id}", api_adventure_detail)
    app.router.add_put("/api/adventures/{adventure_id}", api_adventure_update)
    app.router.add_delete("/api/adventures/{adventure_id}", api_adventure_delete)
