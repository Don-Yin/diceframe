"""Checkpointed, owner-private plans for bounded lorebook visibility changes.

The planner snapshots identity and impact metadata only.  Entry bodies remain in
the owning content service and are never copied into an executable action
payload.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from src.application_action_execution import ActionExecutionStopped, ActionExecutionContext
from src.application_actions import ActionAssessment, PreparedAction, _digest
from src.knowledge.visibility import classify_audience, visibility_values
from src.webui.services.assistant_content import _has_private_markers


_MAX_BOOKS = 128
_MAX_ENTRIES = 1000
_AUDIENCES = frozenset({"gm", "public", "characters"})


@dataclass(frozen=True)
class LorebookVisibilityPlanDependencies:
    list_entries: Callable
    snapshot: Callable
    preview: Callable
    write: Callable
    receipt: Callable
    game_players: Callable


def _audience_values(value: Any) -> set[str]:
    if isinstance(value, dict):
        value = value.get("visible_to")
    if isinstance(value, str) and value in _AUDIENCES:
        return {"*"} if value == "public" else set() if value == "gm" else {value}
    return {str(item).strip() for item in visibility_values(value) if str(item).strip()}


def _is_public(values: set[str]) -> bool:
    return classify_audience({'visible_to': list(values)}) == 'public'


def audience_expands(before: Any, after: Any) -> bool:
    """Return whether ``after`` discloses to a wider audience than ``before``.

    The comparison is intentionally made against the stored marker lists.  A
    public entry remains public without another consent prompt, while adding a
    character to an existing character audience is disclosure.
    """
    before_values = _audience_values(before)
    after_values = _audience_values(after)
    if _is_public(after_values):
        return not _is_public(before_values)
    if _is_public(before_values):
        return False
    before_characters = before_values
    after_characters = after_values
    if not after_characters:
        return False
    return not after_characters.issubset(before_characters)


def _canonical_audience(audience: str, character_ids: list[str] | None = None) -> list[str]:
    if audience == "gm":
        return []
    if audience == "public":
        return ["*"]
    return list(character_ids or [])


def _projection(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ValueError("visibility preview must be an object")
    games = value.get("affected_games", [])
    if not isinstance(games, list) or any(not isinstance(item, str) or not item for item in games):
        raise ValueError("visibility preview has invalid affected games")
    changed = value.get("changed_count")
    if type(changed) is not int or changed < 0:
        raise ValueError("visibility preview has invalid changed count")
    return {"changed_count": changed, "affected_games": sorted(set(games))}


def _stable_operation_id(plan_id: str, book_id: str) -> str:
    return hashlib.sha256(f"{plan_id}:{book_id}".encode()).hexdigest()[:32]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class LorebookVisibilityPlans:
    def __init__(self, deps: LorebookVisibilityPlanDependencies):
        self.deps = deps

    @staticmethod
    def _owner(owner: str) -> str:
        if not isinstance(owner, str) or not owner.strip():
            raise PermissionError("Owner identity required")
        return owner

    @staticmethod
    def _book_ids(args: dict) -> list[str]:
        if not isinstance(args, dict):
            raise ValueError("Visibility plan arguments must be an object")
        has_many = "book_ids" in args
        has_one = "book_id" in args
        if has_many == has_one:
            raise ValueError("Provide explicit book_ids or one book_id")
        if has_many:
            values = args.get("book_ids")
            if (not isinstance(values, list) or not 1 <= len(values) <= _MAX_BOOKS
                    or any(not isinstance(value, str) or not value.strip() for value in values)
                    or len(set(values)) != len(values)):
                raise ValueError("book_ids must be explicit, unique, and contain at most 128 books")
            return list(values)
        value = args.get("book_id")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("book_id must be a non-empty string")
        return [value]

    @staticmethod
    def _entry_ids(args: dict, entries: list[dict], single: bool) -> list[str]:
        if "entry_ids" not in args:
            return [str(row.get("id")) for row in entries]
        if not single or not isinstance(args.get("entry_ids"), list):
            raise ValueError("entry_ids is supported only for one explicit book")
        values = args["entry_ids"]
        if (len(values) > _MAX_ENTRIES
                or any(not isinstance(value, str) or not value.strip() for value in values)
                or len(set(values)) != len(values)):
            raise ValueError("entry_ids must be explicit and unique")
        available = {str(row.get("id")) for row in entries}
        if any(value not in available for value in values):
            raise ValueError("entry_ids must identify existing entries in the selected book")
        return list(values)

    @staticmethod
    def _players(deps: LorebookVisibilityPlanDependencies, game_key: str, owner: str) -> set[str]:
        value = deps.game_players(game_key, owner)
        if isinstance(value, dict):
            value = value.get("players", value)
        if isinstance(value, dict):
            return {str(identity) for identity in value if isinstance(identity, str) and identity.strip()}
        if isinstance(value, list):
            result = set()
            for player in value:
                if isinstance(player, dict):
                    identity = player.get("user_id", player.get("uid", player.get("id")))
                    if isinstance(identity, str) and identity.strip():
                        result.add(identity)
            return result
        raise ValueError("Unable to resolve canonical game character identities")

    def prepare(self, args: dict, owner: str) -> PreparedAction:
        owner = self._owner(owner)
        book_ids = self._book_ids(args)
        audience = args.get("audience")
        if audience not in _AUDIENCES:
            raise ValueError("audience must be gm, public, or characters")
        game_key = args.get("game_key")
        character_ids = args.get("character_ids")
        if audience == "characters":
            if not isinstance(game_key, str) or not game_key.strip():
                raise ValueError("game_key is required for character visibility")
            if (not isinstance(character_ids, list) or not character_ids
                    or len(character_ids) > _MAX_ENTRIES
                    or any(not isinstance(value, str) or not value.strip() for value in character_ids)
                    or len(set(character_ids)) != len(character_ids)):
                raise ValueError("character_ids must be explicit and unique")
            canonical = self._players(self.deps, game_key, owner)
            if any(value not in canonical for value in character_ids):
                raise ValueError("Unknown canonical character ID")
            if _is_public(set(character_ids)):
                raise ValueError('A character ID cannot be a reserved public visibility marker')
        elif game_key is not None or character_ids is not None:
            raise ValueError("game_key and character_ids are only valid for character visibility")
        target_visible = _canonical_audience(audience, character_ids)
        selected_entry_ids = args.get("entry_ids")
        books = []
        preview_books = []
        warnings = []
        expands = False
        total = changed_total = 0
        for book_id in book_ids:
            listing = self.deps.list_entries(book_id)
            if not isinstance(listing, dict) or listing.get("ok") is False:
                raise ValueError("Lorebook does not exist")
            entries = listing.get("entries")
            if not isinstance(entries, list) or len(entries) > _MAX_ENTRIES:
                raise ValueError("Each lorebook must contain at most 1000 entries")
            entry_ids = self._entry_ids(args, entries, len(book_ids) == 1)
            by_id = {str(row.get("id")): row for row in entries if isinstance(row, dict)}
            if len(by_id) != len(entries) or any(identity not in by_id for identity in entry_ids):
                raise ValueError("Lorebook entries must have canonical identities")
            selected = [by_id[identity] for identity in entry_ids]
            rows = [{"id": identity, "visible_to": deepcopy(target_visible)}
                    for identity in entry_ids
                    if by_id[identity].get("visible_to") != target_visible]
            for row in selected:
                if audience != "gm" and _has_private_markers(str(row.get("content") or "")):
                    warnings.append({"book_id": book_id, "entry_id": str(row["id"]),
                                     "warning": "private_marker"})
                if audience_expands(row, target_visible):
                    expands = True
            raw_snapshot = self.deps.snapshot(book_id)
            if not isinstance(raw_snapshot, dict):
                raise ValueError("Lorebook snapshot unavailable")
            impact = self.deps.preview(owner, book_id, rows, _digest(entries))
            impact_projection = _projection(impact)
            if impact_projection["changed_count"] != len(rows):
                raise ValueError("Visibility preview changed while preparing")
            name = str((listing.get("book") or {}).get("name") or book_id)
            affected_games = impact_projection["affected_games"]
            books.append({
                "book_id": book_id,
                "name": name,
                "entry_ids": list(entry_ids),
                "entries_digest": _digest(entries),
                "snapshot_digest": _digest(raw_snapshot),
                "impact": impact_projection,
                "impact_digest": _digest(impact_projection),
                "rows": rows,
            })
            preview_books.append({"book_id": book_id, "name": name, "total": len(entry_ids),
                                  "changed_count": len(rows), "affected_games": affected_games})
            total += len(entry_ids)
            changed_total += len(rows)
        targets = [{"id": row["book_id"], "label": row["name"], "total": row["total"],
                    "changed_count": row["changed_count"], "affected_games": row["affected_games"]}
                   for row in preview_books]
        preview = {"ok": True, "audience": audience, "books": preview_books,
                   "targets": targets,
                   "book_count": len(books), "total": total, "changed_count": changed_total,
                   "batch_count": sum((row['changed_count'] + 15) // 16 for row in preview_books),
                   "affected_games": sorted({game for row in preview_books for game in row["affected_games"]})}
        if warnings:
            preview["warnings"] = warnings
        payload = {"version": 1, "audience": audience, "game_key": game_key,
                   "character_ids": list(character_ids or []), "books": books,
                   "warnings": warnings}
        # A game validates live character identities; it does not own global
        # book metadata. A caller-supplied game key cannot grant book access.
        targets = tuple({"book_id": book_id} for book_id in book_ids)
        assessment = ActionAssessment(effect="disclosure" if expands else "write",
                                      requires_approval=expands, targets=targets)
        return PreparedAction(guard=_digest(payload), preview=preview, payload=payload,
                              assessment=assessment)

    @staticmethod
    def _state_for(context: ActionExecutionContext, payload: dict) -> dict:
        plan_digest = _digest(payload)
        state = context.state if isinstance(context.state, dict) else {}
        if state.get("plan_digest") not in (None, plan_digest):
            raise ValueError("Execution checkpoint belongs to another visibility plan")
        if not isinstance(state.get("books", {}), dict):
            raise ValueError("Visibility execution checkpoint is invalid")
        return {"plan_digest": plan_digest, "books": deepcopy(state.get("books", {}))}

    @staticmethod
    def _request_digest(book: dict) -> str:
        return _digest({"book_id": book["book_id"], "rows": book["rows"],
                        "expected_entries_digest": book["entries_digest"]})

    @staticmethod
    def _report(payload: dict, state: dict, status: str, error: str | None = None) -> dict:
        rows = []
        for book in payload["books"]:
            item = state["books"].get(book["book_id"], {})
            raw_status = item.get("status", "not_executed")
            if item.get("uncertain") is True or raw_status in {"running", "unconfirmed"}:
                item_status = "unconfirmed"
            elif raw_status in {"succeeded", "failed", "not_executed"}:
                item_status = raw_status
            else:
                item_status = "not_executed"
            row = {"book_id": book["book_id"], "name": book["name"],
                   "status": item_status,
                   "changed_count": int(item.get("changed_count", 0)),
                   "operation_ids": list(item.get("operation_ids", []))}
            if item.get("error"):
                row["error"] = item["error"]
            rows.append(row)
        targets = [{"id": row["book_id"], "label": row["name"],
                    "status": row["status"], "changed_count": row["changed_count"],
                    "operation_ids": list(row["operation_ids"]),
                    **({"error": row["error"]} if "error" in row else {})}
                   for row in rows]
        successes = sum(row["status"] == "succeeded" for row in rows)
        failures = sum(row["status"] == "failed" for row in rows)
        unconfirmed = sum(row["status"] == "unconfirmed" for row in rows)
        pending = sum(row["status"] == "not_executed" for row in rows)
        if status == "failed" and successes:
            status = "partial"
        changed = sum(row["changed_count"] for row in rows if row["status"] == "succeeded")
        result = {"ok": status == "completed", "status": status, "books": rows,
                  "targets": targets,
                  "changed_count": changed, "success_count": successes,
                  "failed_count": failures, "unconfirmed_count": unconfirmed,
                  "not_executed_count": pending}
        if error:
            result["error"] = error
        return result

    @classmethod
    def _checkpoint(cls, context: ActionExecutionContext, payload: dict, state: dict,
                    status: str, error: str | None = None) -> None:
        if status == "completed" and any(
                state["books"].get(book.get("book_id"), {}).get("status") != "succeeded"
                for book in payload.get("books", [])):
            status = "partial"
        state["report"] = cls._report(payload, state, status, error)
        context.checkpoint(state)

    async def execute(self, payload: dict, owner: str, context: ActionExecutionContext) -> dict:
        owner = self._owner(owner)
        if not isinstance(payload, dict) or not isinstance(payload.get("books"), list):
            raise ValueError("Invalid visibility plan payload")
        state = self._state_for(context, payload)
        for book in payload["books"]:
            book_id = book.get("book_id")
            if not isinstance(book_id, str) or not isinstance(book.get("rows"), list):
                raise ValueError("Invalid visibility plan book payload")
            item = state["books"].setdefault(book_id, {})
            operation_id = _stable_operation_id(context.plan_id, book_id)
            item.setdefault("operation_id", operation_id)
            if item.get("status") == "succeeded":
                await asyncio.sleep(0)
                continue
            stored = await _maybe_await(self.deps.receipt(owner, operation_id))
            if stored is not None:
                if not isinstance(stored, dict) or stored.get("operation_id", operation_id) != operation_id:
                    raise ValueError("Visibility receipt does not match the plan")
                if stored.get("request_digest") != self._request_digest(book):
                    raise ValueError("Visibility receipt request does not match the plan")
                item.update(status="succeeded", changed_count=int(stored.get("changed_count", len(book["rows"]))),
                            operation_ids=list(stored.get("operation_ids", [])), uncertain=False, error=None)
                self._checkpoint(context, payload, state, "completed")
                await asyncio.sleep(0)
                continue
            if item.get("uncertain"):
                return self._report(payload, state, "failed", item.get("error"))
            dispatch_started = False
            definitive_failure = False
            try:
                listing = self.deps.list_entries(book_id)
                current_entries = listing.get("entries") if isinstance(listing, dict) else None
                if not isinstance(current_entries, list) or _digest(current_entries) != book.get("entries_digest"):
                    raise ValueError("Visibility targets changed; please prepare a new plan")
                snapshot = self.deps.snapshot(book_id)
                if not isinstance(snapshot, dict) or _digest(snapshot) != book.get("snapshot_digest"):
                    raise ValueError("Visibility bindings changed; please prepare a new plan")
                current_ids = {str(row.get("id")) for row in current_entries if isinstance(row, dict)}
                if any(row.get("id") not in current_ids for row in book["rows"]):
                    raise ValueError("Visibility targets changed; please prepare a new plan")
                impact = self.deps.preview(owner, book_id, book["rows"], book["entries_digest"])
                if _projection(impact) != book.get("impact"):
                    raise ValueError("Affected games changed; please prepare a new plan")
                if payload.get("audience") == "characters":
                    game_key = payload.get("game_key")
                    canonical = self._players(self.deps, game_key, owner)
                    if any(identity not in canonical for identity in payload.get("character_ids", [])):
                        raise ValueError("Live character identities changed; please prepare a new plan")
                context.check()
                item.update(status="running", operation_ids=[], error=None)
                self._checkpoint(context, payload, state,
                                 "partial" if any(book_state.get("status") == "succeeded"
                                                   for book_state in state["books"].values()) else "failed")
                dispatch_started = True
                result = await _maybe_await(self.deps.write(
                    owner, book_id, deepcopy(book["rows"]), book["entries_digest"],
                    operation_id=operation_id,
                ))
                if not isinstance(result, dict) or result.get("ok") is False:
                    definitive_failure = True
                    raise ValueError((result or {}).get("error") or "Visibility write failed")
                confirmed = await _maybe_await(self.deps.receipt(owner, operation_id))
                if confirmed is None:
                    raise RuntimeError("Visibility write completed without a durable receipt")
                if confirmed.get("request_digest") != self._request_digest(book):
                    raise ValueError("Visibility receipt request does not match the plan")
                item.update(status="succeeded", changed_count=int(confirmed.get("changed_count", len(book["rows"]))),
                            operation_ids=list(confirmed.get("operation_ids", [])), uncertain=False, error=None)
                self._checkpoint(context, payload, state, "completed")
            except ActionExecutionStopped as exc:
                self._checkpoint(context, payload, state, "cancelled", str(exc) or None)
                return self._report(payload, state, "cancelled", str(exc) or None)
            except Exception as exc:
                # A write that may have committed must be reconciled by receipt
                # before a future retry is considered.
                reconciled = await _maybe_await(self.deps.receipt(owner, operation_id))
                if isinstance(reconciled, dict):
                    if reconciled.get("request_digest") != self._request_digest(book):
                        raise ValueError("Visibility receipt request does not match the plan")
                    item.update(status="succeeded", changed_count=int(reconciled.get("changed_count", len(book["rows"]))),
                                operation_ids=list(reconciled.get("operation_ids", [])), uncertain=False, error=None)
                    self._checkpoint(context, payload, state, "completed")
                    await asyncio.sleep(0)
                    continue
                item.update(status="failed", error=str(exc), uncertain=dispatch_started and not definitive_failure
                            and isinstance(exc, RuntimeError),
                            operation_ids=[])
                self._checkpoint(context, payload, state, "failed", str(exc))
                return self._report(payload, state, "failed", str(exc))
            await asyncio.sleep(0)
        return self._report(payload, state, "completed")
