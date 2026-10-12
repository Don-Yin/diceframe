"""Content sync routes: ``/api/content/import/preview|commit``, ``/api/content/export``,
``/api/content/status`` and ``/api/content/list``.

Thin transport layer. It owns what only the request knows:

- owner-only access (master password or paired-device token);
- the paired-device identity rule: a request authenticated by a paired
  device may declare only that device's install id (bound at pairing, or on
  first use for devices paired earlier); the master-password owner may
  declare any device;
- the confirmation header every owner write requires (no simple
  cross-origin form POST can reach these routes);
- size limits: body and item count before any parsing; per-book entry
  limits on the adapter's parsed draft, before planning.

Everything else is delegated to the content sync use cases.
"""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from src.engine.world.contracts import CANONICAL_ID_PATTERN
from src.webui.access_control import PAIRED_DEVICE_ID_KEY
from src.content_modules.sync import ENTRY_TOO_LARGE, IMPORT_FAILED, TOO_MANY_ENTRIES
from src.webui.device_tokens import DEVICE_TOKENS_KEY, InstallIdInUse
from src.webui.routes._common import _get_api, _require_confirmed_request
from src.webui.routes.auth import ACCESS_PASSWORD_CONFIGURED_KEY
from src.webui.server_identity import SERVER_IDENTITY_UNAVAILABLE, server_instance_id

MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_ITEMS = 50
#: Status rows are tiny; a client checks its whole library in a few calls.
MAX_STATUS_ITEMS = 500
#: List rows are status rows plus a name: the same page size.
MAX_LIST_ITEMS = MAX_STATUS_ITEMS

BODY_TOO_LARGE = "BODY_TOO_LARGE"
TOO_MANY_ITEMS = "TOO_MANY_ITEMS"
OWNER_REQUIRED = "OWNER_REQUIRED"
SOURCE_NOT_THIS_DEVICE = "SOURCE_NOT_THIS_DEVICE"
INSTALL_ID_IN_USE = "INSTALL_ID_IN_USE"

_TOO_LARGE_CODES = frozenset({TOO_MANY_ENTRIES, ENTRY_TOO_LARGE})

_CONFLICT_CODES = frozenset({"PLAN_STALE", "CARD_IDENTITY_CONFLICT", "LOREBOOK_IDENTITY_CONFLICT"})


def _error(status: int, code: str, message: str, **extra: Any) -> web.Response:
    return web.json_response({"ok": False, "error_code": code, "error": message, **extra}, status=status)


def _owner_denied(request: web.Request) -> web.Response | None:
    """The library is the owner's: share, bot and plugin callers are refused.

    Without an access password there is no authentication boundary at all,
    exactly as for the rest of the owner API.
    """

    if request.get("bot_authenticated", False):
        return _error(403, OWNER_REQUIRED, "content sync is owner-only")
    if request.get(ACCESS_PASSWORD_CONFIGURED_KEY, True) and not request.get("owner_authenticated", False):
        return _error(403, OWNER_REQUIRED, "content sync is owner-only")
    return None


