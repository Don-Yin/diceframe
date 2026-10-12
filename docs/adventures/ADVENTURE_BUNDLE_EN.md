# Adventure Bundle v1

An Adventure Bundle is an optional, data-only story package. It owns neither rules mechanics nor a Worldbook. When no adventure is selected, advanced play starts as standard free play.

## Layout and identity

```text
templates/adventures/<directory_id>/
├─ manifest.json
├─ adventure.json
├─ content/**/*.json
└─ locales/<locale>/**/*.json
```

The directory name is only a safe local lookup key. Authoritative identity comes from manifest `adventure_id`; the current format is `diceframe:adventure-graph-v1`. Canonical entities use stable `kind:id` references. Locale files may materialize allowlisted display fields only and cannot alter references, gates, encounters, or mechanics.

## Manifest and compatibility

The manifest declares schema, canonical ID, version, format, minimum runtime contract, world policy (`fixed`, `portable`, or `agnostic`), the recommended world required by a fixed package, and supported locales. Package validation is atomic. Invalid entities, references, locale targets, or executable-content keys reject the entire package.

## Persisted binding

Game creation validates format, runtime ID/version, and world policy before saving an immutable `adventure_id / version / format / content_digest / world_id` binding. The digest covers the manifest, canonical content, every locale, and relative paths. Restart preserves the binding, and runtime loading fails closed if content changes or a fixed-world constraint no longer matches.

## Runtime boundary

An Adventure Bundle may provide a story graph and referenced scenes, NPCs, map locations, and encounter catalogs. It cannot execute code, mutate character or combat state directly, or change generic d20 behavior. D&D adapts story gates and encounters at an explicit runtime boundary; authoritative mutations still pass through Intents, EventBatches, and reducers.

Narration receives both the current adventure step and the actually selected Worldbook. Completion removes the story gate and returns to standard free play in the same world. Coach hints are local presentation state: they submit no Intent and never enter the shared timeline.

## Management lifecycle

The runtime catalogue is `data/templates/adventures/`. Bundled packages are synchronized from installation templates at startup and remain read-only; editing starts by copying one to a new canonical identity in the `user:` namespace. Custom packages support advanced JSON editing, ZIP import/export, and deletion, with every write fully revalidated in a staging directory.

As soon as any save references an `adventure_id`, that package becomes read-only. Further authoring should create a copy with a new identity or a new version package rather than mutating bound content in place. This preserves deterministic restart against the save's pinned digest.
