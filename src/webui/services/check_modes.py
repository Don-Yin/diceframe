"""Permission and atomic persistence for runtime-owned check-mode scopes."""
from __future__ import annotations
from src.engine.modules import checks

from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from src.engine.game_state import GameState
from src.engine.modules import check_modes
from src.engine.participant_view import Viewer
from src.rulesets.contracts import CheckModePolicyRuntime


@dataclass(frozen=True)
class CheckModeDependencies:
    get_instance: Callable[[str], Any | None]
    save_instance: Callable[[Any], Awaitable[None]]
    load_rule: Callable[[Any], Any]
    rulesets: Any


class CheckModeService:
    def __init__(self, dependencies: CheckModeDependencies):
        self.deps = dependencies

    def policy(self, inst: Any, uid: str) -> dict:
        rule = self.deps.load_rule(inst)
        if rule is None:
            raise ValueError("rule missing")
        runtime = self.deps.rulesets.resolve(rule.template)
        return runtime.check_mode_policy(inst, rule, uid) if isinstance(runtime, CheckModePolicyRuntime) else {
            "kind": "", "context_id": "", "blocked_reason": "unsupported", "previews": [],
        }

    def read(self, key: str, viewer: Viewer) -> dict:
        inst = self.deps.get_instance(key)
        if inst is None:
            return {"ok": False, "error_code": "game_missing"}
        if not viewer.is_gm and (not viewer.is_seat or viewer.uid not in inst.players):
            return {"ok": False, "error_code": "forbidden"}
        try:
            slot = check_modes.state(inst)
            seats = []
            for uid, player in inst.players.items():
                if not viewer.is_gm and uid != viewer.uid:
                    continue
                policy = self.policy(inst, uid)
                blocked = policy.get("blocked_reason") or self.blocked(inst, uid)
                seats.append({"uid": uid, "name": player.get("character_name") or uid,
                              **policy, **check_modes.scoped(inst, uid, policy["context_id"]),
                              "blocked_reason": blocked})
            return {"ok": True, "revision": slot["revision"], "run_id": inst.run_id,
                    "is_gm": viewer.is_gm, "seats": seats}
        except ValueError:
            return {"ok": False, "error_code": "unsupported_state"}

    @staticmethod
    def blocked(inst: Any, uid: str) -> str:
        if inst.state not in {GameState.ACTIVE_ACTION, GameState.PAUSED}:
            return "phase_not_actionable"
        if checks.round_checks_prepared(inst) or inst.has_pending_dice():
            return "checks_prepared"
        if inst.players[uid].get("character_sheet", {}).get("deceased"):
            return "deceased"
        return ""

    async def update(self, key: str, viewer: Viewer, uid: str, operation: str, body: Any) -> dict:
        inst = self.deps.get_instance(key)
        if inst is None:
            return {"ok": False, "error_code": "game_missing"}
        if uid not in inst.players or not (viewer.is_gm or (viewer.is_seat and viewer.uid == uid and operation == "request")):
            return {"ok": False, "error_code": "forbidden"}
        if not isinstance(body, dict) or body.keys() - {"expected_revision", "run_id", "context_id", "mode", "reason"}:
            return {"ok": False, "error_code": "invalid_request"}
        try:
            async with inst.authoritative_write() as entered:
                if not entered:
                    return {"ok": False, "error_code": "game_busy"}
                async with inst._lock:
                    if self.deps.get_instance(key) is not inst or uid not in inst.players:
                        raise ValueError("game changed")
                    slot = check_modes.state(inst)
                    policy = self.policy(inst, uid)
                    if (not policy["kind"] or policy.get("blocked_reason") or self.blocked(inst, uid)
                            or body.get("run_id") != inst.run_id or body.get("context_id") != policy["context_id"]
                            or type(body.get("expected_revision")) is not int or body["expected_revision"] != slot["revision"]):
                        raise ValueError("check scope unavailable or stale")
                    before = deepcopy(slot)
                    try:
                        check_modes.change(inst, uid, operation, policy["context_id"], mode=body.get("mode"), reason=body.get("reason"))
                        await self.deps.save_instance(inst)
                    except BaseException:
                        check_modes.restore(inst, before)
                        raise
        except ValueError:
            return {"ok": False, "error_code": "invalid_or_stale_request"}
        return self.read(key, viewer)
