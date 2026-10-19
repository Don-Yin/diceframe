"""Owner-managed script preview, review and publish HTTP entry points."""

from __future__ import annotations

import json
import asyncio
from contextlib import suppress

from aiohttp import web

from src.adventures.script_import import MAX_SCRIPT_BYTES
from src.adventures.external_import import source_limit
from src.webui.routes._common import _get_api
from src.webui.routes.auth import ACCESS_PASSWORD_CONFIGURED_KEY


def _owner_guard(request: web.Request) -> web.Response | None:
    if request.get('owner_authenticated', False):
        return None
    if (request.get(ACCESS_PASSWORD_CONFIGURED_KEY, False) or request.query.get('user')
            or request.headers.get('X-Bot-Token')):
        return web.json_response({'ok': False, 'error_code': 'OWNER_REQUIRED'}, status=403)
    return None


async def preview(request: web.Request) -> web.Response:
    if (denied := _owner_guard(request)) is not None:
        return denied
    try:
        if request.content_type != 'multipart/form-data':
            raise ValueError('script preview requires multipart/form-data')
        reader = await request.multipart()
        payload = bytearray()
        filename = ''
        file_count = 0
        language = request.query.get('language', '')
        async for part in reader:
            if part.name != 'file':
                raise ValueError('script preview accepts one file field')
            file_count += 1
            if file_count > 1 or not part.filename:
                raise ValueError('script preview accepts exactly one file')
            filename = str(part.filename or '')
            while chunk := await part.read_chunk():
                if len(payload) + len(chunk) > source_limit(filename):
                    raise ValueError('script is too large')
                payload.extend(chunk)
        api = _get_api(request)
        draft = await asyncio.to_thread(api.prepare_adventure_script_source, bytes(payload), filename, language)
        result = api.review_adventure_script(draft)
    except ValueError as exc:
        return web.json_response({'ok': False, 'error': str(exc)}, status=400)
    return web.json_response(result)


async def review(request: web.Request) -> web.Response:
    return await _review_or_commit(request, publish=False)


async def commit(request: web.Request) -> web.Response:
    return await _review_or_commit(request, publish=True)


async def organize_ai(request: web.Request) -> web.StreamResponse:
    """Request-scoped generation: disconnecting cancels the active provider call."""
    if (denied := _owner_guard(request)) is not None:
        return denied
    if not request.get('owner_authenticated', False) and request.query.get('share'):
        return web.json_response({'ok': False, 'error_code': 'OWNER_REQUIRED'}, status=403)
    try:
        raw = bytearray()
        async for chunk in request.content.iter_chunked(64 * 1024):
            if len(raw) + len(chunk) > MAX_SCRIPT_BYTES * 4:
                raise ValueError('AI draft is too large')
            raw.extend(chunk)
        body = json.loads(raw)
        if not isinstance(body, dict) or body.get('token_consent') is not True:
            raise ValueError('Confirm token consumption before starting AI organization')
        if not isinstance(body.get('draft'), dict) or not isinstance(body.get('instructions', ''), str):
            raise ValueError('AI organization requires a draft and text instructions')
        if len(body.get('instructions', '')) > 2000:
            raise ValueError('AI instructions exceed 2000 characters')
    except (ValueError, TypeError) as exc:
        return web.json_response({'ok': False, 'error': str(exc)}, status=400)
    response = web.StreamResponse(headers={'Content-Type': 'application/x-ndjson', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
    await response.prepare(request)
    progress: asyncio.Queue = asyncio.Queue()

    async def emit(value):
        await progress.put({'type': 'progress', **value})

    async def write(value):
        await response.write((json.dumps(value, ensure_ascii=False) + '\n').encode())

    task = asyncio.create_task(_get_api(request).organize_adventure_script(
        body['draft'], body.get('instructions', ''), request.query.get('language', ''), emit,
    ))
    deadline = asyncio.get_running_loop().time() + 600
    try:
        while not task.done() or not progress.empty():
            if request.transport is None or request.transport.is_closing():
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError('AI organization timed out. Try importing a smaller section.')
            try:
                value = await asyncio.wait_for(progress.get(), .25)
                await write(value)
            except asyncio.TimeoutError:
                await write({'type': 'heartbeat'})
        if task.done() and request.transport is not None and not request.transport.is_closing():
            await write({'type': 'result', 'preview': task.result()})
    except (ConnectionResetError, BrokenPipeError):
        pass
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if request.transport is not None and not request.transport.is_closing():
            with suppress(ConnectionResetError, BrokenPipeError):
                await write({'type': 'error', 'error': str(exc)})
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task
    return response


async def _review_or_commit(request: web.Request, *, publish: bool) -> web.Response:
    if (denied := _owner_guard(request)) is not None:
        return denied
    try:
        raw = bytearray()
        async for chunk in request.content.iter_chunked(64 * 1024):
            if len(raw) + len(chunk) > MAX_SCRIPT_BYTES * 4:
                raise ValueError('script draft is too large')
            raw.extend(chunk)
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError('script draft must be an object')
        api = _get_api(request)
        result = api.commit_adventure_script(body) if publish else api.review_adventure_script(body)
    except (ValueError, TypeError) as exc:
        return web.json_response({'ok': False, 'error': str(exc)}, status=400)
    return web.json_response(result, status=201 if publish else 200)


def register(app: web.Application) -> None:
    app.router.add_post('/api/adventures/script/preview', preview)
    app.router.add_post('/api/adventures/script/review', review)
    app.router.add_post('/api/adventures/script/commit', commit)
    app.router.add_post('/api/adventures/script/ai', organize_ai)
