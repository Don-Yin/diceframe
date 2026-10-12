"""Lorebook database schema migrations."""

from __future__ import annotations

import sqlite3

from .sqlite import ensure_column, run_migrations, table_columns

_LOREBOOK_COLUMNS = (
    "id", "world_id", "name", "type", "keywords", "content", "unreliable",
    "sync_on_enter", "tier", "triggers_recursive", "visible_to", "is_constant",
    "match_mode", "sticky", "cooldown", "delay", "order", "probability",
    "group", "group_weight", "connected_to", "source_plugin", "created_at", "updated_at",
)

_WORLDS_COLUMNS = ("id", "name", "description", "language", "author", "version", "created_at", "updated_at")

_WORLDS_SQL = """
CREATE TABLE worlds_new (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    language TEXT DEFAULT 'zh-CN',
    author TEXT DEFAULT '',
    version TEXT DEFAULT '1.0',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

_REBUILT_ENTRIES_SQL = """
CREATE TABLE lorebook_entries_new (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'other',
    keywords TEXT NOT NULL DEFAULT '[]',
    content TEXT NOT NULL DEFAULT '',
    unreliable INTEGER DEFAULT 0,
    sync_on_enter INTEGER DEFAULT 0,
    tier TEXT DEFAULT 'background' CHECK(tier IN ('core','background','archived')),
    triggers_recursive TEXT DEFAULT '[]',
    visible_to TEXT DEFAULT '[]',
    is_constant INTEGER DEFAULT 0,
    match_mode TEXT DEFAULT 'any' CHECK(match_mode IN ('any','all','not_any','not_all')),
    sticky INTEGER DEFAULT 0,
    cooldown INTEGER DEFAULT 0,
    delay INTEGER DEFAULT 0,
    "order" INTEGER DEFAULT 100,
    probability INTEGER DEFAULT 100,
    "group" TEXT DEFAULT '',
    group_weight INTEGER DEFAULT 1,
    connected_to TEXT DEFAULT '[]',
    source_plugin TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


_EMBEDDINGS_SQL = """
CREATE TABLE IF NOT EXISTS lorebook_embeddings (
    entry_id TEXT NOT NULL,
    language TEXT NOT NULL,
    embedding_profile TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (entry_id, language, embedding_profile)
);
"""

_LOREBOOKS_SQL = """
CREATE TABLE IF NOT EXISTS lorebooks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    language TEXT DEFAULT 'zh-CN',
    enabled INTEGER NOT NULL DEFAULT 1,
    scan_depth INTEGER NOT NULL DEFAULT 0,
    token_budget INTEGER NOT NULL DEFAULT 0,
    recursive_scanning INTEGER NOT NULL DEFAULT 0,
    settings_json TEXT NOT NULL DEFAULT '{}',
    source_kind TEXT NOT NULL DEFAULT 'native',
    source_id TEXT NOT NULL DEFAULT '',
    source_version TEXT NOT NULL DEFAULT '',
    source_digest TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS lorebook_bindings (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES lorebooks(id) ON DELETE CASCADE,
    scope_kind TEXT NOT NULL,
    scope_id TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    "order" INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(book_id, scope_kind, scope_id, role)
);
"""

_V5_ENTRY_COLUMNS = _LOREBOOK_COLUMNS + (
    "book_id", "enabled", "secondary_keys", "selective_logic", "use_regex",
    "case_sensitive", "match_whole_words", "scan_depth", "priority",
    "vector_activation", "non_recursable", "prevent_further_recursion",
    "delay_until_recursion", "recursion_level", "groups", "prioritize_inclusion",
    "group_scoring", "prompt_slot", "extensions_json", "provenance_json",
)

_V5_ENTRIES_SQL = """
CREATE TABLE lorebook_entries_new (
    id TEXT PRIMARY KEY,
    book_id TEXT REFERENCES lorebooks(id) ON DELETE CASCADE,
    world_id TEXT REFERENCES worlds(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'other',
    keywords TEXT NOT NULL DEFAULT '[]',
    content TEXT NOT NULL DEFAULT '',
    unreliable INTEGER DEFAULT 0,
    sync_on_enter INTEGER DEFAULT 0,
    tier TEXT DEFAULT 'background' CHECK(tier IN ('core','background','archived')),
    triggers_recursive TEXT DEFAULT '[]',
    visible_to TEXT DEFAULT '[]',
    is_constant INTEGER DEFAULT 0,
    match_mode TEXT DEFAULT 'any' CHECK(match_mode IN ('any','all','not_any','not_all')),
    sticky INTEGER DEFAULT 0,
    cooldown INTEGER DEFAULT 0,
    delay INTEGER DEFAULT 0,
    "order" INTEGER DEFAULT 100,
    probability INTEGER DEFAULT 100,
    "group" TEXT DEFAULT '',
    group_weight INTEGER DEFAULT 1,
    connected_to TEXT DEFAULT '[]',
    source_plugin TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    enabled INTEGER NOT NULL DEFAULT 1,
    secondary_keys TEXT NOT NULL DEFAULT '[]',
    selective_logic TEXT NOT NULL DEFAULT 'and',
    use_regex INTEGER NOT NULL DEFAULT 0,
    case_sensitive INTEGER NOT NULL DEFAULT 0,
    match_whole_words INTEGER NOT NULL DEFAULT 0,
    scan_depth INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    vector_activation INTEGER NOT NULL DEFAULT 0,
    non_recursable INTEGER NOT NULL DEFAULT 0,
    prevent_further_recursion INTEGER NOT NULL DEFAULT 0,
    delay_until_recursion INTEGER NOT NULL DEFAULT 0,
    recursion_level INTEGER NOT NULL DEFAULT 0,
    groups TEXT NOT NULL DEFAULT '[]',
    prioritize_inclusion INTEGER NOT NULL DEFAULT 0,
    group_scoring TEXT NOT NULL DEFAULT '',
    prompt_slot TEXT NOT NULL DEFAULT '',
    extensions_json TEXT NOT NULL DEFAULT '{}',
    provenance_json TEXT NOT NULL DEFAULT '{}'
);
"""


def _entry_select_expression(column: str) -> str:
    """Normalize historical unconstrained values while rebuilding v3."""
    quoted = f'"{column}"'
    if column == "tier":
        return f"CASE WHEN {quoted} IN ('core','background','archived') THEN {quoted} ELSE 'background' END"
    if column == "match_mode":
        return f"CASE WHEN {quoted} IN ('any','all','not_any','not_all') THEN {quoted} ELSE 'any' END"
    if column in {"created_at", "updated_at"}:
        return f"COALESCE({quoted}, datetime('now'))"
    if column == "type":
        return f"COALESCE({quoted}, 'other')"
    if column == "keywords":
        return f"COALESCE({quoted}, '[]')"
    if column == "content":
        return f"COALESCE({quoted}, '')"
    return quoted


def _world_select_expression(column: str) -> str:
    quoted = f'"{column}"'
    if column in {"created_at", "updated_at"}:
        return f"COALESCE({quoted}, datetime('now'))"
    if column == "name":
        return f"COALESCE({quoted}, 'Unnamed World')"
    return quoted


def _v1(conn: sqlite3.Connection) -> None:
    for name, definition in (
        ("is_constant", "INTEGER DEFAULT 0"),
        ("match_mode", "TEXT DEFAULT 'any'"),
        ("sticky", "INTEGER DEFAULT 0"),
        ("cooldown", "INTEGER DEFAULT 0"),
        ("delay", "INTEGER DEFAULT 0"),
        ("order", "INTEGER DEFAULT 100"),
        ("probability", "INTEGER DEFAULT 100"),
        ("group", "TEXT DEFAULT ''"),
        ("group_weight", "INTEGER DEFAULT 1"),
        ("connected_to", "TEXT DEFAULT '[]'"),
    ):
        ensure_column(conn, "lorebook_entries", name, definition)
    ensure_column(conn, "worlds", "language", "TEXT DEFAULT 'zh-CN'")
    ensure_column(conn, "lorebook_entries", "source_plugin", "TEXT DEFAULT ''")


def _v3(conn: sqlite3.Connection) -> None:
    """Converge historical tables after the additive v2 migration."""
    world_columns = table_columns(conn, "worlds")
    worlds_sql = str(conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='worlds'"
    ).fetchone()[0] or "")
    worlds_need_rebuild = set(_WORLDS_COLUMNS) - world_columns or any(
        marker not in worlds_sql.upper().replace('"', '')
        for marker in ("CREATED_AT TEXT NOT NULL", "UPDATED_AT TEXT NOT NULL")
    )
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='lorebook_entries'"
    ).fetchone()
    table_sql = str(row[0] or "") if row else ""
    normalized = table_sql.upper().replace('"', "")
    old_columns = table_columns(conn, "lorebook_entries")
    missing_columns = set(_LOREBOOK_COLUMNS) - old_columns
    needs_rebuild = bool(missing_columns)
    needs_rebuild |= "TYPE IN" in normalized
    needs_rebuild |= "TIER IN" not in normalized or "MATCH_MODE IN" not in normalized
    if not needs_rebuild and not worlds_need_rebuild:
        return

    if worlds_need_rebuild:
        # Rebuild parent and child together so old foreign keys never point at
        # a dropped table. Missing values use the current schema defaults.
        conn.execute(_WORLDS_SQL)
        shared_worlds = [column for column in _WORLDS_COLUMNS if column in world_columns]
        if shared_worlds:
            columns = ", ".join(f'"{column}"' for column in shared_worlds)
            selected = ", ".join(_world_select_expression(column) for column in shared_worlds)
            conn.execute(
                f"INSERT INTO worlds_new ({columns}) SELECT {selected} FROM worlds"
            )
        conn.execute(
            _REBUILT_ENTRIES_SQL
            .replace("lorebook_entries_new", "lorebook_entries_world_new")
            .replace("REFERENCES worlds(id)", "REFERENCES worlds_new(id)")
        )
        shared_entries = [column for column in _LOREBOOK_COLUMNS if column in old_columns]
        if shared_entries:
            columns = ", ".join(f'"{column}"' for column in shared_entries)
            selected = ", ".join(_entry_select_expression(column) for column in shared_entries)
            conn.execute(
                f"INSERT INTO lorebook_entries_world_new ({columns}) SELECT {selected} FROM lorebook_entries"
            )
        conn.execute("DROP TABLE lorebook_entries")
        conn.execute("DROP TABLE worlds")
        conn.execute("ALTER TABLE worlds_new RENAME TO worlds")
        conn.execute("ALTER TABLE lorebook_entries_world_new RENAME TO lorebook_entries")
        for statement in (
            "CREATE INDEX IF NOT EXISTS idx_lorebook_world ON lorebook_entries(world_id)",
            "CREATE INDEX IF NOT EXISTS idx_lorebook_type ON lorebook_entries(world_id, type)",
            "CREATE INDEX IF NOT EXISTS idx_lorebook_tier ON lorebook_entries(world_id, tier)",
            "CREATE INDEX IF NOT EXISTS idx_lorebook_source ON lorebook_entries(source_plugin)",
        ):
            conn.execute(statement)
        return

    shared = [column for column in _LOREBOOK_COLUMNS if column in old_columns]
    # ``executescript`` implicitly commits in sqlite3, which would break the
    # migration runner's rollback contract. This block contains one statement.
    conn.execute(_REBUILT_ENTRIES_SQL)
    if shared:
        columns = ", ".join(f'"{column}"' for column in shared)
        selected = ", ".join(_entry_select_expression(column) for column in shared)
        conn.execute(
            f"INSERT INTO lorebook_entries_new ({columns}) "
            f"SELECT {selected} FROM lorebook_entries"
        )
    conn.execute("DROP TABLE lorebook_entries")
    conn.execute("ALTER TABLE lorebook_entries_new RENAME TO lorebook_entries")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_world ON lorebook_entries(world_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_type ON lorebook_entries(world_id, type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_tier ON lorebook_entries(world_id, tier)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_source ON lorebook_entries(source_plugin)")


def _v2(conn: sqlite3.Connection) -> None:
    """补齐早期数据库缺失的现行可选列。

    ``LorebookStore`` 的建表 SQL 只作用于新表，历史表会跳过
    ``CREATE TABLE IF NOT EXISTS``。因此所有当前 CRUD 会用到的非核心列都
    必须在 migration 中显式补齐，且默认值要兼容 SQLite 的 ALTER TABLE。
    """
    for name, definition in (
        ("description", "TEXT DEFAULT ''"),
        ("language", "TEXT DEFAULT 'zh-CN'"),
        ("author", "TEXT DEFAULT ''"),
        ("version", "TEXT DEFAULT '1.0'"),
        # SQLite 不允许 ADD COLUMN 使用 datetime('now') 这类非字面量默认值。
        ("created_at", "TEXT DEFAULT ''"),
        ("updated_at", "TEXT DEFAULT ''"),
    ):
        ensure_column(conn, "worlds", name, definition)

    for name, definition in (
        ("unreliable", "INTEGER DEFAULT 0"),
        ("sync_on_enter", "INTEGER DEFAULT 0"),
        ("tier", "TEXT DEFAULT 'background'"),
        ("triggers_recursive", "TEXT DEFAULT '[]'"),
        ("visible_to", "TEXT DEFAULT '[]'"),
        ("is_constant", "INTEGER DEFAULT 0"),
        ("match_mode", "TEXT DEFAULT 'any'"),
        ("sticky", "INTEGER DEFAULT 0"),
        ("cooldown", "INTEGER DEFAULT 0"),
        ("delay", "INTEGER DEFAULT 0"),
        ("order", "INTEGER DEFAULT 100"),
        ("probability", "INTEGER DEFAULT 100"),
        ("group", "TEXT DEFAULT ''"),
        ("group_weight", "INTEGER DEFAULT 1"),
        ("connected_to", "TEXT DEFAULT '[]'"),
        ("source_plugin", "TEXT DEFAULT ''"),
        ("created_at", "TEXT DEFAULT ''"),
        ("updated_at", "TEXT DEFAULT ''"),
    ):
        ensure_column(conn, "lorebook_entries", name, definition)


def _v4(conn: sqlite3.Connection) -> None:
    """新增纯派生的 world lore embedding 缓存表。

    这是**派生缓存**而不是 authority：删掉整表后系统仍可自动重建，因此不加迁移期
    数据回填。主键 ``(entry_id, language, embedding_profile)`` 保证三种隔离——同一
    entry 的不同语言文本、以及换模型/端点后的旧向量都不会互相混用；``content_hash``
    记录真正送入 embedding 的文本指纹，内容变化即 cache miss。
    """

    conn.execute(_EMBEDDINGS_SQL)


def _v5(conn: sqlite3.Connection) -> None:
    """Introduce canonical lorebooks/bindings while retaining world compatibility."""
    for statement in _LOREBOOKS_SQL.split(';'):
        if statement.strip():
            conn.execute(statement)
    worlds = list(conn.execute("SELECT id, name, description, language FROM worlds"))
    for world_id, name, description, language in worlds:
        book_id = f"world:{world_id}"
        conn.execute(
            "INSERT OR IGNORE INTO lorebooks "
            "(id, name, description, language, source_kind, source_id) VALUES (?, ?, ?, ?, 'world', ?)",
            (book_id, name, description or "", language or "zh-CN", world_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO lorebook_bindings "
            "(id, book_id, scope_kind, scope_id, role) VALUES (?, ?, 'world', ?, 'primary')",
            (f"binding:{book_id}:primary", book_id, world_id),
        )
    old_columns = table_columns(conn, "lorebook_entries")
    needs_rebuild = "book_id" not in old_columns or set(_V5_ENTRY_COLUMNS) - old_columns
    if needs_rebuild:
        conn.execute(_V5_ENTRIES_SQL)
        shared = [column for column in _V5_ENTRY_COLUMNS if column in old_columns]
        columns = ", ".join(f'"{column}"' for column in shared)
        selected = ", ".join(_entry_v5_expression(column) for column in shared)
        if "book_id" not in old_columns:
            columns = f"{columns}, \"book_id\""
            selected = f"{selected}, 'world:' || world_id"
        conn.execute(
            f"INSERT INTO lorebook_entries_new ({columns}) SELECT {selected} FROM lorebook_entries"
        )
        conn.execute("DROP TABLE lorebook_entries")
        conn.execute("ALTER TABLE lorebook_entries_new RENAME TO lorebook_entries")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_book ON lorebook_entries(book_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_binding_scope ON lorebook_bindings(scope_kind, scope_id)")


def _entry_v5_expression(column: str) -> str:
    if column == "book_id":
        return "NULL"
    if column in {"created_at", "updated_at"}:
        return f"COALESCE(\"{column}\", datetime('now'))"
    defaults = {
        "name": "''", "type": "'other'", "keywords": "'[]'", "content": "''",
        "unreliable": "0", "sync_on_enter": "0", "tier": "'background'",
        "triggers_recursive": "'[]'", "visible_to": "'[]'", "is_constant": "0",
        "match_mode": "'any'", "sticky": "0", "cooldown": "0", "delay": "0",
        "order": "100", "probability": "100", "group": "''", "group_weight": "1",
        "connected_to": "'[]'", "source_plugin": "''", "enabled": "1",
        "secondary_keys": "'[]'", "selective_logic": "'and'", "use_regex": "0",
        "case_sensitive": "0", "match_whole_words": "0", "scan_depth": "0",
        "priority": "0", "vector_activation": "0", "non_recursable": "0",
        "prevent_further_recursion": "0", "delay_until_recursion": "0",
        "recursion_level": "0", "groups": "'[]'", "prioritize_inclusion": "0",
        "group_scoring": "''", "prompt_slot": "''", "extensions_json": "'{}'",
        "provenance_json": "'{}'",
    }
    return f'COALESCE("{column}", {defaults.get(column, "NULL")})'


def _v6(conn: sqlite3.Connection) -> None:
    """Represent vector activation as the canonical off/hybrid/vector_only mode.

    The pre-v6 column was an INTEGER "vectorized" flag defaulting to 0, but
    pre-v2 retrieval never consulted it: every entry got the optional semantic
    enhancement. Mapping that legacy 0 to ``off`` would therefore silently strip
    semantic retrieval from all migrated lore — which is why runtime used to
    reinterpret ``off`` as ``hybrid`` on every lookup, making an explicit
    author-set ``off`` unreachable.

    Compatibility is decided **here, once**: legacy rows migrate to an explicit
    ``hybrid``, and ``off`` then means off at runtime. Only a row that already
    carried a canonical textual mode keeps that mode verbatim.
    """

    sql = _V5_ENTRIES_SQL.replace("lorebook_entries_new", "lorebook_entries_v6").replace(
        "vector_activation INTEGER NOT NULL DEFAULT 0",
        "vector_activation TEXT NOT NULL DEFAULT 'hybrid'",
    )
    conn.execute(sql)
    old_columns = table_columns(conn, "lorebook_entries")
    shared = [column for column in _V5_ENTRY_COLUMNS if column in old_columns]
    columns = ", ".join(f'"{column}"' for column in shared)
    selected = ", ".join(
        (
            '"book_id"'
            if column == "book_id" else
            "CASE "
            "WHEN lower(CAST(COALESCE(\"vector_activation\", '') AS TEXT)) "
            "IN ('off', 'hybrid', 'vector_only') THEN lower(CAST(\"vector_activation\" AS TEXT)) "
            "ELSE 'hybrid' END"
            if column == "vector_activation" else _entry_v5_expression(column)
        )
        for column in shared
    )
    conn.execute(
        f"INSERT INTO lorebook_entries_v6 ({columns}) SELECT {selected} FROM lorebook_entries"
    )
    conn.execute("DROP TABLE lorebook_entries")
    conn.execute("ALTER TABLE lorebook_entries_v6 RENAME TO lorebook_entries")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_book ON lorebook_entries(book_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lorebook_binding_scope ON lorebook_bindings(scope_kind, scope_id)")


def _v7(conn: sqlite3.Connection) -> None:
    """Add a monotonic Book revision so entry mutations invalidate matcher caches.

    ``updated_at`` only carries second precision, so two entry edits inside the
    same second would produce an identical Retriever cache fingerprint and keep
    serving a stale matcher. This counter is bumped by every entry mutation
    (add/update/delete/import) and is exact regardless of clock resolution.
    """

    ensure_column(conn, "lorebooks", "revision", "INTEGER NOT NULL DEFAULT 0")


def _v8(conn: sqlite3.Connection) -> None:
    """Add the canonical "secondary filter enabled" flag.

    CCv3/ST carry ``selective`` as a *separate* concept from ``secondary_keys``:
    ``selective=false`` keeps the secondary keys as data but must not gate
    activation. Storing the flag on the canonical entry keeps the matcher
    format-neutral instead of branching on the import source. Defaults to 1 so
    existing rows (where secondary keys implied the gate) keep their behaviour.
    """

    ensure_column(conn, "lorebook_entries", "selective", "INTEGER NOT NULL DEFAULT 1")


def _v9(conn: sqlite3.Connection) -> None:
    """Add the canonical "this entry's regex may be executed" flag.

    SillyTavern / Character Card regexes are JavaScript while DiceFrame executes
    Python ``re``. Only the safely-mappable subset may run: an incompatible
    pattern has to be preserved as data but must never be executed, because
    Python would silently apply different semantics (for example ``\\w`` is
    Unicode-aware in Python and ASCII-only in JavaScript).

    The decision is made by the adapter, which is the only layer that knows the
    payload is JavaScript, and stored canonically so the matcher stays
    format-neutral instead of branching on the import source. Defaults to 1 so
    DiceFrame-native entries keep executing their own Python regexes.
    """

    ensure_column(conn, "lorebook_entries", "regex_executable", "INTEGER NOT NULL DEFAULT 1")


def _v10(conn: sqlite3.Connection) -> None:
    """Separate a Book's external identity from its source.

    A source such as one client install pushes many Books, so ``source_id``
    alone cannot identify a Book any more: ``external_id`` is that source's own
    id for it. Existing rows keep ``external_id = ''`` and with it their current
    meaning (one Book per ``source_id``); they are never rewritten or guessed.

    The partial unique index makes "at most one Book tracks a given external
    identity" a storage invariant, while legacy rows (empty external id) stay
    outside it.
    """

    ensure_column(conn, "lorebooks", "external_id", "TEXT NOT NULL DEFAULT ''")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_lorebooks_external_identity "
        "ON lorebooks(source_kind, source_id, external_id) WHERE external_id <> ''"
    )


def _v11(conn: sqlite3.Connection) -> None:
    """Record whether a Book still follows its import source.

    ``import_link``: ``''`` for rows written before import plans existed (they
    keep their legacy meaning), ``tracked`` for the one Book a source pushes
    updates into, ``detached`` for a Book kept aside when the user chose "keep
    both". ``import_state_digest`` is the Book's content digest right after
    the last import, so a later preview can tell whether the server copy was
    edited since.

    A detached Book keeps its full provenance for display, so the uniqueness
    invariant moves to tracked (non-detached) Books only. Nothing is detached
    by this step: existing rows stay outside both the new and the old meaning
    of "detached", so the replacement index accepts exactly what v10 accepted.
    """

    ensure_column(conn, "lorebooks", "import_link", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "lorebooks", "import_state_digest", "TEXT NOT NULL DEFAULT ''")
    conn.execute("DROP INDEX IF EXISTS idx_lorebooks_external_identity")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_lorebooks_tracked_identity "
        "ON lorebooks(source_kind, source_id, external_id) "
        "WHERE external_id <> '' AND import_link <> 'detached'"
    )


MIGRATIONS: tuple[tuple[int, object], ...] = (
    (1, _v1), (2, _v2), (3, _v3), (4, _v4), (5, _v5), (6, _v6), (7, _v7), (8, _v8),
    (9, _v9), (10, _v10), (11, _v11),
)
CURRENT_LOREBOOK_SCHEMA_VERSION = MIGRATIONS[-1][0]


def migrate(conn: sqlite3.Connection, *, upto: int | None = None) -> int:
    """Run the Lorebook schema migrations.

    ``upto`` stops at a given version so tests and E2E fixtures can materialise
    an authentic older database (and then let real startup migrate it) instead of
    hand-writing a stale schema that drifts from the real one.
    """

    steps = MIGRATIONS if upto is None else tuple(step for step in MIGRATIONS if step[0] <= upto)
    return run_migrations(conn, steps)
