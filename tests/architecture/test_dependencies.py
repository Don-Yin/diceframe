"""Architecture dependency boundaries (AST-level).

这些测试保护的是架构契约本身（模块依赖方向），而不是内部实现写法：

- engine / generation / lorebook / memory / rules 是核心域，不得依赖
  legacy compat 适配层、webui、或具体 ruleset 实现。
- rulesets 运行时层不得依赖 webui / compat。
- dnd2024 combat 是纯战斗计算，不得依赖 campaign / UI 层。
- adventures 加载器独立，不得依赖具体 ruleset / webui / compat。
- web_transport 只是 TLS/传输配置，不得反向依赖业务域。
- 游戏/规则业务层不得感知 HTTP/HTTPS 与证书（web_transport）。

检查方式：解析每个模块的 import 语句（含函数内延迟导入与相对导入），
而不是对源码做字符串匹配——重命名、注释、文档措辞变化不应触发失败，
真实的依赖方向变化必须触发失败。
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def _dotted_module(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(path: Path) -> set[str]:
    """Return every dotted module path imported by this file.

    Relative imports are resolved against the file's package, so both
    `from src.webui import x` and `from ..webui import x` are caught.
    """
    # utf-8-sig 透明去掉 BOM（部分文件带头部 BOM，ast.parse 会拒绝）。
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    package = _dotted_module(path.parent).split(".")
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                parts = [*base, node.module] if node.module else base
                name = ".".join(parts)
            else:
                name = node.module or ""
            if not name:
                continue
            modules.add(name)
            for alias in node.names:
                # `from src import webui` must count as importing src.webui.
                modules.add(f"{name}.{alias.name}")
    return modules


def _depends_on(module: str, forbidden: str) -> bool:
    return module == forbidden or module.startswith(forbidden + ".")


def _assert_boundary(
    directories: tuple[str, ...],
    forbidden: tuple[str, ...],
    *,
    skip_files: tuple[str, ...] = (),
) -> None:
    violations: list[str] = []
    for name in directories:
        for path in sorted((SRC / name).rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            if relative in skip_files:
                continue
            for module in sorted(_imported_modules(path)):
                for banned in forbidden:
                    if _depends_on(module, banned):
                        violations.append(
                            f"{path.relative_to(ROOT)} imports {module} (forbidden: {banned})"
                        )
    assert not violations, "\n".join(violations)


def test_core_domains_do_not_depend_on_compat_adapters_webui_or_rulesets() -> None:
    """核心域保持独立：不依赖 legacy compat 适配器、webui 与具体 ruleset。

    src/rules/loader.py 是显式声明的 V1/V2 适配边界，允许接触 compat。
    """
    _assert_boundary(
        ("engine", "generation", "lorebook", "memory", "rules"),
        (
            "src.compat.rules_v1",
            "src.compat.content_v1",
            "src.compat.worlds_v1",
            "src.webui",
            "src.rulesets.dnd2024",
        ),
        skip_files=("src/rules/loader.py",),
    )


def test_ruleset_runtime_layer_does_not_depend_on_webui_or_compat() -> None:
    _assert_boundary(("rulesets",), ("src.webui", "src.compat"))


def test_dnd_combat_does_not_depend_on_campaign_or_ui_layers() -> None:
    _assert_boundary(
        ("rulesets/dnd2024/combat",),
        ("src.rulesets.dnd2024.campaign", "src.webui"),
    )


def test_standalone_adventure_loader_has_no_dnd_webui_or_compat_dependency() -> None:
    _assert_boundary(
        ("adventures",),
        ("src.rulesets.dnd2024", "src.webui", "src.compat"),
    )


def test_web_transport_has_no_business_or_webui_dependency() -> None:
    """TLS 只是 Web Transport 配置，业务层与 Web 层不得被其反向依赖。"""
    _assert_boundary(
        ("web_transport",),
        ("src.webui", "src.rules", "src.rulesets", "src.engine", "src.generation"),
    )


def test_game_layers_do_not_depend_on_web_transport() -> None:
    """游戏/规则/AI 等业务模块不得感知 HTTP/HTTPS 与证书。"""
    _assert_boundary(
        ("engine", "generation", "lorebook", "memory", "rules", "rulesets", "adventures"),
        ("src.web_transport",),
    )
