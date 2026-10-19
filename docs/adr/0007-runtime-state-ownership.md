# ADR-0007: Kernel state and optional table preferences

- Status: Accepted (local implementation; unreleased)
- Date: 2026-10-15

## Context

The removable-capability criterion in ADR-0005 cannot apply to credentials or
transaction receipts. Removing room access would open protected rooms and skip
credential scrubbing; removing ledger storage would break settlement reversal.
The former `table_settings` slot also mixed turn authority with optional prompt
and presentation preferences. Treating every slot as a removable capability
would weaken authority rather than improve composition.

## Decision

`room_access` and `economy_state` are kernel dependencies. New kernel
`game_config` owns difficulty, solo/multiplayer mode, seed and entry point.
These fields remain outside `GameInstance` property facades and retain their
existing canonical values, independent of display language.

Optional owners `narration_preferences` and `check_presentation` own prompt style
and narrative perspective, and dice display/luck timeout respectively. Their
neutral projections are `auto` / `None` and `auto` / `60`; explicit empty style
and zero timeout retain their distinct meanings. New games reveal dice automatically;
explicit `click` selections and historical migration defaults are preserved. They register their own
read/write/preflight and new-run carry hooks. In-place reset leaves preferences
untouched. Generic flow code reads projections and submits state kinds, without
importing those optional owners. `narrative_notes` uses the same seam; removing
its registration hides notes and drops optional writes while retaining opaque
stored data.

The `round_presentation` owner also keeps the additive `quick_actions_enabled`
display preference (default `true`). Its state/preflight/new-run hooks preserve
the preference while reset clears the transient round fields. Historical migration
output remains unchanged; normalizing a supported old slot supplies the default.
This is an initial display default, not a table-wide visibility mandate. Each player's
browser owns a separate device-local override per canonical game and actor, independent
of round/run state. Personal hiding neither changes authoritative preferences nor stops
suggestion generation.

Reward policy belongs to the economy slot as `reward_policy`, alongside the
unchanged transaction `state`. It is not copied into the ledger or rescaled.
Multi-field configuration validates every participating owner and value before
writing any field; optional ownership does not excuse partial transactions.

## Persistence and compatibility

Instance migration **44→45** moves the old table fields into the new slots and
policy owner. It is sequential, idempotent and works on a copy. Known values are
moved without interpreting locale or amounts. Unknown extra legacy fields remain
in an opaque `table_settings` remainder; no normal code consumes that remainder.
The old internal table module API is retired rather than reintroduced as a new
business facade. Existing public HTTP setting names and projections stay stable.

Unknown legacy slot versions, mixed legacy/new target slots and conflicting
reward policies are refused rather than guessed. A future economy slot can be
preserved when there is no policy to move; moving a nonempty policy into such a
slot is refused. The current instance schema fence prevents older readers from
silently interpreting a split save as an old table. Application release versions
and update-channel policy are separate from this storage version.

## Consequences and verification

Tests must cover old-save upgrade, no input mutation, idempotence, `None` versus
empty style, zero timeout, unchanged amounts/receipts, unknown and mixed shapes,
reset/new-run behavior, and rejection before partial session writes. Optional
owner removal must leave generic game flow operational. The architecture guard
ratchets direct capability coupling down; the runtime deletion audit distinguishes
generic-flow failures from tests directly exercising the missing capability.

This decision implements a bounded ownership change. It does not claim completion
of ADR-0005's proposed general game-assembly platform or add an unrestricted
mechanics event bus.
