"""Owner Agent tools over the GM game-content binding service."""
from src.webui.services.assistant_agent import AgentTool
from src.webui.services.assistant_agent_application import obj, string


def game_lorebook_tools(service):
    game = {'game_key': string(500, minimum=1)}
    selection = {**game, 'book_ids': {'type': 'array', 'maxItems': 16, 'items': string(200, minimum=1)}}
    async def apply(args, owner):
        guard = service.guard(args['game_key'], args['book_ids'], owner, owner_authenticated=True)
        return await service.apply(args['game_key'], args['book_ids'], owner,
                                   owner_authenticated=True, expected_guard=guard)
    return (
        AgentTool('read_game_lorebooks', 'Read this game’s actual source books and protected character sources', obj(game, ('game_key',)),
                  lambda args, owner: service.selection(args['game_key'], owner, owner_authenticated=True)),
        AgentTool('set_game_lorebooks', 'Set up to 16 editable lorebook sources for this game, leaving other games and character sources intact',
            obj(selection, ('game_key', 'book_ids')), apply, mutation=True,
            guard=lambda args, owner: service.guard(args['game_key'], args['book_ids'], owner, owner_authenticated=True),
            preview=lambda args, owner: service.preview(args['game_key'], args['book_ids'], owner, owner_authenticated=True)),
    )
