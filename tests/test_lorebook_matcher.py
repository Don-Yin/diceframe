"""KeywordMatcher 高级匹配测试 —— 概率/分组/NOT/正则。"""

from __future__ import annotations

from src.lorebook.matcher import KeywordMatcher


def _build_matcher(entries: list[dict], *, rng=None) -> KeywordMatcher:
    # Weighted group picks must be deterministic, so tests inject the RNG
    # instead of relying on the process-global random source.
    m = KeywordMatcher(rng=rng)
    # 补充默认字段
    defaults = {
        "id": "", "name": "", "keywords": [], "content": "", "type": "other",
        "sticky": 0, "cooldown": 0, "delay": 0, "order": 100,
        "tier": "background", "is_constant": 0, "match_mode": "any",
        "triggers_recursive": [], "probability": 100, "group": "",
        "group_weight": 1,
    }
    completed = []
    for i, e in enumerate(entries):
        entry = dict(defaults)
        if "id" not in e:
            entry["id"] = f"entry_{i}"
        entry.update(e)
        completed.append(entry)
    m.build(completed)
    return m


class TestRegexKeywords:
    def test_regex_basic(self):
        m = _build_matcher([
            {"id": "e1", "name": "dragon", "keywords": ["/龙.*族/"], "content": "c"},
        ])
        r = m.match("龙人族出现了")
        assert len(r) >= 1
        assert r[0]["id"] == "e1"

    def test_regex_no_match(self):
        m = _build_matcher([
            {"id": "e1", "name": "dragon", "keywords": ["/^龙.*族$/"], "content": "c"},
        ])
        r = m.match("这是一条小龙")
        assert len([e for e in r if e["id"] == "e1"]) == 0

    def test_regex_fallback_plain(self):
        m = _build_matcher([
            {"id": "e1", "name": "normal", "keywords": ["普通关键词"], "content": "c"},
        ])
        r = m.match("包含普通关键词的文字")
        assert len(r) >= 1


class TestNotLogic:
    def test_not_any_exclude(self):
        m = _build_matcher([
            {"id": "e1", "name": "safe", "keywords": ["安全区"],
             "match_mode": "not_any", "content": "安全"},
        ])
        r = m.match("走进安全区")
        assert len([e for e in r if e["id"] == "e1"]) == 0

    def test_not_any_include(self):
        m = _build_matcher([
            {"id": "e1", "name": "danger", "keywords": ["安全区"],
             "match_mode": "not_any", "content": "危险"},
        ])
        r = m.match("走进危险地带")
        assert len([e for e in r if e["id"] == "e1"]) >= 1

    def test_not_all_exclude(self):
        m = _build_matcher([
            {"id": "e1", "name": "hidden", "keywords": ["龙", "火"],
             "match_mode": "not_all", "content": "秘密"},
        ])
        r = m.match("龙喷出了火焰")
        assert len([e for e in r if e["id"] == "e1"]) == 0

    def test_not_all_partial(self):
        m = _build_matcher([
            {"id": "e1", "name": "partial", "keywords": ["龙", "火"],
             "match_mode": "not_all", "content": "部分匹配"},
        ])
        r = m.match("龙出现了")
        assert len([e for e in r if e["id"] == "e1"]) >= 1


class TestGroupCompetition:
    def test_group_winner_only(self):
        m = _build_matcher([
            {"id": "e1", "name": "weak", "keywords": ["怪物"], "group": "encounter",
             "group_weight": 1},
            {"id": "e2", "name": "strong", "keywords": ["怪物"], "group": "encounter",
             "group_weight": 10},
        ], rng=lambda: 0.99)
        r = m.match("遇到了怪物")
        ids = [e["id"] for e in r]
        assert "e2" in ids
        assert "e1" not in ids

    def test_different_groups_coexist(self):
        m = _build_matcher([
            {"id": "e1", "name": "a", "keywords": ["测试"], "group": "g1",
             "group_weight": 1},
            {"id": "e2", "name": "b", "keywords": ["测试"], "group": "g2",
             "group_weight": 1},
        ])
        r = m.match("测试")
        ids = [e["id"] for e in r]
        assert "e1" in ids and "e2" in ids

    def test_prioritized_winner_is_retained_even_when_not_first(self):
        m = _build_matcher([
            {"id": "weighted", "keywords": ["怪物"], "group": "encounter",
             "group_weight": 10},
            {"id": "prioritized", "keywords": ["怪物"], "group": "encounter",
             "group_weight": 1, "prioritize_inclusion": True},
        ])
        ids = {e["id"] for e in m.match("遇到了怪物")}
        assert ids == {"prioritized"}


def test_recursive_scanning_false_does_not_scan_first_match_content():
    m = _build_matcher([
        {"id": "seed", "keywords": ["door"], "content": "sigil",
         "_lorebook_recursive_scanning": False},
        {"id": "child", "keywords": ["sigil"], "content": "deep"},
    ])
    assert {e["id"] for e in m.match_with_recursive("door")} == {"seed"}


def test_non_recursable_direct_match_can_still_propagate():
    m = _build_matcher([
        {"id": "seed", "keywords": ["door"], "content": "sigil",
         "non_recursable": True},
        {"id": "child", "keywords": ["sigil"], "content": "deep"},
    ])
    assert {e["id"] for e in m.match_with_recursive("door")} == {"seed", "child"}


def test_prevent_further_recursion_stops_propagation():
    m = _build_matcher([
        {"id": "seed", "keywords": ["door"], "content": "sigil",
         "prevent_further_recursion": True},
        {"id": "child", "keywords": ["sigil"], "content": "deep"},
    ])
    assert {e["id"] for e in m.match_with_recursive("door")} == {"seed"}


def test_timed_effects_arm_cooldown_behind_sticky_and_never_write_delay():
    """一次激活只启动 sticky；cooldown 只被 arm，delay 完全不落计数器。

    这个测试此前断言 sticky / cooldown / delay 在首次激活时同时被写入——那正是
    缺陷本身：下一轮 cooldown_remaining > 0 会把本该继续生效的 sticky 条目挡掉。
    """

    m = _build_matcher([{
        "id": "timed", "keywords": ["door"], "content": "",
        "sticky": 3, "cooldown": 2, "delay": 1,
    }])
    timed_state = {}
    m.match_with_recursive("door", timed_state=timed_state)
    assert timed_state == {
        "timed": {
            "sticky_remaining": 3,
            "pending_cooldown": 2,
            "activated_tick": 0,
        }
    }
