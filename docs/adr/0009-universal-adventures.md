# ADR-0009: Rule-neutral Adventure packages

- Status: Accepted for local implementation; unreleased
- Date: 2026-10-17

## Decision

Adventure graph v2 is the shared story execution contract. A new, explicit
package requirement, `required_runtime: {"id": "core:adventure",
"minimum_version": 1}`, selects its rule-neutral narrative profile. This is
an Adventure requirement, not a character ruleset registration. A ruleset opts
in through `capabilities.adventure_formats`; no rule name or translated label
determines compatibility. The built-in legacy adapter opts into graph v2,
covering CoC and custom rules that already use its free-form check pipeline.

The profile supports scenes, objectives, decisions, milestones, references,
world facts and progress outcomes. It rejects executable encounters, mechanical
items/rewards, rules.* gates and item_reward outcomes. Such mechanics continue
to require a specific registered ruleset and its validator. Narrative references
to checks or rewards remain descriptions for the GM, never automatic authority.
Unsupported profile versions and formats fail closed before installation or play.

The package loader owns profile validation. One Adventure compatibility module
owns admission, reused by the catalogue, launch, binding and D&D loading paths.
The module installer recognizes this profile only for Adventure requirements;
it does not relax plugin/ruleset dependency checks. Existing ruleset-specific
packages keep their runtime identity, digest, source binding and mechanics.
No package or save is silently relabelled or migrated.

Known Adventure commands use the shared application service with membership,
GM/actor authorization, current phase, binding integrity, locks and durable
rollback. They do not require a ruleset's authoritative combat-intent capability.
Other intents retain their existing admission. Player projections remain filtered.

New packages and prose imports default to this profile and graph v2. An adopted
free-game plan can be copied to an editable, reviewed Adventure draft. The copy
contains only deliberately selected plan fields, starts a fresh graph, and never
includes live progress, players, credentials, logs or world authority references.
GM notes remain GM-only content. Publication uses the existing review/digest/commit
boundary, requires explicit review, and does not bind or mutate the source game.

## Implementation and acceptance

1. Add the profile validator, shared admission, v2 authoring defaults and installer
   support. Test the same narrative package with legacy and D&D rules; reject old
   D&D packages under legacy, future versions and unsupported mechanics.
2. Admit only the two existing Adventure commands through the shared context.
   Test GM completion, player choices, unauthorized writes, save rollback and
   lifecycle fences without enabling arbitrary legacy ruleset intents.
3. Share frontend compatibility logic across creation and the library; show a
   readable universal-profile label and preserve specific-rule filtering.
4. Add plan-to-draft preparation through an explicit service dependency and the
   existing Adventure review UI. Test privacy, identity, stale source revisions,
   source immutability and the review-before-publication requirement.
5. Update architecture and author/user documentation. Verify backend regressions,
   frontend types/lint/locales/tests/build and isolated browser journeys.

## Scope

This enables reusable narrative Adventures across rules. It does not implement
CoC-specific automatic SAN, combat, reward or progression settlement, convert
old D&D mechanics, or introduce a scripting DSL. No persisted GameInstance shape
changes: existing graph/progress and plan owners keep their schemas and fences.