async def _read_json(request: web.Request) -> tuple[Any, web.Response | None]:
    if request.content_length is not None and request.content_length > MAX_BODY_BYTES:
        return None, _error(413, BODY_TOO_LARGE, f"request body exceeds {MAX_BODY_BYTES} bytes")
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await request.content.read(64 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            return None, _error(413, BODY_TOO_LARGE, f"request body exceeds {MAX_BODY_BYTES} bytes")
        chunks.append(chunk)
    try:
        body = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        # RecursionError: a pathologically nested body is malformed input,
        # not a server fault.
        return None, _error(400, "REQUEST_INVALID", "request must be JSON")
    if not isinstance(body, dict):
        return None, _error(400, "REQUEST_INVALID", "request must be an object")
    return body, None


def _limit_denied(body: dict[str, Any], *, max_items: int = MAX_ITEMS) -> web.Response | None:
    items = body.get("items")
    if isinstance(items, list) and len(items) > max_items:
        return _error(413, TOO_MANY_ITEMS, f"at most {max_items} items per request")
    return None


def _server_identity(request: web.Request) -> tuple[str, web.Response | None]:
    """Every sync answer is keyed by the server instance id; without it the
    client cannot map ids safely, so the request is refused up front."""

    instance_id = server_instance_id(request.app)
    if not instance_id:
        return "", _error(
            503, SERVER_IDENTITY_UNAVAILABLE,
            "the server's instance id is unavailable; ask the owner to check the server's data directory",
        )
    return instance_id, None


def _device_denied(request: web.Request, body: dict[str, Any]) -> web.Response | None:
    """A paired device may declare only its own install id."""

    device_id = str(request.get(PAIRED_DEVICE_ID_KEY, "") or "")
    if not device_id:
        return None  # master-password owner (or no password): any device
    source = body.get("source")
    declared = source.get("id") if isinstance(source, dict) else None
    if not isinstance(declared, str) or not CANONICAL_ID_PATTERN.fullmatch(declared):
        return None  # malformed source: the use case rejects it
    devices = request.app.get(DEVICE_TOKENS_KEY)
    if devices is None:
        return _error(403, SOURCE_NOT_THIS_DEVICE, "this device may only push its own install id")
    try:
        bound = devices.bind_install_id(device_id, declared)
    except InstallIdInUse:
        return _error(
            403, INSTALL_ID_IN_USE,
            "another paired device is bound to this install id; revoke it or clear its binding",
        )
    if bound != declared:
        return _error(403, SOURCE_NOT_THIS_DEVICE, "this device may only push its own install id")
    return None


def _respond(result: dict[str, Any], *, instance_id: str = "") -> web.Response:
    if instance_id:
        result = {**result, "server_instance_id": instance_id}
    if result.get("ok"):
        return web.json_response(result)
    code = str(result.get("error_code") or "")
    failed_items = [row for row in result.get("items") or [] if row.get("status") == "error"]
    if code in _TOO_LARGE_CODES:
        return web.json_response(result, status=413)
    if any(row.get("error_code") == IMPORT_FAILED for row in failed_items):
        return web.json_response(result, status=500)
    if code in _CONFLICT_CODES or any(row.get("error_code") in _CONFLICT_CODES for row in failed_items):
        return web.json_response(result, status=409)
    if code == "NOT_FOUND":
        return web.json_response(result, status=404)
    return web.json_response(result, status=400)


async def _import_request(request: web.Request) -> tuple[dict[str, Any] | None, web.Response | None]:
    # Preview can bind a device's install id, so it is a write too.
    if denied := _require_confirmed_request(request):
        return None, denied
    if denied := _owner_denied(request):
        return None, denied
    body, denied = await _read_json(request)
    if denied is not None:
        return None, denied
    if denied := _limit_denied(body):
        return None, denied
    if denied := _device_denied(request, body):
        return None, denied
    return body, None


async def api_content_import_preview(request: web.Request) -> web.Response:
    body, denied = await _import_request(request)
    if denied is not None or body is None:
        return denied or _error(400, "REQUEST_INVALID", "request must be an object")
    instance_id, denied = _server_identity(request)
    if denied is not None:
        return denied
    return _respond(_get_api(request).preview_content_import(
        body, pushed_by_device=str(request.get(PAIRED_DEVICE_ID_KEY, "") or ""),
    ), instance_id=instance_id)


async def api_content_import_commit(request: web.Request) -> web.Response:
    body, denied = await _import_request(request)
    if denied is not None or body is None:
        return denied or _error(400, "REQUEST_INVALID", "request must be an object")
    instance_id, denied = _server_identity(request)
    if denied is not None:
        return denied
    return _respond(_get_api(request).commit_content_import(
        body, pushed_by_device=str(request.get(PAIRED_DEVICE_ID_KEY, "") or ""),
    ), instance_id=instance_id)


async def _read_request(request: web.Request, *, max_items: int) -> tuple[dict[str, Any] | None, web.Response | None]:
    if denied := _require_confirmed_request(request):
        return None, denied
    if denied := _owner_denied(request):
        return None, denied
    body, denied = await _read_json(request)
    if denied is not None or body is None:
        return None, denied or _error(400, "REQUEST_INVALID", "request must be an object")
    if denied := _limit_denied(body, max_items=max_items):
        return None, denied
    return body, None


async def api_content_export(request: web.Request) -> web.Response:
    body, denied = await _read_request(request, max_items=MAX_ITEMS)
    if denied is not None or body is None:
        return denied or _error(400, "REQUEST_INVALID", "request must be an object")
    instance_id, denied = _server_identity(request)
    if denied is not None:
        return denied
    return _respond(_get_api(request).export_content(body, server_instance_id=instance_id), instance_id=instance_id)


async def api_content_status(request: web.Request) -> web.Response:
    """State token and provenance per object: detect server changes cheaply."""

    body, denied = await _read_request(request, max_items=MAX_STATUS_ITEMS)
    if denied is not None or body is None:
        return denied or _error(400, "REQUEST_INVALID", "request must be an object")
    instance_id, denied = _server_identity(request)
    if denied is not None:
        return denied
    return _respond(_get_api(request).content_status(body), instance_id=instance_id)


async def api_content_list(request: web.Request) -> web.Response:
    """Every card or Book in the owner's library, one page at a time.

    Read-only: unlike preview it declares no source, so it never binds a
    paired device's install id.
    """

    body, denied = await _read_request(request, max_items=MAX_LIST_ITEMS)
    if denied is not None or body is None:
        return denied or _error(400, "REQUEST_INVALID", "request must be an object")
    instance_id, denied = _server_identity(request)
    if denied is not None:
        return denied
    return _respond(_get_api(request).list_content(body, max_limit=MAX_LIST_ITEMS), instance_id=instance_id)


def register_content(app: web.Application) -> None:
    app.router.add_post("/api/content/import/preview", api_content_import_preview)
    app.router.add_post("/api/content/import/commit", api_content_import_commit)
    app.router.add_post("/api/content/export", api_content_export)
    app.router.add_post("/api/content/status", api_content_status)
    app.router.add_post("/api/content/list", api_content_list)
