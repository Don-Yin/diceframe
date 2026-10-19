"""GM-only post-start selection of canonical game Lorebooks.

The service owns only the game-scoped projection.  Global, world, and
character bindings remain Lorebook-owned and are never rewritten here.
"""

from __future__ import annotations
from src.engine.modules import progression_state

import asyncio
import hashlib
import inspect
import json
import uuid
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from src.content_modules.refs import ContentRefError, parse_content_ref
from src.engine.modules import content_binding
from src.lorebook.resolver import BookRef, resolve_active_books
from src.webui.services._common import is_game_gm

MAX_BOOKS = 16


@dataclass(frozen=True)
class GameLorebookDependencies:
    store: Any
    get_game: Callable[[str], Any | None]
    list_books: Callable[[], dict[str, Any]]
    save_instance: Callable[[Any], Any]


class GameLorebookService:
    def __init__(self, deps: GameLorebookDependencies):
        self.deps = deps
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, game_key: str) -> asyncio.Lock:
        lock = self._locks.get(game_key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[game_key] = lock
        return lock

    def _game(self, game_key: str, owner: str, *, owner_authenticated: bool = False) -> Any:
        if not isinstance(game_key, str) or not game_key.strip():
            raise ValueError("game_key is required")
        if not isinstance(owner, str) or not owner.strip():
            raise PermissionError("GM access required")
        instance = self.deps.get_game(game_key)
        if instance is None:
            raise ValueError("game does not exist")
        # The dependency receives the authenticated owner identity.  Requiring
        # the actual GM here keeps service callers safe even when a route's
        # outer auth middleware is bypassed in tests or another adapter.
        if not is_game_gm(instance, owner, owner_authenticated=owner_authenticated):
            raise PermissionError("GM access required")
        return instance

    @staticmethod
    def _canonical_game_key(instance: Any, requested: str) -> str:
        raw = getattr(instance, "game_key", ())
        if isinstance(raw, (tuple, list)) and raw:
            return "|".join(str(part) for part in raw)
        return requested

    @staticmethod
    def _game_aliases(instance: Any, requested: str, canonical: str) -> set[str]:
        aliases = {str(requested), str(canonical)}
        legacy = getattr(instance, "game_id", "")
        if legacy:
            aliases.add(str(legacy))
        raw = getattr(instance, "game_key", ())
        if raw:
            aliases.add(str(raw))
            if isinstance(raw, (tuple, list)):
                aliases.add("|".join(str(part) for part in raw))
        return {value for value in aliases if value}

    def _catalog(self) -> list[dict[str, Any]]:
        raw = self.deps.list_books()
        if not isinstance(raw, Mapping) or not isinstance(raw.get("books"), list):
            raise ValueError("canonical Lorebook catalogue unavailable")
        catalog: list[dict[str, Any]] = []
        seen: set[str] = set()
        for value in raw["books"]:
            if not isinstance(value, Mapping):
                raise ValueError("invalid canonical Lorebook row")
            row = dict(value)
            book_id = row.get("id")
            if not isinstance(book_id, str) or not book_id.strip() or book_id in seen:
                if book_id in seen:
                    raise ValueError("duplicate canonical Lorebook identity")
                raise ValueError("invalid canonical Lorebook identity")
            seen.add(book_id)
            raw_ref = row.get("ref")
            if not isinstance(raw_ref, Mapping):
                raise ValueError("canonical Lorebook row is missing ref")
            try:
                ref = parse_content_ref(raw_ref, default_source=f"user:{book_id}")
            except (ContentRefError, ValueError, TypeError) as exc:
                raise ValueError("invalid canonical Lorebook reference") from exc
            if ref.kind != "lorebook" or ref.id != book_id:
                raise ValueError("Lorebook reference identity mismatch")
            row["id"] = book_id
            row["name"] = str(row.get("name") or book_id)
            row["enabled"] = bool(row.get("enabled", True))
            row["entry_count"] = int(row.get("entry_count", len(self.deps.store.list_book_entries(book_id))) or 0)
            row["ref"] = ref.to_portable_dict()
            catalog.append(row)
        return catalog

    @staticmethod
    def _binding_index(store: Any) -> dict[str, list[dict[str, Any]]]:
        by_book: dict[str, list[dict[str, Any]]] = {}
        for binding in store.list_bindings():
            by_book.setdefault(str(binding.get("book_id") or ""), []).append(dict(binding))
        return by_book

    def _resolved(self, instance: Any) -> list[BookRef]:
        return list(resolve_active_books(
            instance,
            viewer_kind="gm",
            viewer_uid="",
            action_actor_uids=list(getattr(instance, "action_actor_uids", []) or []),
            store=self.deps.store,
        ))

    def _selection_rows(self, instance: Any) -> tuple[list[dict[str, Any]], list[BookRef], set[str]]:
        catalog = self._catalog()
        resolved = self._resolved(instance)
        resolved_by_id = {ref.book_id: ref for ref in resolved}
        bindings = self._binding_index(self.deps.store)
        locked: set[str] = set()
        for ref in resolved:
            binding = next((row for row in bindings.get(ref.book_id, []) if str(row.get("id") or "") == ref.binding_id), None)
            if binding is not None and str(binding.get("scope_kind") or "") == "character":
                locked.add(ref.book_id)
        rows = []
        for book in catalog:
            book_id = book["id"]
            rows.append({
                "id": book_id,
                "name": book["name"],
                "enabled": book["enabled"],
                "entry_count": book["entry_count"],
                "selected": book_id in resolved_by_id,
                "locked": book_id in locked,
            })
        return rows, resolved, locked

    @staticmethod
    def _existing_content_binding(instance: Any) -> Mapping[str, Any] | None:
        """Read the already-present binding module without initializing it.

        Older game snapshots may have no content-binding module at all; that
        means automatic inheritance remains in effect.  A present module must
        be a schema we understand and must contain only canonical Lorebook
        refs.  Failing closed here prevents a future or malformed module from
        being silently rewritten by an explicit selection.
        """

        modules = getattr(instance, "modules", None)
        if modules is None:
            return None
        if not isinstance(modules, Mapping):
            raise ValueError("invalid game module container")
        if "content_binding" not in modules:
            return None
        slot = modules.get("content_binding")
        if not isinstance(slot, Mapping):
            raise ValueError("invalid content binding module")
        if type(slot.get("schema_version")) is not int or slot["schema_version"] != content_binding.SCHEMA_VERSION:
            raise ValueError("unsupported content binding schema")
        if "book_refs" not in slot or not isinstance(slot.get("book_refs"), list):
            raise ValueError("invalid content binding book_refs")
        for raw in slot["book_refs"]:
            try:
                ref = parse_content_ref(raw, default_source="world:unknown")
            except (ContentRefError, ValueError, TypeError) as exc:
                raise ValueError("invalid content binding book ref") from exc
            if ref.kind != "lorebook":
                raise ValueError("content binding book_refs must contain Lorebook refs")
        return slot

    @staticmethod
    def _state_value(instance: Any) -> str:
        state = getattr(instance, "state", "")
        return str(getattr(state, "value", state) or "").strip().lower()

    def _ensure_editable_phase(self, instance: Any) -> None:
        if self._state_value(instance) in {"creating", "created", "active_judgment", "round_processing"}:
            raise ValueError("game is not editable during its current phase")
        processing = getattr(instance, "round_processing_in_flight", None)
        if callable(processing) and processing():
            raise ValueError("game round processing is in flight")

    def selection(self, game_key: str, owner: str, *, owner_authenticated: bool = False) -> dict[str, Any]:
        instance = self._game(game_key, owner, owner_authenticated=owner_authenticated)
        content = self._existing_content_binding(instance)
        rows, _resolved, _locked = self._selection_rows(instance)
        mode = "explicit" if isinstance(content, Mapping) and content.get("book_selection") == "explicit" else "auto"
        return {
            "ok": True,
            "game_key": game_key,
            "world_id": str(getattr(instance, "world_id", "") or ""),
            "world_name": str(getattr(instance, "world_name", "") or ""),
            "mode": mode,
            "max_books": MAX_BOOKS,
            "books": rows,
        }

    def _selected_catalog(self, instance: Any, book_ids: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
        if not isinstance(book_ids, list) or len(book_ids) > MAX_BOOKS:
            raise ValueError(f"at most {MAX_BOOKS} Lorebooks may be selected")
        catalog = self._catalog()
        by_id = {row["id"]: row for row in catalog}
        selected: list[dict[str, Any]] = []
        selected_ids: set[str] = set()
        for raw in book_ids:
            if isinstance(raw, str):
                book_id = raw
                row = by_id.get(book_id)
                if row is None:
                    raise ValueError("unknown Lorebook reference")
                parsed = parse_content_ref(row["ref"], default_source=f"user:{book_id}")
            else:
                try:
                    parsed = parse_content_ref(raw, default_source="user:selection")
                except (ContentRefError, ValueError, TypeError) as exc:
                    raise ValueError("invalid Lorebook reference") from exc
                if parsed.kind != "lorebook":
                    raise ValueError("selected reference is not a Lorebook")
                book_id = parsed.id
                row = by_id.get(book_id)
                if row is None or row["ref"] != parsed.to_portable_dict():
                    raise ValueError("unknown or non-canonical Lorebook reference")
            if book_id in selected_ids:
                raise ValueError("duplicate Lorebook selection")
            if not row["enabled"] or not self.deps.store.get_lorebook(book_id) or not bool(self.deps.store.get_lorebook(book_id).get("enabled", True)):
                raise ValueError("disabled or unavailable Lorebook cannot be selected")
            selected_ids.add(book_id)
            selected.append(row)
        return selected, catalog, selected_ids

    def _validate_selection(self, instance: Any, book_ids: Any) -> tuple[list[dict[str, Any]], set[str], set[str]]:
        self._existing_content_binding(instance)
        selected, _catalog, selected_ids = self._selected_catalog(instance, book_ids)
        _rows, resolved, locked = self._selection_rows(instance)
        if selected_ids.intersection(locked):
            raise ValueError("character Lorebooks are locked")
        return selected, selected_ids, {ref.book_id for ref in resolved}

    def preview(self, game_key: str, book_ids: Any, owner: str, *, owner_authenticated: bool = False) -> dict[str, Any]:
        instance = self._game(game_key, owner, owner_authenticated=owner_authenticated)
        self._ensure_editable_phase(instance)
        selected, _selected_ids, _resolved = self._validate_selection(instance, book_ids)
        return {
            "target_name": str(getattr(instance, "world_name", "") or getattr(instance, "world_id", "") or game_key),
            "books": [{"id": row["id"], "name": row["name"]} for row in selected],
            "target_count": len(selected),
            "affected_games": [game_key],
            "recovery_hint": "Only this game's editable Lorebook bindings will change; character sources remain locked.",
        }

    def guard(self, game_key: str, book_ids: Any, owner: str, *, owner_authenticated: bool = False) -> str:
        preview = self.preview(game_key, book_ids, owner, owner_authenticated=owner_authenticated)
        instance = self._game(game_key, owner, owner_authenticated=owner_authenticated)
        catalog = self._catalog()
        selected_rows, _catalog, _selected_ids = self._selected_catalog(instance, book_ids)
        resolved = self._resolved(instance)
        aliases = self._game_aliases(
            instance, game_key, self._canonical_game_key(instance, game_key),
        )
        world_id = str(getattr(instance, "world_id", "") or "")
        actor_ids = {str(uid) for uid in (getattr(instance, "action_actor_uids", []) or [])}
        relevant = [
            row for row in self.deps.store.list_bindings()
            if (
                row.get("scope_kind") == "game" and str(row.get("scope_id") or "") in aliases
            ) or (
                row.get("scope_kind") == "world" and str(row.get("scope_id") or "") == world_id
            ) or (
                row.get("scope_kind") == "global" and str(row.get("scope_id") or "") == ""
            ) or (
                row.get("scope_kind") == "character" and str(row.get("scope_id") or "") in actor_ids
            )
        ]
        resolved_refs = [
            {
                "book_id": ref.book_id, "binding_id": ref.binding_id,
                "order": ref.order, "role": ref.role,
            }
            for ref in resolved
        ]
        payload = {
            "preview": preview,
            "selected_refs": [row["ref"] for row in selected_rows],
            "selected_books": [
                {key: row.get(key) for key in ("id", "name", "enabled", "entry_count", "ref")}
                for row in selected_rows
            ],
            "resolved_refs": resolved_refs,
            "catalog": [
                {key: row.get(key) for key in ("id", "name", "enabled", "entry_count", "ref")}
                for row in catalog
            ],
            "run_id": str(getattr(instance, "run_id", "") or ""),
            "round_number": progression_state.peek_round_value(instance),
            "state": self._state_value(instance),
            "action_actor_uids": sorted(actor_ids),
            "players": deepcopy(getattr(instance, "players", {}) or {}),
            "content_binding": deepcopy((getattr(instance, "modules", {}) or {}).get("content_binding", {})),
            "bindings": relevant,
        }
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
        return f"sha256:{digest}"

    @staticmethod
    def _runtime_refs(instance: Any, selected: list[dict[str, Any]], locked_ids: set[str]) -> list[dict[str, Any]]:
        retained: list[dict[str, Any]] = []
        content = GameLorebookService._existing_content_binding(instance)
        for raw in (content.get("book_refs", []) if content is not None else []):
            try:
                ref = parse_content_ref(raw, default_source="world:unknown")
            except (ContentRefError, ValueError, TypeError) as exc:
                raise ValueError("invalid content binding book ref") from exc
            if ref.kind != "lorebook":
                raise ValueError("content binding book_refs must contain Lorebook refs")
            if ref.kind == "lorebook" and ref.id in locked_ids:
                portable = ref.to_portable_dict()
                if portable not in retained:
                    retained.append(portable)
        for row in selected:
            if row["ref"] not in retained:
                retained.append(deepcopy(row["ref"]))
        return retained

    @staticmethod
    def _target_bindings(store: Any, aliases: set[str]) -> list[dict[str, Any]]:
        return [
            dict(row) for row in store.list_bindings()
            if str(row.get("scope_kind") or "") == "game" and str(row.get("scope_id") or "") in aliases
        ]

    def _replace_game_bindings(self, instance: Any, requested: str, selected: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str, set[str]]:
        canonical = self._canonical_game_key(instance, requested)
        aliases = self._game_aliases(instance, requested, canonical)
        before = self._target_bindings(self.deps.store, aliases)
        existing_by_id = {str(row.get("id") or ""): row for row in self.deps.store.list_bindings()}
        new_ids = {f"binding:game:{canonical}:lorebook:{row['id']}" for row in selected}
        for binding_id in new_ids:
            existing = existing_by_id.get(binding_id)
            if existing is not None and existing not in before:
                raise ValueError("game binding identity is owned by another scope")
        for row in before:
            self.deps.store.delete_binding(str(row["id"]))
        for index, row in enumerate(selected):
            self.deps.store.bind_lorebook({
                "id": f"binding:game:{canonical}:lorebook:{row['id']}",
                "book_id": row["id"], "scope_kind": "game", "scope_id": canonical,
                "role": "runtime", "order": 100 + index,
            })
        return before, canonical, aliases

    def bind_carried_game(self, candidate: Any) -> None:
        """Idempotently materialize the new game's canonical selections.

        The durable carry outbox owns retry. Only the destination scope is
        touched; the archived game and per-character sources stay unchanged.
        """
        content = self._existing_content_binding(candidate)
        if content is None:
            return
        selected, _, _ = self._selected_catalog(candidate, content.get('book_refs', []))
        canonical = '|'.join(candidate.game_key)
        before = self._target_bindings(self.deps.store, {canonical})
        try:
            self._replace_game_bindings(candidate, canonical, selected)
        except Exception:
            self._restore_game_bindings(candidate, canonical, before)
            raise

    def _restore_game_bindings(self, instance: Any, requested: str, before: list[dict[str, Any]]) -> None:
        canonical = self._canonical_game_key(instance, requested)
        aliases = self._game_aliases(instance, requested, canonical)
        for row in self._target_bindings(self.deps.store, aliases):
            self.deps.store.delete_binding(str(row["id"]))
        for row in before:
            self.deps.store.bind_lorebook(dict(row))

    @staticmethod
    def _state_fence(instance: Any) -> tuple[Any, ...]:
        modules = getattr(instance, "modules", None)
        content = deepcopy(modules.get("content_binding") if isinstance(modules, Mapping) else None)
        processing = getattr(instance, "round_processing_in_flight", None)
        processing = bool(processing()) if callable(processing) else bool(processing)
        actor_ids = tuple(str(uid) for uid in (getattr(instance, "action_actor_uids", []) or []))
        players = deepcopy(getattr(instance, "players", {}) or {})
        return (
            getattr(instance, "game_key", None),
            str(getattr(instance, "game_id", "") or ""),
            str(getattr(instance, "world_id", "") or ""),
            str(getattr(instance, "gm_uid", "") or ""),
            str(getattr(instance, "run_id", "") or ""),
            progression_state.peek_round_value(instance),
            GameLorebookService._state_value(instance),
            actor_ids,
            json.dumps(players, ensure_ascii=False, sort_keys=True, default=str),
            processing,
            json.dumps(content, ensure_ascii=False, sort_keys=True, default=str),
        )

    @staticmethod
    def _owner_id(owner: str) -> str:
        return hashlib.sha256(str(owner).encode("utf-8")).hexdigest()

    @staticmethod
    def _bindings_fingerprint(bindings: list[dict[str, Any]]) -> str:
        return json.dumps(bindings, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))

    def _mark_uncertain(self, operation_id: str, owner_id: str, payload: dict[str, Any]) -> None:
        uncertain = deepcopy(payload)
        uncertain["phase"] = "uncertain"
        uncertain["recovery_required"] = True
        try:
            self.deps.store.update_lorebook_operation(
                operation_id, owner_id, {"payload": uncertain},
            )
        except BaseException:
            # The prepared row itself is the durable evidence if even its
            # diagnostic update cannot be written.
            return

    async def apply(
        self,
        game_key: str,
        book_ids: Any,
        owner: str,
        *,
        owner_authenticated: bool = False,
        expected_guard: str | None = None,
    ) -> dict[str, Any]:
        async with self._lock_for(str(game_key)):
            instance = self._game(game_key, owner, owner_authenticated=owner_authenticated)
            self._ensure_editable_phase(instance)
            if expected_guard is not None:
                current_guard = self.guard(
                    game_key, book_ids, owner,
                    owner_authenticated=owner_authenticated,
                )
                if current_guard != expected_guard:
                    return {
                        "ok": False, "game_key": game_key,
                        "error": "selection approval is stale; preview again",
                        "error_code": "STALE_GUARD",
                    }
            selected, _selected_ids, _resolved = self._validate_selection(instance, book_ids)
            _rows, _resolved_refs, locked_ids = self._selection_rows(instance)
            modules = getattr(instance, "modules", {})
            before_module_present = isinstance(modules, dict) and "content_binding" in modules
            before_module_snapshot = deepcopy(modules.get("content_binding")) if before_module_present else None
            before_module = deepcopy(before_module_snapshot)
            if before_module is None:
                before_module = content_binding.fresh()
            runtime_refs = self._runtime_refs(instance, selected, locked_ids)
            after_module = deepcopy(before_module)
            after_module["book_selection"] = "explicit"
            after_module["book_refs"] = deepcopy(runtime_refs)
            before_fence = self._state_fence(instance)
            canonical_before = self._canonical_game_key(instance, game_key)
            aliases_before = self._game_aliases(instance, game_key, canonical_before)
            bindings_before = self._target_bindings(self.deps.store, aliases_before)
            if self._state_fence(instance) != before_fence or self._target_bindings(self.deps.store, aliases_before) != bindings_before:
                return {"ok": False, "game_key": game_key, "error": "game state changed; reload and retry"}
            owner_id = self._owner_id(owner)
            operation_id = uuid.uuid4().hex
            payload: dict[str, Any] = {
                "phase": "prepared",
                "owner_id": owner_id,
                "game_key": game_key,
                "canonical_game_key": canonical_before,
                "before": {
                    "content_binding": deepcopy(before_module_snapshot),
                    "bindings": deepcopy(bindings_before),
                },
                "after": {
                    "content_binding": deepcopy(after_module),
                    "book_ids": [row["id"] for row in selected],
                },
            }
            with self.deps.store.transaction():
                before_bindings, canonical, _aliases = self._replace_game_bindings(instance, game_key, selected)
                after_bindings = self._target_bindings(self.deps.store, self._game_aliases(instance, game_key, canonical))
                payload["before"]["bindings"] = deepcopy(before_bindings)
                payload["after"]["bindings"] = deepcopy(after_bindings)
                self.deps.store.record_lorebook_operation({
                    "id": operation_id,
                    "owner": owner_id,
                    "kind": "game_lorebooks",
                    "status": "prepared",
                    "payload": payload,
                })
            after_binding_fingerprint = self._bindings_fingerprint(after_bindings)
            after_fence: tuple[Any, ...] | None = None
            try:
                content_binding.select_books_explicitly(instance)
                content_binding.replace_book_refs(instance, runtime_refs)
                after_fence = self._state_fence(instance)
                result = self.deps.save_instance(instance)
                if inspect.isawaitable(result):
                    await result
                if (
                    after_fence is None or self._state_fence(instance) != after_fence
                    or self._bindings_fingerprint(self._target_bindings(self.deps.store, self._game_aliases(instance, game_key, canonical))) != after_binding_fingerprint
                ):
                    self._mark_uncertain(operation_id, owner_id, payload)
                    return {
                        "ok": False, "game_key": game_key,
                        "error": "game state or bindings changed during save; manual recovery required",
                        "recovery_required": True,
                    }
                payload["phase"] = "applied"
                with self.deps.store.transaction():
                    if not self.deps.store.update_lorebook_operation(
                        operation_id, owner_id, {"status": "applied", "payload": payload},
                    ):
                        raise RuntimeError("prepared game Lorebook operation disappeared")
            except asyncio.CancelledError:
                self._mark_uncertain(operation_id, owner_id, payload)
                raise
            except BaseException as exc:
                # A callback is allowed to fail before or after persistence.  Only
                # compensate when the guarded run/module state is still ours.
                if not isinstance(exc, Exception):
                    self._mark_uncertain(operation_id, owner_id, payload)
                    raise
                current_bindings = self._target_bindings(
                    self.deps.store, self._game_aliases(instance, game_key, canonical),
                )
                if (
                    after_fence is None or self._state_fence(instance) != after_fence
                    or self._bindings_fingerprint(current_bindings) != after_binding_fingerprint
                ):
                    self._mark_uncertain(operation_id, owner_id, payload)
                    return {
                        "ok": False, "game_key": game_key,
                        "error": "save outcome or bindings are uncertain; manual recovery required",
                        "recovery_required": True,
                    }
                try:
                    with self.deps.store.transaction():
                        self._restore_game_bindings(instance, game_key, before_bindings)
                    content_binding.restore_snapshot(
                        instance, before_module, present=before_module_present,
                    )
                    restored_fence = self._state_fence(instance)
                    restored_bindings_fingerprint = self._bindings_fingerprint(
                        self._target_bindings(self.deps.store, self._game_aliases(instance, game_key, canonical)),
                    )
                    compensation = self.deps.save_instance(instance)
                    if inspect.isawaitable(compensation):
                        await compensation
                    if (
                        self._state_fence(instance) != restored_fence
                        or self._bindings_fingerprint(
                            self._target_bindings(self.deps.store, self._game_aliases(instance, game_key, canonical)),
                        ) != restored_bindings_fingerprint
                    ):
                        self._mark_uncertain(operation_id, owner_id, payload)
                        return {
                            "ok": False, "game_key": game_key,
                            "error": "compensation outcome is uncertain; manual recovery required",
                            "recovery_required": True,
                        }
                    payload["phase"] = "undone"
                    with self.deps.store.transaction():
                        if not self.deps.store.update_lorebook_operation(
                            operation_id, owner_id, {"status": "undone", "payload": payload},
                        ):
                            raise RuntimeError("prepared game Lorebook operation disappeared")
                except BaseException:
                    self._mark_uncertain(operation_id, owner_id, payload)
                    return {
                        "ok": False, "game_key": game_key,
                        "error": "save failed; compensation was not confirmed",
                        "recovery_required": True,
                    }
                return {"ok": False, "game_key": game_key, "error": str(exc) or "save failed"}
            return {
                "ok": True, "game_key": game_key,
                "world_id": str(getattr(instance, "world_id", "") or ""),
                "world_name": str(getattr(instance, "world_name", "") or ""),
                "mode": "explicit", "max_books": MAX_BOOKS,
                "book_ids": [row["id"] for row in selected],
            }


__all__ = ["GameLorebookDependencies", "GameLorebookService", "MAX_BOOKS"]
