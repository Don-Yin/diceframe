"""Lorebook 表模型 —— 与 SCHEMA / user_version 迁移产出的 on-disk 结构一一对应。

模型只服务于查询构造；建表与迁移仍由 ``store.SCHEMA`` 和 ``src.migrations.lorebook``
负责，因此字段类型只需要保证读写时的取值/类型语义与存量一致。``worlds`` 上的
外键级联由 SCHEMA 声明和 ``PRAGMA foreign_keys=ON`` 承担，模型层刻意不声明
关系字段，避免 peewee 引入第二条删除路径。
"""

from __future__ import annotations

from peewee import (
    BooleanField,
    CharField,
    CompositeKey,
    IntegerField,
    Model,
    SQL,
    TextField,
)

from src.lorebook.activation import DEFAULT_VECTOR_ACTIVATION

from src.db.peewee_bridge import SharedConnectionSqliteDatabase

database = SharedConnectionSqliteDatabase()


class World(Model):
    id = CharField(primary_key=True)
    name = CharField()
    description = TextField(default="")
    language = CharField(default="zh-CN")
    author = CharField(default="")
    version = CharField(default="1.0")
    created_at = CharField(constraints=[SQL("DEFAULT (datetime('now'))")])
    updated_at = CharField(constraints=[SQL("DEFAULT (datetime('now'))")])

    class Meta:
        database = database
        table_name = "worlds"


class Lorebook(Model):
    id = CharField(primary_key=True)
    name = CharField()
    description = TextField(default="")
    language = CharField(default="zh-CN")
    enabled = BooleanField(default=True)
    scan_depth = IntegerField(default=0)
    token_budget = IntegerField(default=0)
    recursive_scanning = BooleanField(default=False)
    settings_json = TextField(default="{}")
    source_kind = CharField(default="native")
    source_id = CharField(default="")
    source_version = CharField(default="")
    source_digest = CharField(default="")
    # The source's own id for this Book; '' for legacy one-Book-per-source rows.
    external_id = CharField(default="")
    # '' (legacy row) | tracked | detached; see migration v11.
    import_link = CharField(default="")
    # Content digest of the Book right after its last import.
    import_state_digest = CharField(default="")
    # Bumped by every entry mutation so Retriever cache fingerprints never go
    # stale (updated_at alone is second-precision).
    revision = IntegerField(default=0)
    created_at = CharField(constraints=[SQL("DEFAULT (datetime('now'))")])
    updated_at = CharField(constraints=[SQL("DEFAULT (datetime('now'))")])

    class Meta:
        database = database
        table_name = "lorebooks"


class LorebookBinding(Model):
    id = CharField(primary_key=True)
    book_id = CharField()
    scope_kind = CharField()
    scope_id = CharField(default="")
    role = CharField(default="")
    enabled = BooleanField(default=True)
    order = IntegerField(default=100, column_name="order")
    created_at = CharField(constraints=[SQL("DEFAULT (datetime('now'))")])
    updated_at = CharField(constraints=[SQL("DEFAULT (datetime('now'))")])

    class Meta:
        database = database
        table_name = "lorebook_bindings"


class LorebookEntry(Model):
    id = CharField(primary_key=True)
    book_id = CharField(null=True, default=None)
    world_id = CharField(null=True, default=None)
    name = CharField()
    type = CharField(default="other")
    keywords = TextField(default="[]")
    content = TextField(default="")
    unreliable = BooleanField(default=False)
    sync_on_enter = BooleanField(default=False)
    tier = CharField(
        default="background",
        constraints=[SQL("CHECK(tier IN ('core','background','archived'))")],
    )
    triggers_recursive = TextField(default="[]")
    visible_to = TextField(default="[]")
    is_constant = BooleanField(default=False)
    match_mode = CharField(
        default="any",
        constraints=[SQL("CHECK(match_mode IN ('any','all','not_any','not_all'))")],
    )
    sticky = IntegerField(default=0)
    cooldown = IntegerField(default=0)
    delay = IntegerField(default=0)
    order = IntegerField(default=100, column_name="order")
    probability = IntegerField(default=100)
    group = CharField(default="", column_name="group")
    group_weight = IntegerField(default=1)
    connected_to = TextField(default="[]")
    source_plugin = CharField(default="")
    enabled = BooleanField(default=True)
    secondary_keys = TextField(default="[]")
    selective_logic = CharField(default="and")
    # Whether ``secondary_keys`` actually gates activation (CCv3/ST ``selective``).
    selective = BooleanField(default=True)
    use_regex = BooleanField(default=False)
    # Whether this entry's regex keys may actually be executed. Adapters that read
    # JavaScript regexes clear it when a pattern is not safely mappable to Python,
    # so the matcher never runs a pattern whose semantics would silently differ.
    regex_executable = BooleanField(default=True)
    case_sensitive = BooleanField(default=False)
    match_whole_words = BooleanField(default=False)
    scan_depth = IntegerField(default=0)
    priority = IntegerField(default=0)
    vector_activation = CharField(default=DEFAULT_VECTOR_ACTIVATION)
    non_recursable = BooleanField(default=False)
    prevent_further_recursion = BooleanField(default=False)
    delay_until_recursion = BooleanField(default=False)
    recursion_level = IntegerField(default=0)
    groups = TextField(default="[]")
    prioritize_inclusion = BooleanField(default=False)
    group_scoring = CharField(default="")
    prompt_slot = CharField(default="")
    extensions_json = TextField(default="{}")
    provenance_json = TextField(default="{}")
    created_at = CharField(constraints=[SQL("DEFAULT (datetime('now'))")])
    updated_at = CharField(constraints=[SQL("DEFAULT (datetime('now'))")])

    class Meta:
        database = database
        table_name = "lorebook_entries"


class LorebookEmbedding(Model):
    """World lore embedding 派生缓存（migration v4）。

    不是 authority：整表删掉后可由内容自动重建。复合主键
    ``(entry_id, language, embedding_profile)`` 表达三种隔离——同一 entry 的不同语言
    文本、以及换模型/端点后的旧向量都不互相混用；``content_hash`` 是送入 embedding
    的文本指纹，内容变化即 cache miss。
    """

    entry_id = CharField()
    language = CharField()
    embedding_profile = CharField()
    content_hash = CharField()
    embedding = TextField(default="[]")
    updated_at = CharField(constraints=[SQL("DEFAULT (datetime('now'))")])

    class Meta:
        database = database
        table_name = "lorebook_embeddings"
        primary_key = CompositeKey("entry_id", "language", "embedding_profile")
