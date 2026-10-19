from copy import deepcopy

import pytest

from src.engine.game_instance import GameInstance
from src.engine.participant_view import Viewer
from src.engine.world.read import project_visible_state, world_facts, world_revision
from src.engine.world_state import apply_world_ops, fresh_world_state
from src.webui.services.assistant_agent import validate_arguments
from src.webui.services.assistant_world_tools import WorldToolDependencies, world_tools


def fixture_world():
    game = GameInstance(game_key=("web", "world-agent", "bot"), gm_uid="gm")
    game.world_state = fresh_world_state()
    apply_world_ops(game, [{"op": "set_fact", "key": "secret:door.open", "value": True, "visibility": "gm"}])
    viewers = {
        "gm": Viewer("gm", "gm"),
        "alice": Viewer("seat", "alice"),
    }
    game.put_player("alice", {"character_name": "Alice", "character_sheet": {}})
    saved = []
    async def save(instance):
        saved.append(deepcopy(instance.world_state))
    deps = WorldToolDependencies(
        get_game=lambda key: game if key == "game" else None,
        viewer_for=lambda instance, owner: viewers[owner],
        save_instance=save,
    )
    tools = {tool.name: tool for tool in world_tools(deps)}
    return game, tools, saved


def read_args(game):
    return {"game_key": "game"}


@pytest.mark.asyncio
async def test_world_fact_visibility_preserves_value_and_player_projection(tmp_path):
    game, tools, saved = fixture_world()
    read = tools["get_world_state"]
    write = tools["set_world_fact_visibility"]
    before = world_facts(game.world_state)["secret:door.open"]["value"]
    assert "secret:door.open" not in read.handler(read_args(game), "alice")["facts"]
    assert "secret:door.open" in read.handler(read_args(game), "gm")["facts"]

    args = {"game_key": "game", "run_id": game.run_id, "fact_id": "secret:door.open",
            "visibility": "public", "expected_revision": world_revision(game.world_state)}
    result = await write.handler(args, "gm")
    assert result["ok"]
    assert world_facts(game.world_state)["secret:door.open"]["value"] is before
    assert "secret:door.open" in read.handler(read_args(game), "alice")["facts"]
    assert saved

    args["expected_revision"] = world_revision(game.world_state)
    args["visibility"] = "gm"
    await write.handler(args, "gm")
    assert "secret:door.open" not in read.handler(read_args(game), "alice")["facts"]


def test_world_fact_visibility_requires_gm_and_canonical_key():
    game, tools, _saved = fixture_world()
    write = tools["set_world_fact_visibility"]
    args = {"game_key": "game", "run_id": game.run_id, "fact_id": "secret:door.open",
            "visibility": "public", "expected_revision": world_revision(game.world_state)}
    with pytest.raises(PermissionError):
        write.guard(args, "alice")
    with pytest.raises(ValueError):
        validate_arguments({**args, "fact_id": "display name"}, write.schema)


@pytest.mark.asyncio
async def test_world_fact_visibility_rejects_stale_guard_and_run():
    game, tools, _saved = fixture_world()
    write = tools["set_world_fact_visibility"]
    args = {"game_key": "game", "run_id": game.run_id, "fact_id": "secret:door.open",
            "visibility": "public", "expected_revision": world_revision(game.world_state)}
    guard = write.guard(args, "gm")
    apply_world_ops(game, [{"op": "set_fact", "key": "other.fact", "value": 1}])
    assert write.guard(args, "gm") != guard
    with pytest.raises(ValueError, match="changed"):
        await write.handler(args, "gm")
    with pytest.raises(ValueError, match="Run changed"):
        await write.handler({**args, "run_id": "other"}, "gm")


@pytest.mark.asyncio
async def test_world_fact_visibility_save_failure_rolls_back():
    game, _tools, _saved = fixture_world()
    async def fail(_instance):
        raise RuntimeError("disk full")
    deps = WorldToolDependencies(
        get_game=lambda key: game,
        viewer_for=lambda instance, owner: Viewer("gm", "gm"),
        save_instance=fail,
    )
    write = {tool.name: tool for tool in world_tools(deps)}["set_world_fact_visibility"]
    before = deepcopy(game.world_state)
    args = {"game_key": "game", "run_id": game.run_id, "fact_id": "secret:door.open",
            "visibility": "public", "expected_revision": world_revision(game.world_state)}
    with pytest.raises(RuntimeError, match="disk full"):
        await write.handler(args, "gm")
    assert game.world_state == before
