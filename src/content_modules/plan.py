"""Confirmable import plans: per-item decisions and plan revalidation.

A preview shows the user, item by item, what a commit would do against the
server state *at preview time*. The commit request echoes ``plan_digest``; the
server recomputes the plan from the re-sent documents and the current state
and refuses to act on a plan the user did not see (``PLAN_STALE``).

The digest covers, per item, the draft digest, the matched canonical object
and that object's state token. Decisions are not part of it: they are the
user's answer to the plan, not part of the plan.

This module owns only the kind-neutral vocabulary. Each content kind owns its
matching, its state token and its writes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

PlanAction = Literal["create", "update", "unchanged", "unsupported"]
Decision = Literal["update", "duplicate", "skip"]

DECISIONS: tuple[Decision, ...] = ("update", "duplicate", "skip")

PLAN_STALE = "PLAN_STALE"
DECISION_REQUIRED = "DECISION_REQUIRED"
DECISION_NOT_ALLOWED = "DECISION_NOT_ALLOWED"
ITEM_UNSUPPORTED = "ITEM_UNSUPPORTED"

#: Source kinds a client may declare for its own content. Every other kind
#: (plugin, module, builtin, ...) is assigned by server-side import code.
DECLARABLE_SOURCE_KINDS = frozenset({"device"})


@dataclass(frozen=True, slots=True)
class DeclaredSource:
    """A client's declared identity for one pushed item."""

    source_kind: str
    source_id: str
    external_id: str


def declared_import_source(source: Any, external_id: Any) -> DeclaredSource | None:
    """Validate the identity a client declares; ``None`` when it declares none.

    Fails closed (``ValueError``) on anything but a canonical device identity:
    a client may name its own install and its own content id, never another
    source's.
    """

    from src.engine.world.contracts import canonical_id

    if source is None and external_id is None:
        return None
    kind, source_id = declared_source_ref(source)
    external = canonical_id(external_id, field="external id")
    return DeclaredSource(kind, source_id, external)


def declared_source_ref(source: Any) -> tuple[str, str]:
    """Validate a declared ``{kind, id}`` source on its own (``ValueError``)."""

    from src.engine.world.contracts import canonical_id

    if not isinstance(source, dict):
        raise ValueError("source must be an object with kind and id")
    kind = source.get("kind")
    if kind not in DECLARABLE_SOURCE_KINDS:
        raise ValueError(f"source kind cannot be declared by a client: {kind!r}")
    return str(kind), canonical_id(source.get("id"), field="source id")


@dataclass(frozen=True, slots=True)
class ExistingMatch:
    """The canonical object a draft's identity currently resolves to."""

    canonical_id: str
    state_token: str
    #: ``None`` when the object predates import bookkeeping and nobody can
    #: tell whether it was edited on the server since.
    server_modified: bool | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlanItem:
    client_ref: str
    kind: str
    draft_digest: str
    action: PlanAction
    existing: ExistingMatch | None = None
    #: Narrower answers for this match (e.g. no "update" of a plugin card).
    restricted_to: tuple[Decision, ...] | None = None
    #: Machine-readable reason for ``unsupported`` or a restriction.
    reason: str = ""

    @property
    def allowed(self) -> tuple[Decision, ...]:
        if self.action == "unsupported" or self.existing is None:
            return ()
        if self.restricted_to is not None:
            return self.restricted_to
        # "update" on an unchanged item is accepted and writes nothing, so a
        # client can answer every match the same way.
        return DECISIONS

    def digest_basis(self) -> dict[str, str]:
        return {
            "client_ref": self.client_ref,
            "kind": self.kind,
            "draft_digest": self.draft_digest,
            "canonical_id": self.existing.canonical_id if self.existing else "",
            "state_token": self.existing.state_token if self.existing else "",
            "action": self.action,
            "allowed": ",".join(self.allowed),
        }

    def to_portable_dict(self) -> dict[str, Any]:
        existing = None
        if self.existing is not None:
            existing = {
                "canonical_id": self.existing.canonical_id,
                "state_token": self.existing.state_token,
                "server_modified": self.existing.server_modified,
                **dict(self.existing.details),
            }
        return {
            "client_ref": self.client_ref,
            "kind": self.kind,
            "draft_digest": self.draft_digest,
            "action": self.action,
            "existing": existing,
            "allowed": list(self.allowed),
            "reason": self.reason,
        }


def plan_digest(items: Iterable[PlanItem]) -> str:
    basis = sorted(
        (item.digest_basis() for item in items),
        key=lambda row: (row["kind"], row["client_ref"]),
    )
    text = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class PlanDecisionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def resolve_decision(item: PlanItem, raw: Any) -> Decision | None:
    """Validate the user's answer for one item; ``None`` means "create".

    A match always needs an explicit answer: silently picking one would make
    "overwrite my server copy" the default.
    """

    if item.action == "unsupported":
        # The item's own reason is the clearer code (e.g. RULESET_CARD_UNSUPPORTED).
        raise PlanDecisionError(item.reason or ITEM_UNSUPPORTED, "this item cannot be imported")
    if item.existing is None:
        if raw not in (None, "", "create"):
            raise PlanDecisionError(DECISION_NOT_ALLOWED, "nothing to update, duplicate or skip")
        return None
    if raw in (None, ""):
        raise PlanDecisionError(DECISION_REQUIRED, "an existing copy needs update, duplicate or skip")
    if raw not in item.allowed:
        raise PlanDecisionError(DECISION_NOT_ALLOWED, f"decision not allowed here: {raw!r}")
    decision: Decision = raw
    return decision


def content_digest(value: Any) -> str:
    """Deterministic digest of JSON-like content."""

    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "DECLARABLE_SOURCE_KINDS",
    "DECISIONS",
    "DeclaredSource",
    "ITEM_UNSUPPORTED",
    "declared_import_source",
    "declared_source_ref",
    "DECISION_NOT_ALLOWED",
    "DECISION_REQUIRED",
    "Decision",
    "ExistingMatch",
    "PLAN_STALE",
    "PlanAction",
    "PlanDecisionError",
    "PlanItem",
    "content_digest",
    "plan_digest",
    "resolve_decision",
]
