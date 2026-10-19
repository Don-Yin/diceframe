from dataclasses import dataclass
from collections.abc import Callable, Awaitable
from copy import deepcopy
from uuid import uuid4
from typing import Any

from src.engine.game_instance import GameInstance, GameState
from src.engine.modules import profile_progression, profile_run
from src.engine.module_state import get_module_state
from src.engine.player_control import get_control, submission_block
from src.engine.action_gate import (
    GateRequest,
    evaluate,
    STRUCTURED_INTENT_POLICY,
    check_ai_control_current,
)
from src.engine.language import normalize_language
from src.game_profiles import registry
from src.game_profiles.projection import unconfigured_binding


@dataclass(frozen=True)
class ProfileDependencies:
    get: Callable[[tuple], Any]
    register: Callable[[Any], None]
    save: Callable[[Any], Awaitable[None]]
    roll: Callable[[], int]


class ProfileService:
    def __init__(self, deps):
        self.deps = deps

    async def create(self, body):
        if not isinstance(body, dict) or set(body) - {
            "profile_id",
            "names",
            "language",
            "name",
        }:
            raise ValueError("unexpected profile creation fields")
        profile = registry.resolve(body.get("profile_id"))
        names = body.get("names")
        if (
            not isinstance(names, list)
            or not 1 <= len(names) <= 4
            or any(
                not isinstance(name, str) or not name.strip() or len(name) > 40
                for name in names
            )
        ):
            raise ValueError("choose 1–4 player names, each 1–40 characters")
        title = body.get("name") or profile.title
        if not isinstance(title, str) or len(title) > 120:
            raise ValueError("invalid game name")
        identity = uuid4().hex
        instance = GameInstance(
            game_key=("web", f"profile_{identity}", "web_bot"),
            world_name=title,
            group_name=title,
            state=GameState.ACTIVE_ACTION,
            language=normalize_language(body.get("language")),
        )
        for index, name in enumerate(names):
            instance.put_player(
                f"{identity}_{index}",
                {
                    "character_name": name.strip(),
                    "character_sheet": {"character_name": name.strip()},
                },
            )
        instance.gm_uid = next(iter(instance.players))
        profile_run.install(
            instance,
            {
                "schema_version": 1,
                "profile_id": profile.id,
                "profile_version": profile.version,
                **profile.runtime.initial(instance.players),
            },
        )
        profile_progression.install(
            instance, profile_progression.initial(profile.mode, profile.phases)
        )
        self._state(instance)
        await self.deps.save(instance)
        self.deps.register(instance)
        return {
            "ok": True,
            "game_key": "|".join(instance.game_key),
            "view": self.view(instance, instance.gm_uid, True),
        }

    def _state(self, instance):
        if not isinstance(instance.modules.get("profile_run"), dict) or not isinstance(
            instance.modules.get("profile_progression"), dict
        ):
            raise ValueError("profile state is missing or malformed")
        state = get_module_state(instance, "profile_run")
        if (
            type(state.get("schema_version")) is not int
            or state.get("schema_version") != 1
        ):
            raise ValueError("unsupported profile state schema")
        profile = registry.resolve(
            state.get("profile_id"), state.get("profile_version")
        )
        time = get_module_state(instance, "profile_progression")
        profile_progression.validate(time, profile.mode, profile.phases)
        profile.runtime.validate(state)
        if set(state["actors"]) != set(instance.players):
            raise ValueError(
                "profile roster changed; this demo requires its original seats"
            )
        if not set(time["acted"]) <= set(state["actors"]) or any(
            count > profile.actions_per_stage for count in time["acted"].values()
        ):
            raise ValueError("invalid profile action counters")
        return profile, state, time

    def view(self, instance, uid, gm, actor_uid=""):
        if instance is None:
            raise ValueError("game does not exist")
        slot = instance.modules.get("profile_run")
        if slot is not None and not isinstance(slot, dict):
            raise ValueError("invalid profile state slot")
        if unconfigured_binding(slot):
            if not profile_progression.accepts_narrative(instance):
                raise ValueError("profile progression has no valid profile binding")
            return {"ok": True, "profile": None}
        if not gm and uid not in instance.players:
            raise ValueError("player is not in this game")
        profile, state, time = self._state(instance)
        selected = actor_uid if gm and actor_uid else uid
        if selected not in state["actors"]:
            selected = instance.gm_uid if gm else uid
        control = get_control(instance, selected)
        moves = (
            profile.runtime.legal(state, time, selected)
            if time["acted"].get(selected, 0) < profile.actions_per_stage
            else []
        )
        return {
            "ok": True,
            "profile": {
                "id": profile.id,
                "version": profile.version,
                "title": profile.title,
                "ui_sections": list(profile.ui_sections),
            },
            "game_name": instance.world_name,
            "gm_uid": instance.gm_uid,
            "revision": state["revision"],
            "run_id": instance.run_id,
            "is_gm": gm,
            "status": state["status"],
            "actor_uid": selected,
            "control_revision": control["revision"],
            "control_mode": control["mode"],
            "progression": deepcopy(time),
            "resources": deepcopy(state["resources"]),
            "clocks": deepcopy(state["clocks"]),
            "weather": state.get("weather"),
            "actors": [
                {
                    "uid": key,
                    "name": instance.players[key]["character_name"],
                    "control": get_control(instance, key),
                    **deepcopy(value),
                }
                for key, value in state["actors"].items()
            ],
            "actions": [{"id": move} for move in moves],
            "can_advance": gm and state["status"] == "active",
            "history": deepcopy(state["history"]),
        }

    async def act(self, instance, uid, gm, body):
        if not isinstance(body, dict) or set(body) - {
            "type",
            "move_id",
            "actor_uid",
            "expected_revision",
            "expected_control_revision",
            "expected_run_id",
        }:
            raise ValueError("unexpected profile action fields")
        async with instance.authoritative_write() as entered, instance._lock:
            if not entered or self.deps.get(instance.game_key) is not instance:
                raise ValueError("game run changed")
            if body.get("expected_run_id") != instance.run_id:
                raise ValueError("game run changed")
            error = evaluate(
                instance,
                GateRequest(uid, "intent", requester_is_gm=gm),
                STRUCTURED_INTENT_POLICY,
            )
            if error:
                raise ValueError(error)
            profile, state, time = self._state(instance)
            if (
                type(body.get("expected_revision")) is not int
                or body["expected_revision"] != state["revision"]
            ):
                raise ValueError("profile action is stale")
            if state["status"] != "active":
                raise ValueError("profile game has ended")
            kind = body.get("type")
            actor = body.get("actor_uid", uid)
            if kind == "advance":
                if not gm:
                    raise ValueError("GM_ONLY")
                if set(body) - {"type", "expected_revision", "expected_run_id"}:
                    raise ValueError("unexpected stage action fields")
            elif kind in ("move", "auto"):
                if actor not in instance.players or not gm and actor != uid:
                    raise ValueError("actor ownership rejected")
                control = get_control(instance, actor)
                if (
                    type(body.get("expected_control_revision")) is not int
                    or body["expected_control_revision"] != control["revision"]
                ):
                    raise ValueError("control changed")
                if kind == "auto":
                    if not gm:
                        raise ValueError("GM_ONLY")
                    error = check_ai_control_current(
                        instance,
                        GateRequest(
                            actor,
                            "ai_seat",
                            expected_control_revision=control["revision"],
                        ),
                    )
                else:
                    error = submission_block(instance, actor)
                if error:
                    raise ValueError(error)
                legal = (
                    profile.runtime.legal(state, time, actor)
                    if time["acted"].get(actor, 0) < profile.actions_per_stage
                    else []
                )
                move = legal[0] if kind == "auto" and legal else body.get("move_id")
                if move not in legal:
                    raise ValueError("move is not legal in this stage")
            else:
                raise ValueError("unsupported profile action")
            next_state, next_time = deepcopy(state), deepcopy(time)
            roll = self.deps.roll()
            if type(roll) is not int or not 1 <= roll <= 6:
                raise ValueError("invalid authoritative die")
            if kind == "advance":
                result = profile.runtime.advance(next_state, next_time, roll)
                if next_state["status"] == "active":
                    profile_progression.advance(next_time, profile.mode, profile.phases)
            else:
                result = profile.runtime.move(next_state, next_time, actor, move, roll)
                next_time["acted"][actor] = next_time["acted"].get(actor, 0) + 1
            next_state["revision"] += 1
            next_state["history"] = (
                next_state["history"]
                + [
                    {
                        "revision": next_state["revision"],
                        "type": kind,
                        "actor_uid": actor if kind != "advance" else instance.gm_uid,
                        **result,
                    }
                ]
            )[-100:]
            profile.runtime.validate(next_state)
            profile_progression.validate(next_time, profile.mode, profile.phases)
            profile_run.install(instance, next_state)
            profile_progression.install(instance, next_time)
            try:
                await self.deps.save(instance)
            except BaseException:
                profile_run.install(instance, state)
                profile_progression.install(instance, time)
                raise
            return {
                "ok": True,
                "result": result,
                "view": self.view(
                    instance, uid, gm, actor if kind != "advance" else ""
                ),
            }
