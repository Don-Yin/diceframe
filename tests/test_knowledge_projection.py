"""knowledge 领域纯函数测试：可见性判定与视角投影。"""

from __future__ import annotations

import pytest

from src.knowledge.projection import Viewer, project_entries
from src.knowledge.visibility import (
    classify_audience,
    entry_visible_to_viewer,
    visibility_values,
)


def _entry(entry_id: str, visible_to: object) -> dict:
    return {"id": entry_id, "name": f"条目{entry_id}", "visible_to": visible_to}


class TestVisibilityValues:
    def test_list_shape(self) -> None:
        assert visibility_values([" 莱拉 ", "", "布兰"]) == ["莱拉", "布兰"]

    def test_json_string_shape(self) -> None:
        assert visibility_values('["a", "b"]') == ["a", "b"]

    def test_comma_string_shape(self) -> None:
        assert visibility_values("莱拉, 布兰") == ["莱拉", "布兰"]

    def test_missing_or_invalid_shapes(self) -> None:
        assert visibility_values(None) == []
        assert visibility_values("") == []
        assert visibility_values("   ") == []
        assert visibility_values(42) == []
        assert visibility_values({"a": 1}) == []


class TestClassifyAudience:
    def test_public_marker(self) -> None:
        for marker in ("public", "*", "全体玩家", "公开"):
            assert classify_audience(_entry("a", [marker])) == "public"

    def test_public_marker_mixed_with_names(self) -> None:
        assert classify_audience(_entry("a", ["莱拉", "party"])) == "public"

    def test_character_only(self) -> None:
        assert classify_audience(_entry("a", ["莱拉"])) == "character"

    @pytest.mark.parametrize("visible_to", [None, [], "", "   ", 42])
    def test_empty_is_gm_secret(self, visible_to: object) -> None:
        assert classify_audience(_entry("a", visible_to)) == "gm"

    def test_non_dict_entry_is_gm(self) -> None:
        assert classify_audience("not-an-entry") == "gm"


class TestEntryVisibleToViewer:
    def test_gm_sees_everything(self) -> None:
        assert entry_visible_to_viewer(_entry("a", []), "gm")
        assert entry_visible_to_viewer(_entry("a", ["莱拉"]), "gm")
        assert entry_visible_to_viewer("not-a-dict", "gm")

    def test_party_only_sees_public_markers(self) -> None:
        assert entry_visible_to_viewer(_entry("a", ["public"]), "party")
        assert entry_visible_to_viewer(_entry("a", ["所有人"]), "party")
        assert not entry_visible_to_viewer(_entry("a", ["莱拉"]), "party")
        assert not entry_visible_to_viewer(_entry("a", []), "party")

    def test_character_matches_uid(self) -> None:
        assert entry_visible_to_viewer(_entry("a", ["u1"]), "character", uid="u1")

    def test_character_matches_name(self) -> None:
        assert entry_visible_to_viewer(_entry("a", ["莱拉"]), "character", uid="u1", name="莱拉")

    def test_character_match_is_casefolded(self) -> None:
        assert entry_visible_to_viewer(_entry("a", ["Layla"]), "character", uid="u1", name="layla")

    def test_character_also_sees_public(self) -> None:
        assert entry_visible_to_viewer(_entry("a", ["公开"]), "character", uid="u1", name="莱拉")

    def test_character_fail_closed(self) -> None:
        assert not entry_visible_to_viewer(_entry("a", []), "character", uid="u1", name="莱拉")
        assert not entry_visible_to_viewer(_entry("a", ["布兰"]), "character", uid="u1", name="莱拉")

    def test_unknown_viewer_is_never_visible(self) -> None:
        assert not entry_visible_to_viewer(_entry("a", ["public"]), "alien")


class TestProjectEntries:
    @pytest.fixture()
    def entries(self) -> list[dict]:
        return [
            _entry("a", ["public"]),
            _entry("b", "莱拉, 布兰"),
            _entry("c", []),
            _entry("d", '["u2"]'),
        ]

    def test_gm_projection(self, entries: list[dict]) -> None:
        result = project_entries(entries, Viewer("gm"))
        assert set(result) == {"a", "b", "c", "d"}
        assert all(p["visible"] for p in result.values())
        assert result["a"]["audience"] == "public"
        assert result["b"]["audience"] == "character"
        assert result["c"]["audience"] == "gm"

    def test_party_projection(self, entries: list[dict]) -> None:
        result = project_entries(entries, Viewer("party"))
        assert [k for k, p in result.items() if p["visible"]] == ["a"]

    def test_character_projection(self, entries: list[dict]) -> None:
        result = project_entries(entries, Viewer("character", "u1", "莱拉"))
        visible = {k for k, p in result.items() if p["visible"]}
        assert visible == {"a", "b"}

    def test_subjects_drop_public_markers_keep_order(self, entries: list[dict]) -> None:
        result = project_entries(entries, Viewer("gm"))
        assert result["a"]["subjects"] == []
        assert result["b"]["subjects"] == ["莱拉", "布兰"]

    def test_entries_without_id_are_skipped(self) -> None:
        entries = [{"visible_to": ["public"]}, _entry("a", ["public"]), "junk"]
        result = project_entries(entries, Viewer("gm"))
        assert set(result) == {"a"}
