"""Architecture content-layout contracts.

这里保留的是“布局/权威”类契约（不是内部实现锁）：

- V2 产品规则不得重新引入整份 `_en/_ja` 复制式本地化文件。
- 冒险包保持独立安装目录，不被复制进 ruleset 包；且 ruleset 运行时
  能真实发现并加载已安装冒险（行为验证，替代旧的源码 import 字符串断言）。
- 规则 locale 由后端 materialize：客户端按语言请求得到最终文本，
  而不是拿到带 `_en` 后缀的双份字段自行拼装。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_product_rules_have_no_full_locale_copies() -> None:
    """V2 不新增后缀全文复制式本地化；历史样本只留在 fixtures。"""
    product_rules = ROOT / "templates" / "rules"
    legacy_copies = []
    for path in (*product_rules.glob("*_en.json"), *product_rules.glob("*_ja.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not data.get("abstract"):
            legacy_copies.append(path)
    assert not legacy_copies
    fixtures = ROOT / "tests" / "fixtures" / "legacy_rules"
    assert list(fixtures.glob("*_en.json"))


def test_dnd_adventures_stay_outside_ruleset_packages() -> None:
    ruleset = ROOT / "templates" / "rulesets" / "dnd2024_srd"
    assert not list((ruleset / "presets" / "adventures").glob("*.json"))
    assert not list(ruleset.rglob("*lanterns_of_greymoor*"))
    assert (ROOT / "templates" / "adventures" / "lanterns_of_greymoor" / "manifest.json").is_file()


def test_ruleset_runtime_discovers_installed_adventures() -> None:
    """冒险可以由运行时正确发现和加载（行为契约）。"""
    from src.adventures import ADVENTURE_GRAPH_FORMAT, AdventureBundleLoader

    loader = AdventureBundleLoader(ROOT / "templates" / "adventures")
    bundle = loader.resolve("core:lanterns_of_greymoor")
    assert bundle.manifest.adventure_id == "core:lanterns_of_greymoor"
    assert bundle.manifest.format == ADVENTURE_GRAPH_FORMAT


def test_rule_locale_is_materialized_by_backend() -> None:
    """客户端按语言请求规则时，后端返回 materialize 后的最终文本。

    返回值不得要求前端再用 `*_en` 后缀字段自行拼装显示内容。
    """
    import tempfile

    from src.rules.loader import RuleBundleLoader

    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = Path(tmp)
        (rules_dir / "demo.json").write_text(
            json.dumps({
                "rule_id": "demo",
                "rule_schema_version": 2,
                "rule_name": "演示规则",
                "description": "中文描述",
                "dice_system": "d20",
                "attributes": [{"key": "str", "name": "力量"}],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        en_dir = rules_dir / "locales" / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "demo.json").write_text(
            json.dumps({
                "locale_schema_version": 1,
                "locale": "en",
                "target": {"kind": "rule", "id": "demo"},
                "rule": {"rule_name": "Demo Rules"},
                "fields": {"description": "English description"},
            }, ensure_ascii=False),
            encoding="utf-8",
        )

        loader = RuleBundleLoader()
        zh = loader.load_rule(rules_dir, "demo", "")
        en = loader.load_rule(rules_dir, "demo", "en")

        assert zh["rule_name"] == "演示规则"
        assert en["rule_name"] == "Demo Rules"
        assert en["description"] == "English description"
        # locale 不改 mechanics：核心结构保持一致
        assert en["dice_system"] == zh["dice_system"] == "d20"
        assert en["attributes"][0]["key"] == "str"
        # materialize 后不应出现 *_en 双份后缀字段
        assert not [key for key in en if key.endswith("_en")]
