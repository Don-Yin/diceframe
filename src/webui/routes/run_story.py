"""Member-safe story reads and GM-only run planning/finalization."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import json

from aiohttp import web

from src.webui.viewer import viewer_for


def _context(request):
    api = request.app['api']
    key = request.match_info['game_key']
    inst = api.get_game_instance(key)
    if inst is None:
        raise web.HTTPNotFound()
    viewer = viewer_for(request, inst)
    if not viewer.is_member:
        raise web.HTTPForbidden()
    return api.run_story, key, viewer


async def get(request: web.Request) -> web.Response:
    service, key, viewer = _context(request)
    result = service.get(key, viewer)
    return web.json_response(result, status=200 if result.get('ok') else 409)


async def mutate(request: web.Request) -> web.Response:
    service, key, viewer = _context(request)
    if not viewer.is_gm:
        raise web.HTTPForbidden()
    try:
        result = await service.mutate(key, viewer, request.match_info['action'], await request.json())
    except ValueError as exc:
        return web.json_response({'ok': False, 'error_code': 'UNSUPPORTED_RUN_STATE', 'error': str(exc)}, status=409)
    pool = request.app.get('connection_pool')
    if pool and result.get('ok'):
        # Invalidate role-filtered views; never broadcast GM plans/materials.
        await pool.broadcast(key, {'type': 'run_story_changed'})
    return web.json_response(result, status=200 if result.get('ok') else 409)


async def export(request: web.Request) -> web.Response:
    service, key, viewer = _context(request)
    try:
        result = service.export(key, viewer, character=request.query.get('kind') == 'character',
                                target_uid=request.query.get('uid', ''))
    except PermissionError as exc:
        return web.json_response({'ok': False, 'error': str(exc)}, status=403)
    except ValueError as exc:
        return web.json_response({'ok': False, 'error_code': 'UNSUPPORTED_RUN_STATE', 'error': str(exc)}, status=409)
    return web.Response(body=json.dumps(result, ensure_ascii=False, indent=2).encode(),
                        content_type='application/json', headers={
                            'Content-Disposition': 'attachment; filename="diceframe-run.json"', 'Cache-Control': 'no-store'})


async def adventure_draft(request: web.Request) -> web.Response:
    service, key, viewer = _context(request)
    if not viewer.is_gm:
        raise web.HTTPForbidden()
    try:
        result = await service.prepare_adventure(key, viewer, await request.json())
    except ValueError as exc:
        return web.json_response({'ok': False, 'error': str(exc)}, status=409)
    return web.json_response(result, headers={'Cache-Control': 'no-store'})


async def generate(request: web.Request) -> web.StreamResponse:
    service, key, viewer = _context(request)
    if not viewer.is_gm:
        raise web.HTTPForbidden()
    body = await request.json()
    if not isinstance(body, dict) or body.get('token_consent') is not True:
        return web.json_response({'ok': False, 'error': 'Confirm token consumption first'}, status=400)
    response = web.StreamResponse(headers={'Content-Type': 'application/x-ndjson', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
    await response.prepare(request)
    progress: asyncio.Queue = asyncio.Queue()

    async def emit(value):
        await progress.put({'type': 'progress', **value})

    async def write(value):
        await response.write((json.dumps(value, ensure_ascii=False) + '\n').encode())

    task = asyncio.create_task(service.generate(key, viewer, request.match_info['kind'], body, emit))
    deadline = asyncio.get_running_loop().time() + 600
    try:
        while not task.done() or not progress.empty():
            if request.transport is None or request.transport.is_closing():
                break
            if asyncio.get_running_loop().time() > deadline:
                raise TimeoutError('AI generation timed out; preparation is retained and can be retried or cancelled')
            try:
                await write(await asyncio.wait_for(progress.get(), .25))
            except asyncio.TimeoutError:
                await write({'type': 'heartbeat'})
        if task.done() and request.transport is not None and not request.transport.is_closing():
            await write({'type': 'result', **task.result()})
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


def register(app: web.Application) -> None:
    prefix = '/api/games/{game_key}/run-story'
    app.router.add_get(prefix, get)
    app.router.add_get(prefix + '/export', export)
    app.router.add_post(prefix + '/adventure-draft', adventure_draft)
    app.router.add_post(prefix + '/generate/{kind:plan|finale}', generate)
    app.router.add_post(prefix + '/{action:plan|advance|intermission|prepare|materials|cancel|commit|carry}', mutate)
