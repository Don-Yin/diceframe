# Lorebook adapter guide

Adapters are pure format boundaries under `src/lorebook/adapters/`. They convert external
payloads to `LorebookDraft` and must not write the store, mutate WorldState, evaluate macros,
or execute regex through another runtime. New formats must support tolerant reads, preserve
unknown fields, and report warnings through import preview.

The canonical path is:

```text
detect → draft → preview → commit_lorebook_import
```

Use `lorebook_v3` for standards-oriented export. Keep DiceFrame legacy fields in explicit
extensions/provenance rather than adding format branches to `LorebookStore`.

## Three concepts that are never derived from each other

Primary matching, the secondary-key gate, and how secondary keys combine are separate:

- `match_mode` — DiceFrame legacy primary matching (`any`/`all`/`not_any`/`not_all`).
- `selective` — canonical boolean: do `secondary_keys` gate activation at all.
- `selective_logic` — SillyTavern logic for combining secondary keys
  (`AND_ANY`/`NOT_ALL`/`NOT_ANY`/`AND_ALL`).

The primary key must match before the secondary gate is consulted. `selective=false` keeps the
secondary keys as data but must not filter, which is why it is its own canonical column rather
than something the matcher infers from the entry's source format.

## Regex compatibility

SillyTavern and Character Card regexes are JavaScript; DiceFrame executes Python `re`. Only the
safely-mappable subset runs. When an adapter reads JavaScript regexes it clears the canonical
`regex_executable` flag on the entry if any of its patterns is not valid in Python or diverges in
semantics (JavaScript's `\d`/`\w`/`\s`/`\b` are ASCII-only while Python's are Unicode-aware). The
raw pattern is preserved verbatim as data and reported through import preview as an
`unsupported regex` / `regex mismatch` warning, but the matcher never executes it — the key simply
never matches. This is why the flag is stored: the adapter is the only layer that knows the payload
is JavaScript, while the matcher must stay format-neutral and must not branch on the import source.
Adapters never rewrite, translate, or evaluate a pattern through a JavaScript runtime, and
DiceFrame-native entries (whose Python regexes are intentional) keep their flag set.

## Where DiceFrame-only fields live

`lorebook_v3` is a standards-oriented format, so DiceFrame-specific entry semantics
(`type`, `tier`, `unreliable`, `sync_on_enter`, `visible_to`, `connected_to`,
`triggers_recursive`, `match_mode`, `regex_executable`) are exported under
`extensions.diceframe` rather than expanding the standard top-level with private keys. Reads are
tolerant: an explicit standard top-level value wins, then `extensions.diceframe` is consulted, and
files produced by the older exporter (which wrote `match_mode` at top level) keep being read.

## Character Card and Tavern entry points

Every Character Card / Tavern route funnels into one canonical commit: the card body import is
separate, and an embedded `character_book` always goes adapter → preview → canonical commit →
binding. Binding precedence is canonical character uid, then the current world, then unbound.
The legacy `/api/import-tavern-card` route is a facade over the same path.
