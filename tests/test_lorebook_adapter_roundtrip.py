"""§5/§6/§7 — Adapter 与 export/reimport 的语义保真。

施工单要求：

* §5 ``selective`` 与 ``secondary_keys`` 是两个独立概念：``selective=false``
  保留 keys 但不参与 gate；``selective=true`` 才按 ``selective_logic`` 过滤。
* §6 ``lorebook_v3`` 必须导出所有可表达的 runtime semantics，否则
  ``canonical → export → reimport`` 会静默丢行为。
* §7 ST 是 JavaScript regex、DiceFrame 是 Python regex：只有安全子集能执行，
  不兼容的要 preserve + warning，且 runtime 不能 crash。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.lorebook.activation import python_regex_incompatibility
from src.lorebook.exporter import export_lorebook_native, export_lorebook_v3
from src.lorebook.importer import commit_lorebook_import, preview_lorebook_import
from src.lorebook.matcher import KeywordMatcher
from src.lorebook.store import LorebookStore


def _store(tmp_path: Path) -> LorebookStore:
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    return store


def _match(entry: dict, text: str) -> bool:
    """Run one entry through the real matcher (no hand-rolled keyword logic)."""

    matcher = KeywordMatcher()
    matcher.build([{"enabled": True, "probability": 100, "keywords": [], "content": "", **entry}])
    return bool(matcher.match(text))


# ---- §5 CCv3 selective -----------------------------------------------------


def test_ccv3_selective_false_keeps_secondary_keys_but_does_not_gate(tmp_path: Path) -> None:
    """primary 命中 + secondary 不命中 + selective=false → 仍然激活。"""

    payload = {
        "spec": "lorebook_v3",
        "data": {"lorebook": {"entries": [{
            "id": "e1", "keys": ["harbor"], "secondary_keys": ["night"],
            "selective": False, "selective_logic": "and_any", "content": "body",
        }]}},
    }
    draft = preview_lorebook_import(payload)["book"]
    entry = draft.entries[0]
    assert entry.secondary_keys == ["night"], "keys 必须保留为数据"
    assert entry.selective is False

    store = _store(tmp_path)
    try:
        commit_lorebook_import(store, draft, None, book_id="book:ccv3")
        stored = store.list_book_entries("book:ccv3")[0]
        assert stored["secondary_keys"] == ["night"]
        assert stored["selective"] is False
        # secondary 未命中，但 selective=false 所以不该被 gate 拦住。
        assert _match(stored, "the harbor at dawn") is True
    finally:
        store.close()


def test_ccv3_selective_true_blocks_on_secondary_miss(tmp_path: Path) -> None:
    """同一个 fixture 但 selective=true → 被 secondary 拦截。"""

    payload = {
        "spec": "lorebook_v3",
        "data": {"lorebook": {"entries": [{
            "id": "e1", "keys": ["harbor"], "secondary_keys": ["night"],
            "selective": True, "selective_logic": "and_any", "content": "body",
        }]}},
    }
    draft = preview_lorebook_import(payload)["book"]
    assert draft.entries[0].selective is True

    store = _store(tmp_path)
    try:
        commit_lorebook_import(store, draft, None, book_id="book:ccv3")
        stored = store.list_book_entries("book:ccv3")[0]
        assert _match(stored, "the harbor at dawn") is False, "secondary 未命中必须被拦截"
        assert _match(stored, "the harbor at night") is True
    finally:
        store.close()


def test_selective_flag_survives_a_lorebook_v3_round_trip(tmp_path: Path) -> None:
    """selective 必须在 export → reimport 后保持（§5 要求覆盖 roundtrip）。"""

    store = _store(tmp_path)
    try:
        store.create_lorebook({"id": "book:rt", "name": "RT"})
        store.add_entry({
            "id": "e1", "book_id": "book:rt", "name": "E1", "content": "body",
            "keywords": ["harbor"], "secondary_keys": ["night"],
            "selective": False, "selective_logic": "and_any",
        })
        exported = export_lorebook_v3(store, "book:rt")
        raw = exported["data"]["lorebook"]["entries"][0]
        assert raw["selective"] is False
        assert raw["secondary_keys"] == ["night"]

        draft = preview_lorebook_import(exported)["book"]
        assert draft.entries[0].selective is False
        commit_lorebook_import(store, draft, None, book_id="book:rt2")
        assert store.list_book_entries("book:rt2")[0]["selective"] is False
    finally:
        store.close()


def test_selective_defaults_to_enabled_for_legacy_rows(tmp_path: Path) -> None:
    """没有 selective 字段的旧行默认启用 secondary gate，行为不变。"""

    store = _store(tmp_path)
    try:
        store.create_lorebook({"id": "book:legacy", "name": "Legacy"})
        store.add_entry({
            "id": "e1", "book_id": "book:legacy", "name": "E1", "content": "body",
            "keywords": ["harbor"], "secondary_keys": ["night"],
        })
        stored = store.list_book_entries("book:legacy")[0]
        assert stored["selective"] is True
        assert _match(stored, "the harbor at dawn") is False
    finally:
        store.close()


# ---- §6 rich lorebook_v3 round trip ---------------------------------------


#: 每个字段都取一个「与默认值不同」的值，这样丢字段一定会被断言抓到。
RICH_ENTRY = {
    "name": "Rich", "content": "rich body",
    "keywords": ["alpha"], "secondary_keys": ["beta"],
    "enabled": True, "is_constant": False,
    "selective": False, "selective_logic": "not_any", "match_mode": "all",
    "use_regex": False, "case_sensitive": True, "match_whole_words": True,
    "scan_depth": 3, "priority": 77, "order": 42, "probability": 55,
    "groups": ["g1"], "group_weight": 5, "prioritize_inclusion": True,
    "group_scoring": "matched_keys",
    "sticky": 2, "cooldown": 4, "delay": 1,
    "vector_activation": "vector_only", "prompt_slot": "scene_context",
    "non_recursable": True, "prevent_further_recursion": True,
    "delay_until_recursion": True, "recursion_level": 2,
}

#: 运行语义字段 → 允许在 roundtrip 中变化的值（这里为空：全部必须一致）。
SEMANTIC_FIELDS = tuple(RICH_ENTRY)


def test_rich_lorebook_v3_round_trip_preserves_runtime_semantics(tmp_path: Path) -> None:
    """canonical → export lorebook_v3 → reimport → 运行语义一致。"""

    store = _store(tmp_path)
    try:
        store.create_lorebook({"id": "book:rich", "name": "Rich"})
        store.add_entry({"id": "e1", "book_id": "book:rich", **RICH_ENTRY})
        before = store.list_book_entries("book:rich")[0]

        exported = export_lorebook_v3(store, "book:rich")
        draft = preview_lorebook_import(exported)["book"]
        commit_lorebook_import(store, draft, None, book_id="book:rich2")
        after = store.list_book_entries("book:rich2")[0]

        mismatched = {
            field: (before.get(field), after.get(field))
            for field in SEMANTIC_FIELDS
            if before.get(field) != after.get(field)
        }
        assert mismatched == {}, f"lorebook_v3 round trip 丢了运行语义: {mismatched}"
    finally:
        store.close()


def test_lorebook_v3_export_carries_every_documented_field(tmp_path: Path) -> None:
    """导出的 entry 必须显式包含施工单 §6 列出的全部字段。"""

    store = _store(tmp_path)
    try:
        store.create_lorebook({"id": "book:rich", "name": "Rich"})
        store.add_entry({"id": "e1", "book_id": "book:rich", **RICH_ENTRY})
        raw = export_lorebook_v3(store, "book:rich")["data"]["lorebook"]["entries"][0]
        required = {
            "selective", "selective_logic", "use_regex", "case_sensitive",
            "match_whole_words", "scan_depth", "probability", "groups",
            "group_weight", "prioritize_inclusion", "group_scoring",
            "non_recursable", "prevent_further_recursion", "delay_until_recursion",
            "recursion_level", "sticky", "cooldown", "delay", "vector_activation",
            "prompt_slot",
        }
        missing = sorted(required - set(raw))
        assert missing == [], f"lorebook_v3 export 缺少字段: {missing}"
    finally:
        store.close()


def test_native_backup_keeps_settings_entries_bindings_visibility_provenance(tmp_path: Path) -> None:
    """Native backup 继续无损：book settings / entries / bindings / visibility /
    provenance / raw extensions。"""

    store = _store(tmp_path)
    try:
        store.create_lorebook({
            "id": "book:nat", "name": "Nat", "scan_depth": 4, "token_budget": 321,
            "recursive_scanning": True, "settings": {"custom": "keep"},
            "source_kind": "plugin", "source_id": "src-1", "source_version": "2",
            "source_digest": "abc",
        })
        store.bind_lorebook({
            "id": "binding:nat", "book_id": "book:nat", "scope_kind": "world",
            "scope_id": "w", "role": "secondary",
        })
        store.add_entry({
            "id": "e1", "book_id": "book:nat", "name": "E1", "content": "c",
            "visible_to": ["gm"], "extensions": {"plugin": {"x": 1}},
            "provenance": {"kind": "plugin", "id": "src-1"},
        })

        backup = export_lorebook_native(store, "book:nat")
        assert backup["spec"] == "diceframe_lorebook_native"
        book = backup["data"]["book"]
        assert book["scan_depth"] == 4 and book["token_budget"] == 321
        assert book["recursive_scanning"] is True
        assert backup["data"]["settings"] == {"custom": "keep"}
        assert book["source_digest"] == "abc"
        assert [b["id"] for b in backup["data"]["bindings"]] == ["binding:nat"]
        entry = backup["data"]["entries"][0]
        assert entry["visible_to"] == ["gm"]
        assert entry["extensions"] == {"plugin": {"x": 1}}
        assert entry["provenance"] == {"kind": "plugin", "id": "src-1"}
    finally:
        store.close()


# ---- §7 JS vs Python regex compatibility ----------------------------------


@pytest.mark.parametrize("pattern", [r"^harbou?r$", r"(?:a|b)+", r"[A-Z]{2,}", r"harbor|dock"])
def test_compatible_regex_reports_no_incompatibility(pattern: str) -> None:
    assert python_regex_incompatibility(pattern) == ""


@pytest.mark.parametrize(
    "pattern",
    [
        r"(?<name>a)",      # JS named group syntax
        r"\p{Letter}+",     # JS unicode property escape
        r"\k<name>",        # JS named backreference
        r"[a-",             # unterminated class
    ],
)
def test_js_only_or_python_invalid_regex_is_reported_as_unsupported(pattern: str) -> None:
    reason = python_regex_incompatibility(pattern)
    assert "unsupported" in reason


@pytest.mark.parametrize("pattern", [r"^\d{3}$", r"\bsecret\b", r"\w+", r"\s*end"])
def test_js_ascii_class_divergence_is_reported_as_mismatch(pattern: str) -> None:
    """Python 的 \\d/\\w/\\s/\\b 是 Unicode-aware，JS 是 ASCII-only：语义不同要提示。"""

    reason = python_regex_incompatibility(pattern)
    assert "mismatch" in reason


def test_st_preview_warns_and_preserves_js_only_regex() -> None:
    """JS-only / Python-invalid fixture → preview warning，且 raw 原样保留。"""

    payload = {
        "name": "ST regex",
        "entries": [{
            "uid": 1, "key": ["(?<name>harbor)"], "content": "x", "useRegex": True,
        }],
    }
    preview = preview_lorebook_import(payload)
    assert preview["format"] == "sillytavern"
    assert any("unsupported regex" in w for w in preview["warnings"])
    assert preview["counts"]["unsupported"] >= 1
    # raw source 原样保留，不被改写。
    assert preview["book"].entries[0].keys == ["(?<name>harbor)"]


def test_lorebook_v3_preview_warns_on_js_only_regex() -> None:
    payload = {
        "spec": "lorebook_v3",
        "data": {"lorebook": {"entries": [{
            "id": "e1", "keys": [r"\p{Letter}+"], "content": "x", "use_regex": True,
        }]}},
    }
    preview = preview_lorebook_import(payload)
    assert any("unsupported regex" in w for w in preview["warnings"])


def test_incompatible_regex_does_not_crash_the_runtime(tmp_path: Path) -> None:
    """runtime 不 crash：不兼容 pattern 只是永不命中，不影响其它条目。"""

    store = _store(tmp_path)
    try:
        store.create_lorebook({"id": "book:rx", "name": "RX"})
        store.add_entry({
            "id": "bad", "book_id": "book:rx", "name": "Bad", "content": "b",
            "keywords": ["(?<name>harbor)"], "use_regex": True,
        })
        store.add_entry({
            "id": "good", "book_id": "book:rx", "name": "Good", "content": "g",
            "keywords": ["harbor"], "use_regex": True,
        })
        matcher = KeywordMatcher()
        matcher.build(store.list_book_entries("book:rx"))
        hits = {row["id"] for row in matcher.match("the harbor")}
        assert hits == {"good"}, "坏 pattern 不命中，但不能影响好 pattern 或抛异常"
    finally:
        store.close()
