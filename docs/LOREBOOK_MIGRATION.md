# Lorebook migration notes

Migration v5 creates `lorebooks` and `lorebook_bindings`, rebuilds entries with nullable
`book_id`/`world_id`, and creates one deterministic `world:<world_id>` primary book per world.
Existing worlds, entry IDs, plugin provenance, connected links, and embedding cache rows remain
usable. Reopening is idempotent and `list_entries(world_id)` reads only the primary book.

Migration v7 adds `lorebooks.revision`, a monotonic counter bumped by every entry mutation. It
exists so a cached matcher fingerprint is invalidated by book content changing, instead of
relying on a timestamp that a same-second edit can hide. Legacy `ensure_world` scoping still
reads the primary world book, and its cache key carries that book's revision.

Migration v8 adds `lorebook_entries.selective`, the canonical boolean deciding whether
`secondary_keys` gates activation at all. It defaults to `1` so existing rows keep their current
behaviour, where present secondary keys implied the gate. It is a separate column from
`secondary_keys` (the data) and `selective_logic` (how the secondary keys combine) because the
three are independent concepts.

Both columns are added with `ensure_column`, so v7/v8 do not rewrite the v5 table definitions.

Migration v9 adds `lorebook_entries.regex_executable`, the canonical flag saying whether that
entry's regex keys may be executed. SillyTavern / Character Card regexes are JavaScript while
DiceFrame executes Python `re`, so an adapter that reads JavaScript clears the flag when a
pattern cannot be mapped faithfully; the raw key is still preserved as data, but the matcher
never runs it. It defaults to `1` so DiceFrame-native entries keep executing their own Python
regexes.

A fresh database walks v1 through v9; `PRAGMA user_version` ends at 9.

Legacy timer state is converted at load/save boundaries from `{status, remaining}` to independent
`sticky_remaining` and `cooldown_remaining` counters. Ambiguous delayed state is not guessed;
the entry's delay setting controls future eligibility.

## Automatic legacy world-identity upgrade

The application performs the world-identity upgrade automatically at the front of a cold start,
before the stores and registries become live. It supports legacy Lorebook SQLite v4 and canonical
v5–v12 world/book/binding layouts, plus save files whose `instance_schema_version` is in the
current local writer's recognized range. It scans the data templates, all `saves/state*.json`
files and other known JSON references. It does not scan or rewrite arbitrary prose.

The replacement world ID is a stable ASCII hash of the old identity. This keeps two worlds with
the same display title separate. Known world/book references are rebound; display titles, entry
IDs, `game_key`, `memory_namespace` and chat/log text stay as they are. Newly generated AI worlds
also use ASCII IDs, reserve length for the `world:` primary-book prefix and prefix generated entry
IDs with the world identity.

Users do not need to edit saves by hand or disable Lorebook validation. The SQLite receipt and
durable migration journal allow an interrupted startup to roll forward. If a file was changed by
the user, a target identity already exists, or the database/save schema is invalid or from the
future, startup fails closed without overwriting the source data. This is the current local
implementation boundary; it does not promise support for every historical or future format.
