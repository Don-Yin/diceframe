"""Agent adapters for authoritative WorldState facts.

World facts remain owned by ``src.engine.world_state``.  This module only
projects facts for the current viewer and changes visibility through the
existing ``apply_world_ops`` transaction boundary.
"""
from __future__ import annotations

import inspect
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from src.engine.world.read import project_visible_state, world_facts, world_revision
from src.engine.world_state import FACT_VISIBILITIES, apply_world_ops
from src.webui.services._common import is_game_gm
from src.webui.services.assistant_agent import AgentTool, _digest
from src.webui.services.assistant_agent_application import obj, string


@dataclass(frozen=True)
class WorldToolDependencies:
    get_game: Callable[[str], Any]
    viewer_for: Callable[[Any, str], Any]
    save_instance: Callable[[Any], Awaitable[None]]
    read_world_state: Callable[[Any, Any], dict] | None = None


async def _call(callback: Callable, *args: Any) -> Any:
    result = callback(*args)
    return await result if inspect.isawaitable(result) else result


def world_tools(deps: WorldToolDependencies) -> tuple[AgentTool, ...]:
    game_props = {"game_key": string(240, minimum=1)}
    run_props = {**game_props, "run_id": string(240, minimum=1)}

    def instance(args: dict, owner: str) -> tuple[Any, Any]:
        game = deps.get_game(args["game_key"])
        if game is None:
            raise ValueError("Game does not exist")
        viewer = deps.viewer_for(game, owner)
        if not getattr(viewer, "is_member", False):
            raise PermissionError("Game membership required")
        return game, viewer

    def gm_instance(args: dict, owner: str) -> tuple[Any, Any]:
        game, viewer = instance(args, owner)
        if not getattr(viewer, "is_gm", False) and not is_game_gm(game, owner, owner_authenticated=False):
            raise PermissionError("GM access required")
        return game, viewer

    def read(args: dict, owner: str) -> dict:
        game, viewer = instance(args, owner)
        if deps.read_world_state is not None:
            return deps.read_world_state(game, viewer)
        return project_visible_state(game, viewer_uid=getattr(viewer, "uid", ""),
                                     viewer_is_gm=bool(getattr(viewer, "is_gm", False)))

    def visibility_guard(args: dict, owner: str) -> str:
        game, _viewer = gm_instance(args, owner)
        facts = world_facts(game.world_state)
        fact = facts.get(args["fact_id"])
        return _digest({"run_id": game.run_id, "revision": world_revision(game.world_state),
                        "fact_id": args["fact_id"], "fact": deepcopy(fact)})

    async def set_visibility(args: dict, owner: str) -> dict:
        game, viewer = gm_instance(args, owner)
        if args["run_id"] != game.run_id:
            raise ValueError("Run changed; refresh first")
        if args["visibility"] not in FACT_VISIBILITIES:
            raise ValueError("Unsupported fact visibility")
        expected = args["expected_revision"]
        current = world_revision(game.world_state)
        if expected != current:
            raise ValueError("World state changed; refresh first")
        fact = world_facts(game.world_state).get(args["fact_id"])
        if not isinstance(fact, dict) or "value" not in fact:
            raise ValueError("Fact does not exist")
        async with game.authoritative_write() as entered, game._lock:
            if not entered or deps.get_game(args["game_key"]) is not game:
                raise ValueError("Run is read-only or stale")
            if game.run_id != args["run_id"]:
                raise ValueError("Run changed; refresh first")
            if world_revision(game.world_state) != expected:
                raise ValueError("World state changed; refresh first")
            fact = world_facts(game.world_state).get(args['fact_id'])
            if not isinstance(fact, dict) or 'value' not in fact:
                raise ValueError('Fact does not exist')
            before = deepcopy(game.world_state)
            try:
                summary = apply_world_ops(game, [{"op": "set_fact", "key": args["fact_id"],
                                                 "value": deepcopy(fact["value"]),
                                                 "visibility": args["visibility"]}])
                await deps.save_instance(game)
            except BaseException:
                game.world_state = before
                raise
        return {"ok": True, "run_id": game.run_id, "fact_id": args["fact_id"],
                "visibility": args["visibility"], "revision": summary["revision"]}

    return (
        AgentTool("get_world_state", "Read the current viewer-safe authoritative world projection",
                  obj(game_props, ("game_key",)), read, domain="games", effect="read"),
        AgentTool("set_world_fact_visibility", "GM change one existing world fact between public and GM-only visibility",
                  obj({**run_props, "fact_id": {"type": "string", "minLength": 1, "maxLength": 120,
                                               "pattern": r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}"},
                       "visibility": string(8, choices=FACT_VISIBILITIES),
                       "expected_revision": {"type": "integer", "minimum": 0}},
                      ("game_key", "run_id", "fact_id", "visibility", "expected_revision")),
                  set_visibility, mutation=True, guard=visibility_guard,
                  domain="games", effect="disclosure"),
    )
