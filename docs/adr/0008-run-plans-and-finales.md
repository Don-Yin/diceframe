# ADR-0008: Run plans, deferred development and immutable finales

- Status: Accepted (local implementation; unreleased)
- Date: 2026-10-17

## Context

World facts, reusable Adventure packages and one run's story need distinct
authority. Narrator-generated quest notes cannot safely own progress, skill
improvement or the end of a multiplayer game. Existing incremental recaps also
cannot represent an entire long run. Ending a game must preserve receipts,
privacy and character values through restarts and delivery failures.

## Decision

An optional `run_story` owner stores a GM-adopted free-game plan. Typed model
transition proposals require GM confirmation, current run/revision, adjacency
and committed-round evidence. Bound Adventures keep their existing authority.
Current-scene projection is role-filtered before budgeting and model calls.
NPC state admission and stall hints assist the GM without changing dice or
making arbitrary model prose authoritative.

`skill_growth` stores settled-check marks and audited intermission receipts.
Rules opt into its versioned policy. A mark's canonical row identity is distinct
from translated labels; explicit rule aliases support legacy rows at that
boundary. Narrator tags cannot mark or roll improvement. The service first
persists an internal entropy reservation, then evaluates each marked-check
identity deterministically within settlement. Failed/cancelled final persistence
can retry without rerolling. A settled check cannot earn a second mark.

`run_finale` stores a preparation job, immutable archive and separate delivery
outbox. Preparing retains the original phase while freezing writes. The GM may
cancel preparation, save manual materials or request cancellable AI drafts.
Public whole-run sources are whitelisted before summarization; GM notes remain
separate. Materials use optimistic revisions. Explicit final confirmation
publishes rule results, character snapshots, receipt and ENDED together.

The finale write barrier and skill-development receipts are kernel authority,
following ADR-0007's distinction between storage/authority and optional UI.
Removing presentation hooks cannot reopen an archive or permit rewinding across
settled growth. HTTP transport admission and aggregate authority gates enforce
the boundary; administrative writes stay within the finale service. Credentials
may be revoked and read-only SSE subscriptions renewed without reopening story
or character mutation. Reset/restart
cannot replace an archive.

Optional workspace owners contribute invalidation values through
`gm.workspace.revisions`. An opaque GM-only revision joins the SSE cursor and
detail projection; player cursors exclude it. Same-round edits and subscription
gaps therefore refresh the workspace without publishing private material or
reloading it for every unrelated detail change. Client reads cannot overwrite
a newer successful mutation or discard its reviewed-material confirmation.

Specific rule settlement uses optional `RunFinaleRuntime`; no concrete ruleset
branch enters the generic engine. D&D audits existing rewards and pending level
choices without awarding them twice. Lite CoC applies supported intermission
development. Unimplemented SAN/money settlement is explicit rather than inferred.

Carrying characters creates a separate game/run from settled full snapshots.
The original archive's durable delivery outbox reserves the destination identity
before creating it. Retries reuse it; runtime initialization must preserve the
settled sheets exactly. Content owners materialize the new game's canonical
Lorebook selections, while room/seat credentials, NPCs and secret plans stay out.
Native character-card export follows the library contract; full-snapshot carry
is the supported way to preserve every live value into another game.

## Persistence and compatibility

Instance schema 45→46 is a reader fence. It preserves old character values and
does not reconstruct historical plans or marks. Missing new slots receive empty
state. Persisted non-object slots and damaged module containers are rejected before generic defaulting;
unsupported/future slots fail closed. Preparing saves must be cancelled
before cross-run import; ended imports stay read-only and preserve provenance.
Plan state and historical plan snapshots rebind through the migration owner.
This is a storage version, not an application release/version bump.

## Consequences and verification

Tests cover safe model input, real percentile checks, authoritative transitions,
NPC admission, snapshots, stale material review, hook detachment, failed saves,
restart, role-filtered exports, SHA-256 ZIP manifests and idempotent character
delivery. Desktop/mobile journeys exercise preparation/cancel/commit/export/
carry alongside existing play flows. Scripted model tests verify source and
state boundaries; they do not guarantee arbitrary model prose or replace
real-provider editorial acceptance. ADR-0009 adds rule-neutral narrative packages
and explicit plan-to-draft review; full CoC-specific mechanical automation remains
outside this implementation.
