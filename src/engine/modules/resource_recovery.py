"""One-use recovery qualifications and receipts; character sheets own balances.

Service callers own locks, authorization, time advancement and persistence. A
source's seed must be persisted before it is approved and settled. Rest retries
therefore cannot change a failed outcome or claim a qualification twice.
"""
from __future__ import annotations

from copy import deepcopy
import random
import re
import secrets
from typing import Any
from types import SimpleNamespace
from uuid import uuid4

from src.engine import module_hooks
from src.engine.character_utils import apply_bounded_stat_delta
from src.engine.game_state import GameState
from src.engine.module_state import ModuleStateError, ModuleStateSpec, register_module_state
from src.engine.modules import progression_state
from src.engine.world_state import WORLD_STATE_SCHEMA_VERSION, clock_to_minutes
from src.rulesets.resource_recovery import (
    KINDS, RESOURCES, managed_resources, policy, requirements, resolve_delta, reward_delta, skill_value,
)

MODULE_NAME = "resource_recovery"
SCHEMA_VERSION = 1
MAX_RECORDS = 10000


def fresh() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "revision": 0, "sources": {},
            "receipts": {}, "operations": {}, "consumed": {}, "commands": {}}


def ensure(raw: Any) -> dict[str, Any]:
    return raw if isinstance(raw, dict) else fresh()


