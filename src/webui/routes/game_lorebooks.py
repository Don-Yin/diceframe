"""Owner-only catalogue for deterministic game-source selection."""
from aiohttp import web
from src.webui.routes._common import _get_api


async def api_game_lorebooks(request):
    if not request.get('owner_authenticated') or not request.get('user_id'):
        return web.json_response({'ok': False, 'error': '只有登录房主可以管理本局资料册'}, status=403)
    try:
        return web.json_response(_get_api(request).game_lorebook_selection(request['user_id'], request.match_info['game_key']))
    except PermissionError as exc:
        return web.json_response({'ok': False, 'error': str(exc)}, status=403)
    except ValueError as exc:
        return web.json_response({'ok': False, 'error': str(exc)}, status=400)
