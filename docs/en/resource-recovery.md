# Resource recovery and intermissions

This page describes DiceFrame's lightweight recovery and intermission features. It is a product guide, not a complete copy of the official Call of Cthulhu rules.

## Open the panel

During Play, open **Recovery / rest** from the character rail. When the
`resource_recovery` declaration is absent, the entry is hidden and the feature
is disabled. When a declaration is present but malformed or unsupported, the
entry remains available and the panel reports a server validation error; it
fails closed. The client does not guess a policy from an old custom rule or
rewrite that rule for you.

## Request rest or treatment

1. A player chooses **Overnight rest** or **Treatment** and submits a request from the panel.
2. The GM reviews the request and approves or rejects it.
3. On approval, the server advances the game's logical clock for the declared duration, checks the character's current state, and settles the result atomically.

The clock uses elapsed time since the request: the server advances only the
remaining difference (`duration - elapsed`), never another full duration on
each approval or retry.

The character must be present, alive, conscious, and outside combat. A character with 0 SAN or permanent madness cannot be revived by ordinary recovery. The active policy supplies the exact duration, resource, and treatment skill; do not infer those values from a narration tag.

The built-in MVP profiles are deliberately small:

- `coc_light` supports an eight-hour overnight recovery that rolls `1d6` SAN, and treatment using the skills declared by the policy (a successful treatment rolls `1d3`).
- `coc7e_style` does not grant SAN from overnight rest and uses a 30-day Psychoanalysis treatment. It is a style profile, not a complete official rules implementation.

## Give and claim a story reward

The GM can choose a character, select SAN or Luck, enter one of the fixed reward sizes (`1d3`, `1d6`, or `1d10`) or a bounded integer, and record a reason. The server authorizes and records the reward first. The player then uses **Claim** in the panel to receive it. Submitting a reward does not apply it twice, and retrying the same operation is safe.

## Recover Luck after an intermission

After the group has actually completed an intermission, the GM can open the Luck recovery action for that intermission. The server rolls `d100` and succeeds only when the result is greater than the character's current Luck. A success grants `1d10` Luck. A failed check consumes that intermission's opportunity, so it cannot be retried by refreshing the page or changing clients.

## Party rest activity

Open **Rest activity** in the party rail to review recent requests and settlement
statuses available in the current save. Rest/treatment requests and outcomes,
and cooperative short/long rest status, are shared with members. SAN/Luck
balances, treatment reasons, check rolls and private GM rewards retain their
existing access rules and are never included in these notices.

New activity shows one non-focusing notice by default. It disappears after five
seconds and can be dismissed immediately. Select **Mute reminders**, or disable
**Show rest reminders (only me)** inside **Rest activity**, to silence notices.
This device remembers the preference separately for each game and identity. It
does not affect other members, approvals or settlement. Activity remains
available to open manually; entering, refreshing or re-enabling reminders never
replays existing records. Notices do not enter the story chat or resize its input.
Cooperative rests reflect the existing rest session, rather than a separate
permanent rest ledger.

## Rules and compatibility

Recovery uses fixed v1 policy profiles rather than a general-purpose rules DSL. The server owns the logical clock, character balance, deterministic seed, receipt, and one-use ledger. Narrative or legacy positive SAN/Luck tags do not authorize a positive change when a recovery policy is active.

Old saves and custom rules without a valid policy remain unchanged and unsupported by this feature. DiceFrame does not infer missing policy, silently convert old semantics, or force a migration. A save imported across the recovery authority boundary also refuses pending recovery work instead of reconstructing it from history.

Guests connected through P2P can read recovery state and use the player request/claim operations. GM approval, rejection, rewards, Luck checks, clock advancement, and settlement remain server-authorized actions.