def _identity(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 240:
        raise ValueError(f"invalid recovery {field}")
    return value


def _valid_source(source: Any, identity: str) -> bool:
    if not isinstance(source, dict):
        return False
    strings = ("run_id", "actor_uid", "healer_uid", "skill_id", "resource_key", "reason", "authorizer", "origin_id")
    if (source.get("id") != identity or source.get("source_id") != identity
            or not source.get("run_id") or not source.get("actor_uid")
            or any(not isinstance(source.get(key), str) for key in strings)
            or not isinstance(source.get("kind"), str) or source["kind"] not in KINDS
            or not isinstance(source.get("status"), str) or source["status"] not in {"pending", "approved", "settled", "rejected"}
            or not isinstance(source.get("seed"), str) or not re.fullmatch(r"[0-9a-f]{64}", source["seed"])
            or type(source.get("started_tick")) is not int or source["started_tick"] < 0
            or type(source.get("created_round")) is not int or source['created_round'] < 0):
        return False
    if source["status"] in {"approved", "settled"} and not source["authorizer"]:
        return False
    selected = source.get("policy")
    try:
        # The strategy validator also rejects unsupported future contracts.
        policy(SimpleNamespace(template={"resource_recovery": selected}))
        if source["kind"] == "reward":
            reward_delta(source.get("resource_delta"))
            if source["resource_key"] not in RESOURCES:
                return False
        elif source["resource_key"] != ("luck" if source["kind"] == "luck" else "sanity"):
            return False
        if source["kind"] == "therapy" and (not source["healer_uid"] or source["skill_id"] not in {"psychology", "psychoanalysis"}):
            return False
        if source["kind"] == "luck" and not source["origin_id"]:
            return False
    except (TypeError, ValueError):
        return False
    return True


def _validate(raw: Any, *, nested: bool = False) -> None:
    if (not isinstance(raw, dict) or type(raw.get("schema_version")) is not int
            or raw["schema_version"] != SCHEMA_VERSION or type(raw.get("revision")) is not int
            or raw["revision"] < 0):
        raise ModuleStateError("unsupported resource_recovery schema or revision")
    for key in ("sources", "receipts", "operations", "consumed", "commands"):
        if not isinstance(raw.get(key), dict) or len(raw[key]) > MAX_RECORDS:
            raise ModuleStateError(f"invalid resource_recovery {key} ledger")
    for identity, source in raw["sources"].items():
        if not isinstance(identity, str) or not _valid_source(source, identity):
            raise ModuleStateError("invalid resource_recovery source")
    for identity, receipt in raw["receipts"].items():
        source = raw["sources"].get(identity)
        if (not isinstance(receipt, dict) or not source or source["status"] != "settled"
                or receipt.get("source_id") != identity or receipt.get("run_id") != source["run_id"]
                or receipt.get("actor_uid") != source["actor_uid"]
                or receipt.get("resource_key") != source["resource_key"]
                or receipt.get("id") != identity or receipt.get("policy") != source["policy"]
                or any(receipt.get(key) != source[key] for key in ("kind", "healer_uid", "skill_id", "origin_id", "authorizer", "reason"))
                or receipt.get("purpose") != source["kind"]
                or not isinstance(receipt.get("operation_id"), str) or not receipt["operation_id"]
                or not isinstance(receipt.get("scope"), str) or not receipt["scope"]
                or not isinstance(receipt.get("rolls"), dict)
                or any(not isinstance(key, str) or type(value) is not int for key, value in receipt["rolls"].items())
                or type(receipt.get("success")) is not bool or type(receipt.get("fumble")) is not bool
                or type(receipt.get("resource_delta")) is not int
                or any(type(receipt.get(key)) is not int for key in ("before", "after", "delta", "round"))
                or receipt["round"] < 0 or receipt["before"] < 0 or receipt["after"] < 0
                or receipt["delta"] != receipt["after"] - receipt["before"]):
            raise ModuleStateError("invalid resource_recovery receipt")
        if (raw["consumed"].get(receipt["scope"]) != identity
                or raw["operations"].get(receipt["operation_id"]) != identity):
            raise ModuleStateError("recovery receipt lost its consumption or operation identity")
    for identity, source in raw["sources"].items():
        if source["status"] == "settled" and identity not in raw["receipts"]:
            raise ModuleStateError("settled recovery source has no receipt")
    for operation, identity in raw["operations"].items():
        if (not isinstance(operation, str) or not operation or not isinstance(identity, str)
                or identity not in raw["receipts"]):
            raise ModuleStateError("invalid resource_recovery operation")
    for scope, identity in raw["consumed"].items():
        if (not isinstance(scope, str) or not scope or not isinstance(identity, str)
                or identity not in raw["receipts"]):
            raise ModuleStateError("invalid resource_recovery consumption")
    for operation, record in raw["commands"].items():
        if (not isinstance(operation, str) or not operation or not isinstance(record, dict)
                or not isinstance(record.get("action"), str) or not record["action"]
                or not isinstance(record.get("body"), dict)
                or not isinstance(record.get("source_ids"), list)
                or any(not isinstance(identity, str) or identity not in raw["sources"] for identity in record["source_ids"])):
            raise ModuleStateError("invalid resource_recovery command")
    if "_before_round" in raw:
        if nested:
            raise ModuleStateError("nested resource_recovery round snapshots")
        _validate(raw["_before_round"], nested=True)


def require_writable(instance: Any) -> None:
    modules = getattr(instance, "modules", None)
    if not isinstance(modules, dict):
        raise ModuleStateError("instance has no module state container")
    if MODULE_NAME in modules:
        _validate(modules[MODULE_NAME])


def view(instance: Any) -> dict[str, Any]:
    require_writable(instance)
    return deepcopy(instance.modules.get(MODULE_NAME) or fresh())


def _tick(instance: Any) -> int:
    state = instance.world_state
    if (not isinstance(state, dict) or type(state.get("schema_version")) is not int
            or state["schema_version"] != WORLD_STATE_SCHEMA_VERSION):
        raise ValueError("recovery requires a supported authoritative world clock")
    return clock_to_minutes(state.get("clock"))


def _eligible(instance: Any, actor_uid: str) -> dict[str, Any]:
    if instance.state == GameState.ENDED:
        raise ValueError("ended runs cannot recover resources")
    if actor_uid not in instance.players or actor_uid in instance.away_players or not instance.is_alive(actor_uid):
        raise ValueError("recovery requires a present, living character")
    character = instance.get_character_sheet(actor_uid)
    if "sanity" in character and (type(character["sanity"]) is not int or character["sanity"] <= 0):
        raise ValueError("permanent madness cannot be reversed by ordinary recovery")
    if int(character.get("hp", 0) or 0) <= 0:
        raise ValueError("an unconscious character cannot perform recovery")
    combat = module_hooks.combat_view(instance)
    if combat["combat_active"] or combat["combat_state"] == "active":
        raise ValueError("recovery is unavailable during combat")
    return character


def new_source(instance: Any, kind: str, actor_uid: str, *, healer_uid: str = "", skill_id: str = "",
               resource_key: str = "", resource_delta: Any = "", reason: str = "", authorizer: str = "",
               origin_id: str = "", started_tick: int = 0,
               policy_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    state = view(instance)
    _identity(actor_uid, "actor identity")
    _eligible(instance, actor_uid)
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("unsupported recovery source kind")
    if type(started_tick) is not int or not 0 <= started_tick <= _tick(instance):
        raise ValueError("recovery start must be a server logical time")
    if policy_snapshot is None:
        raise ValueError("recovery source requires its explicit rule policy snapshot")
    selected = policy(SimpleNamespace(template={"resource_recovery": policy_snapshot}))
    if kind == "reward":
        if resource_key not in RESOURCES:
            raise ValueError("this recovery version supports only SAN and Luck")
        resource_delta = reward_delta(resource_delta)
    elif kind == "therapy":
        _identity(healer_uid, "healer identity")
        _eligible(instance, healer_uid)
        if not isinstance(skill_id, str) or skill_id not in {"psychoanalysis", "psychology"}:
            raise ValueError("therapy requires a declared canonical treatment skill")
    if kind in {"overnight", "therapy"}:
        resource_key = "sanity"
    elif kind == "luck":
        resource_key = "luck"
    if kind == "luck":
        _identity(origin_id, "intermission identity")
    if any(not isinstance(value, str) for value in (reason, authorizer, origin_id, healer_uid, skill_id, resource_key)):
        raise ValueError("recovery source labels must be strings")
    if len(state["sources"]) >= MAX_RECORDS:
        raise ValueError("recovery qualification ledger is full; records cannot be discarded")
    identity = "recovery_" + uuid4().hex
    source = {"id": identity, "source_id": identity, "run_id": instance.run_id, "kind": kind,
              "actor_uid": actor_uid, "healer_uid": healer_uid, "skill_id": skill_id,
              "resource_key": resource_key, "resource_delta": resource_delta, "reason": reason,
              "authorizer": authorizer, "origin_id": origin_id, "started_tick": started_tick,
              "status": "pending", "seed": secrets.token_hex(32), "policy": selected}
    source['created_round'] = progression_state.round_value(instance)
    state["sources"][identity] = source
    state["revision"] += 1
    instance.modules[MODULE_NAME] = state
    return deepcopy(source)


def approve_source(instance: Any, source_id: str, authorizer: str) -> dict[str, Any]:
    state = view(instance)
    _identity(authorizer, "GM authorizer")
    source = state["sources"].get(source_id)
    if source is None or source["run_id"] != instance.run_id or source["status"] == "rejected":
        raise ValueError("recovery source is missing, stale, or rejected")
    if source["status"] == "pending":
        source["authorizer"] = authorizer
        source["status"] = "approved"
        state["revision"] += 1
        instance.modules[MODULE_NAME] = state
    return deepcopy(source)


def reject_source(instance: Any, source_id: str, authorizer: str) -> dict[str, Any]:
    state = view(instance)
    _identity(authorizer, "GM authorizer")
    source = state["sources"].get(source_id)
    if source is None or source["run_id"] != instance.run_id or source["status"] == "settled":
        raise ValueError("recovery source is missing, stale, or already settled")
    if source["status"] != "rejected":
        source["status"] = "rejected"
        source["authorizer"] = authorizer
        state["revision"] += 1
        instance.modules[MODULE_NAME] = state
    return deepcopy(source)


def command(instance: Any, operation_id: str) -> dict[str, Any] | None:
    _identity(operation_id, "operation identity")
    return view(instance)["commands"].get(operation_id)


def record_command(instance: Any, operation_id: str, record: dict[str, Any]) -> None:
    _identity(operation_id, "operation identity")
    state = view(instance)
    previous = state["commands"].get(operation_id)
    if previous is not None:
        if previous != record:
            raise ValueError("recovery operation identity was already used for another command")
        return
    if len(state["commands"]) >= MAX_RECORDS:
        raise ValueError("recovery command ledger is full; identities cannot be discarded")
    state["commands"][operation_id] = deepcopy(record)
    state["revision"] += 1
    _validate(state)
    instance.modules[MODULE_NAME] = state


def _source_rng(source: dict[str, Any]) -> random.Random:
    return random.Random(f"{source['seed']}:{source['run_id']}:{source['id']}")


def _scope(source: dict[str, Any], requirement: dict[str, Any]) -> str:
    kind = source["kind"]
    if kind in {"overnight", "therapy"}:
        origin = str(source["started_tick"] // requirement["period"])
    else:
        origin = source["origin_id"] or source["id"]
    # Length-prefixed JSON prevents delimiter-bearing player ids from colliding.
    import json
    return json.dumps([source["run_id"], kind, source["actor_uid"], origin], separators=(",", ":"))


def settle(instance: Any, rule: Any, source_id: str, operation_id: str) -> dict[str, Any]:
    state = view(instance)
    _identity(operation_id, "operation identity")
    source = state["sources"].get(source_id)
    if source is None or source["run_id"] != instance.run_id:
        raise ValueError("recovery source is missing or belongs to another run")
    previous_operation = state["operations"].get(operation_id)
    if previous_operation is not None and previous_operation != source_id:
        raise ValueError("recovery operation identity was already used for another source")
    if source_id in state["receipts"]:
        return deepcopy(state["receipts"][source_id])
    if source["status"] != "approved" or not source["authorizer"]:
        raise ValueError("the GM must authorize this recovery source before settlement")
    selected = policy(rule)
    if selected is None or source["policy"] != selected:
        raise ValueError("the recovery source's rule policy has changed")
    requirement = requirements(rule, source["kind"])
    resource = source["resource_key"] if source["kind"] == "reward" else requirement["resource_key"]
    if resource not in managed_resources(rule):
        raise ValueError("this rule does not declare the requested recovery resource")
    character = _eligible(instance, source["actor_uid"])
    if type(character.get(resource)) is not int:
        raise ValueError("the character has no authoritative recovery resource")
    elapsed = _tick(instance) - source["started_tick"]
    if elapsed < requirement["duration"]:
        raise ValueError("the required recovery duration has not elapsed")
    healer = None
    if source["kind"] == "therapy":
        if source["skill_id"] not in requirement["skills"]:
            raise ValueError("this treatment skill is not allowed by the recovery policy")
        healer = _eligible(instance, source["healer_uid"])
        skill_value(rule, healer, source["skill_id"])
    scope = _scope(source, requirement)
    if scope in state["consumed"]:
        raise ValueError("this recovery qualification has already been consumed")
    if any(len(state[key]) >= MAX_RECORDS for key in ("receipts", "operations", "consumed")):
        raise ValueError("recovery receipt ledger is full; consumption records cannot be discarded")
    declared = next(item for item in rule.template["special_stats"] if item.get("key") == resource)
    cap = declared.get("max", 99)
    if type(cap) is not int or not 1 <= cap <= 1000:
        raise ValueError("recovery resource requires a valid declared maximum")
    max_key = "max_" + resource
    if max_key in character and (type(character[max_key]) is not int or character[max_key] < 0):
        raise ValueError("recovery resource has an invalid character maximum")
    cap = min(cap, character.get(max_key, cap))
    if not 0 <= character[resource] <= cap:
        raise ValueError("recovery resource is outside its declared bounds")
    raw_revision = character.get("ruleset_revision", 0)
    if type(raw_revision) is not int or raw_revision < 0:
        raise ValueError("recovery character revision is invalid")
    if "resources" in character and not isinstance(character["resources"], dict):
        raise ValueError("recovery character resource projection is invalid")
    if isinstance(character.get("resources"), dict) and resource in character["resources"] and not isinstance(character["resources"][resource], dict):
        raise ValueError("recovery character resource projection is invalid")
    rng = _source_rng(source)
    resolved = resolve_delta(rule, source, character, healer, rng)
    updated = deepcopy(character)
    before = updated[resource]
    accepted = max(-before, min(resolved["resource_delta"], cap - before))
    after = apply_bounded_stat_delta(updated, resource, accepted, max_key=max_key, default_max=cap)
    # Use the same insanity transitions as narrative SAN loss. The source RNG
    # also fixes symptom duration so a failed save cannot reroll that state.
    if resource == "sanity" and after < before:
        from src.rulesets.sanity import apply_sanity_loss
        apply_sanity_loss(instance, source['actor_uid'], updated, before - after, rng=rng)
    updated["ruleset_revision"] = raw_revision + 1
    receipt = {"id": source_id, "source_id": source_id, "run_id": instance.run_id,
               "operation_id": operation_id, "actor_uid": source["actor_uid"],
               "healer_uid": source["healer_uid"], "kind": source["kind"], "purpose": source["kind"],
               "skill_id": source["skill_id"], "check_id": f"{source_id}:check" if source["kind"] in {"therapy", "luck"} else "",
               "resource_key": resource, "resource_delta": resolved["resource_delta"],
               "before": before, "after": after, "delta": after - before,
               "rolls": resolved["rolls"], "success": resolved["success"], "fumble": resolved["fumble"],
               "policy": selected, "round": progression_state.round_value(instance),
               "origin_id": source["origin_id"], "authorizer": source["authorizer"], "reason": source["reason"],
               "scope": scope}
    source["status"] = "settled"
    state["receipts"][source_id] = receipt
    state["operations"][operation_id] = source_id
    state["consumed"][scope] = source_id
    state["revision"] += 1
    instance.set_character_sheet(source["actor_uid"], updated)
    instance.modules[MODULE_NAME] = state
    return deepcopy(receipt)


def rewind_preflight(instance: Any, target: int) -> None:
    state = view(instance)
    if any(receipt["round"] >= target for receipt in state["receipts"].values()):
        raise ValueError("cannot rewrite across a settled resource recovery; start a new run instead")


def _begin(instance: Any) -> None:
    before = view(instance)
    before.pop("_before_round", None)
    state = deepcopy(before)
    state["_before_round"] = before
    instance.modules[MODULE_NAME] = state


def _commit(instance: Any, entry: Any, _pre: Any) -> None:
    state = view(instance)
    state.pop("_before_round", None)
    # The immutable consumption ledger is an out-of-round authority. Copying
    # it into every history entry multiplies save size by the history window.
    # Rewind instead keeps receipts and invalidates qualifications from its cut.
    instance.modules[MODULE_NAME] = state


def _abort(instance: Any) -> bool:
    before = view(instance).get("_before_round")
    if isinstance(before, dict):
        instance.modules[MODULE_NAME] = deepcopy(before)
        return True
    return False


def _rewind(instance: Any, entry: Any, target: int, _source: str) -> None:
    rewind_preflight(instance, target)
    state = view(instance)
    state.pop("_before_round", None)
    changed = False
    for source in state['sources'].values():
        if (source['run_id'] == instance.run_id and source['created_round'] >= target
                and source['status'] in {'pending', 'approved'}):
            source.update(status='rejected', authorizer='history-rewind')
            changed = True
    if changed:
        state['revision'] += 1
    instance.modules[MODULE_NAME] = state


def reset(instance: Any) -> None:
    require_writable(instance)
    instance.modules[MODULE_NAME] = fresh()


register_module_state(ModuleStateSpec(MODULE_NAME, SCHEMA_VERSION, fresh, ensure))
module_hooks.register(module_hooks.AUTHORITATIVE_WRITE_ALLOWED, MODULE_NAME, require_writable)
module_hooks.register(module_hooks.ROUND_PROCESSING_BEGIN, MODULE_NAME, _begin)
module_hooks.register(module_hooks.ROUND_COMMIT, MODULE_NAME, _commit)
module_hooks.register(module_hooks.ROUND_ABORT, MODULE_NAME, _abort)
module_hooks.register(module_hooks.ROUND_REWIND_RESTORE, MODULE_NAME, _rewind)
module_hooks.register(module_hooks.ROUND_RECOVERY_PREFLIGHT, MODULE_NAME, require_writable)
module_hooks.register(module_hooks.INSTANCE_RESET_PREFLIGHT, MODULE_NAME, require_writable)
module_hooks.register(module_hooks.INSTANCE_NEW_RUN_PREFLIGHT, MODULE_NAME, require_writable)
module_hooks.register(module_hooks.INSTANCE_RESET, MODULE_NAME, reset)
