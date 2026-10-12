"""内置世界模板的可见性结构契约（语义分级由审计完成，这里只做结构性护栏）。

- visible_to 必须是合法的非空字符串列表；模板条目只允许两种形态：
  []（GM 秘密）或 canonical 公开标记 ["*"]。
- 条目必备 id/name/keywords/content，公开条目不得使用非 canonical 标记。
- 模板不允许全量回滚成 GM-only：整体公开条目数必须保住公共常识量。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "worlds"


def _template_files() -> list[Path]:
    return sorted(p for p in TEMPLATES_DIR.glob("*.json"))


def test_template_visibility_contract() -> None:
    files = _template_files()
    assert files, "未找到内置世界模板"
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("starter_lorebook") or []
        ids = [e.get("id") for e in entries]
        assert len(ids) == len(set(ids)), f"{path.name} 条目 id 重复"
        for entry in entries:
            where = f"{path.name}:{entry.get('id')}"
            for field in ("id", "name", "content"):
                assert entry.get(field), f"{where} 缺少 {field}"
            visible_to = entry.get("visible_to", [])
            assert isinstance(visible_to, list), where
            assert all(isinstance(v, str) and v.strip() for v in visible_to), where
            if visible_to:
                assert visible_to == ["*"], (
                    f"{where} 公开条目必须使用 canonical 标记 [\"*\"]，"
                    f"实际为 {visible_to}"
                )


def test_templates_keep_common_knowledge_public() -> None:
    """防全量回滚护栏：模板必须保留足够的公开常识供玩家视角与共享提问使用。"""
    public_total = 0
    for path in _template_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        for entry in data.get("starter_lorebook") or []:
            if entry.get("visible_to") == ["*"]:
                public_total += 1
    assert public_total >= 30, f"模板公开条目仅剩 {public_total} 条，疑似被全量回滚"


@pytest.mark.parametrize(
    "filename", ["coc_horror.json", "coc_horror_en.json", "scifi_cyberpunk.json", "scifi_cyberpunk_en.json"]
)
def test_suspicious_worlds_keep_secrets(filename: str) -> None:
    """含剧情底牌的世界必须保留 GM 秘密条目（防把秘密也整批公开）。"""
    data = json.loads((TEMPLATES_DIR / filename).read_text(encoding="utf-8"))
    secrets = [e for e in data.get("starter_lorebook") or [] if not e.get("visible_to")]
    assert secrets, f"{filename} 的全部条目都是公开的，剧情底牌会直接暴露"
