"""REVIEW-7 §4/§5 — regex 不兼容就不执行；lorebook_v3 的 DiceFrame-only 字段入 extensions。

§4：Adapter 发现 JS-only 语法或 JS/Python 语义差异后，过去只 warning，仍然把
``use_regex=true`` 存下去，Matcher 继续用 Python ``re`` 执行 —— 也就是对 ``\\w+``
这种 pattern 静默套用了与 JavaScript 不同的语义。现在必须「preserve + warning +
no execute」：raw 原样保留，但永不执行。

§5：``lorebook_v3`` 是标准格式。DiceFrame-only 字段必须收进
``extensions.diceframe``，不能把 ``match_mode`` 当作自创的标准顶层字段扩张出去；
同时要能继续读旧 exporter 产生的顶层 ``match_mode``，以及读回自己导出的文件。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.lorebook.exporter import export_lorebook_v3
from src.lorebook.importer import commit_lorebook_import, preview_lorebook_import
from src.lorebook.matcher import KeywordMatcher
from src.lorebook.store import LorebookStore

JS_ONLY = "(?<name>harbor)"
MISMATCH = r"\w+"
SAFE = "^harbou?r$"


def _store(tmp_path: Path) -> LorebookStore:
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    return store


def _st_payload(*keys: str) -> dict:
    return {
        "name": "ST",
        "entries": [
            {"uid": i, "key": [key], "content": f"body-{i}", "useRegex": True}
            for i, key in enumerate(keys)
        ],
    }


def _matcher(store: LorebookStore, book_id: str) -> KeywordMatcher:
    matcher = KeywordMatcher()
    matcher.build(store.list_book_entries(book_id))
    return matcher


# ---- §4 regex：不兼容就不执行 ----------------------------------------------


def test_js_only_regex_is_preserved_warned_and_never_executed(tmp_path):
    store = _store(tmp_path)
    try:
        preview = preview_lorebook_import(_st_payload(JS_ONLY))
        draft = preview["book"]
        assert draft.entries[0].regex_executable is False
        assert any("unsupported regex" in w for w in draft.warnings)

        commit_lorebook_import(store, draft, None, book_id="b")
        stored = store.list_book_entries("b")[0]
        # raw source 原样保留（既不改写也不丢）。
        assert stored["keywords"] == [JS_ONLY]
        assert stored["use_regex"] is True
        assert stored["regex_executable"] is False
        # runtime 不命中。
        assert _matcher(store, "b").match("the harbor is quiet") == []
    finally:
        store.close()


def test_semantic_mismatch_regex_is_warned_and_not_executed(tmp_path):
    """``\\w+`` 在 Python 下会命中，但 JS 语义不同 —— 必须不执行。"""

    store = _store(tmp_path)
    try:
        preview = preview_lorebook_import(_st_payload(MISMATCH))
        draft = preview["book"]
        assert draft.entries[0].regex_executable is False
        assert any("regex mismatch" in w for w in draft.warnings)

        commit_lorebook_import(store, draft, None, book_id="b")
        stored = store.list_book_entries("b")[0]
        assert stored["keywords"] == [MISMATCH]
        assert stored["regex_executable"] is False
        assert _matcher(store, "b").match("the harbor is quiet") == [], (
            "语义不兼容的 regex 不得按 Python 语义执行"
        )
    finally:
        store.close()


def test_safely_mappable_regex_still_executes(tmp_path):
    store = _store(tmp_path)
    try:
        preview = preview_lorebook_import(_st_payload(SAFE))
        draft = preview["book"]
        assert draft.entries[0].regex_executable is True
        assert not [w for w in draft.warnings if "regex" in w]

        commit_lorebook_import(store, draft, None, book_id="b")
        assert store.list_book_entries("b")[0]["regex_executable"] is True
        matcher = _matcher(store, "b")
        assert [r["id"] for r in matcher.match("harbor")]
        assert matcher.match("the harbor is quiet") == [], "锚定 pattern 不该匹配整句"
    finally:
        store.close()


def test_mixed_keys_only_preserve_the_incompatible_one(tmp_path):
    """同一 entry 内兼容与不兼容并存：兼容的照常命中，不兼容的永不命中。"""

    store = _store(tmp_path)
    try:
        payload = {"name": "ST", "entries": [{
            "uid": 1, "key": [SAFE, MISMATCH], "content": "mixed", "useRegex": True,
        }]}
        draft = preview_lorebook_import(payload)["book"]
        # entry 上只要有一个 key 不能安全映射，该 entry 的 regex 就不执行（fail closed）。
        assert draft.entries[0].regex_executable is False
        commit_lorebook_import(store, draft, None, book_id="b")
        stored = store.list_book_entries("b")[0]
        assert stored["keywords"] == [SAFE, MISMATCH], "两个 key 都必须原样保留"
        assert _matcher(store, "b").match("harbor") == []
    finally:
        store.close()


def test_native_diceframe_regex_is_unaffected(tmp_path):
    """DiceFrame 自己写的 Python regex 必须照常执行（不回退成不执行）。"""

    store = _store(tmp_path)
    try:
        store.create_lorebook({"id": "native", "name": "Native"})
        store.add_entry({
            "id": "n1", "book_id": "native", "name": "N", "content": "c",
            "keywords": [r"guard-\d+"], "use_regex": True,
        })
        stored = store.list_book_entries("native")[0]
        assert stored["regex_executable"] is True, "canonical 默认必须可执行"
        assert [r["id"] for r in _matcher(store, "native").match("guard-42")]
    finally:
        store.close()


def test_regex_executable_survives_export_and_reimport(tmp_path):
    """导出再导入后，不兼容的 regex 仍然不执行（不能靠这一跳洗白）。"""

    store = _store(tmp_path)
    try:
        draft = preview_lorebook_import(_st_payload(MISMATCH))["book"]
        commit_lorebook_import(store, draft, None, book_id="b")
        exported = export_lorebook_v3(store, "b")
        raw = exported["data"]["lorebook"]["entries"][0]
        assert raw["extensions"]["diceframe"]["regex_executable"] is False

        again = preview_lorebook_import(exported)["book"]
        assert again.entries[0].regex_executable is False
        commit_lorebook_import(store, again, None, book_id="b2")
        assert store.list_book_entries("b2")[0]["regex_executable"] is False
        assert _matcher(store, "b2").match("the harbor is quiet") == []
    finally:
        store.close()


# ---- §5 lorebook_v3 的 DiceFrame-only 字段 ---------------------------------

LEGACY_RICH = {
    "name": "Rich", "content": "body",
    "keywords": ["alpha"], "secondary_keys": ["beta"],
    "match_mode": "all", "type": "npc", "tier": "core",
    "unreliable": True, "sync_on_enter": True,
    "visible_to": ["gm", "p1"], "connected_to": ["other-entry"],
    "triggers_recursive": ["child-entry"],
}

DICEFRAME_ONLY = (
    "type", "tier", "unreliable", "sync_on_enter", "visible_to",
    "connected_to", "triggers_recursive", "match_mode",
)


def test_diceframe_only_fields_live_under_extensions_diceframe(tmp_path):
    """新 exporter 不再把 DiceFrame 私有字段当标准顶层字段扩张。"""

    store = _store(tmp_path)
    try:
        store.create_lorebook({"id": "b", "name": "B"})
        store.add_entry({"id": "e1", "book_id": "b", **LEGACY_RICH})
        raw = export_lorebook_v3(store, "b")["data"]["lorebook"]["entries"][0]

        assert "match_mode" not in raw, "match_mode 是 DiceFrame 私有字段，不得占据标准顶层"
        private = raw["extensions"]["diceframe"]
        for field in DICEFRAME_ONLY:
            assert field in private, f"{field} 未进入 extensions.diceframe"
        assert private["match_mode"] == "all"
        assert private["visible_to"] == ["gm", "p1"]
        assert private["triggers_recursive"] == ["child-entry"]
        # 标准可表达字段仍然在标准顶层。
        assert raw["keys"] == ["alpha"] and raw["secondary_keys"] == ["beta"]
    finally:
        store.close()


def test_legacy_rich_roundtrip_keeps_diceframe_compatibility_semantics(tmp_path):
    store = _store(tmp_path)
    try:
        store.create_lorebook({"id": "b", "name": "B"})
        store.add_entry({"id": "e1", "book_id": "b", **LEGACY_RICH})
        before = store.list_book_entries("b")[0]

        exported = export_lorebook_v3(store, "b")
        draft = preview_lorebook_import(exported)["book"]
        commit_lorebook_import(store, draft, None, book_id="b2")
        after = store.list_book_entries("b2")[0]

        mismatched = {
            field: (before.get(field), after.get(field))
            for field in DICEFRAME_ONLY
            if before.get(field) != after.get(field)
        }
        assert mismatched == {}, f"round trip 丢了 DiceFrame compatibility semantics: {mismatched}"
    finally:
        store.close()


def test_old_top_level_match_mode_is_still_read(tmp_path):
    """旧 exporter 产生的顶层 match_mode 必须继续被读取。"""

    store = _store(tmp_path)
    try:
        payload = {
            "spec": "lorebook_v3",
            "data": {"lorebook": {"name": "Old", "entries": [
                {"id": "e1", "keys": ["a"], "content": "c", "match_mode": "all"},
            ]}},
        }
        draft = preview_lorebook_import(payload)["book"]
        assert draft.entries[0].match_mode == "all"
        commit_lorebook_import(store, draft, None, book_id="b")
        assert store.list_book_entries("b")[0]["match_mode"] == "all"
    finally:
        store.close()


def test_standard_top_level_wins_over_the_private_bucket(tmp_path):
    """tolerant read 的优先级：标准顶层优先，其次 extensions.diceframe。"""

    payload = {
        "spec": "lorebook_v3",
        "data": {"lorebook": {"name": "T", "entries": [{
            "id": "e1", "keys": ["a"], "content": "c",
            "match_mode": "all",
            "extensions": {"diceframe": {"match_mode": "not_any", "tier": "core"}},
        }]}},
    }
    entry = preview_lorebook_import(payload)["book"].entries[0]
    assert entry.match_mode == "all", "显式顶层值应优先"
    assert entry.tier == "core", "顶层没有时回落到 extensions.diceframe"
