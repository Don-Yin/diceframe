"""Schema-upgrade operations must live in src/migrations.

契约：持久化 schema 的升级/重建操作（ALTER/DROP/RENAME、user_version
探测、补列逻辑）只能集中在 ``src/migrations``，防止启动存储层再长出
一次性迁移逻辑。

实现方式：AST 扫描真实出现的字符串字面量与 ``ensure_column`` 调用，
忽略注释与文档措辞——措辞变化不触发失败，真实的迁移代码出现在
migrations 之外必须触发失败。
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
MIGRATIONS = SRC / "migrations"

_FORBIDDEN_SQL_MARKERS = (
    "alter table",
    "drop table",
    "rename to",
    "pragma table_info",
    "pragma user_version",
)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    docstrings: set[int] = set()
    for parent in ast.walk(tree):
        body = getattr(parent, "body", None)
        if not isinstance(body, list) or not body:
            continue
        if not isinstance(parent, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))
    return docstrings


def _string_literals(tree: ast.AST) -> list[str]:
    docstrings = _docstring_nodes(tree)
    literals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                literals.append(node.value)
    return literals


def _called_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.append(func.id)
        elif isinstance(func, ast.Attribute):
            names.append(func.attr)
    return names


def test_persisted_schema_upgrade_operations_stay_in_migrations() -> None:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if MIGRATIONS in path.parents:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for literal in _string_literals(tree):
            lowered = literal.lower()
            for marker in _FORBIDDEN_SQL_MARKERS:
                if marker in lowered:
                    violations.append(f"{path.relative_to(ROOT)} contains {marker!r}")
                    break
        for name in _called_names(tree):
            if name == "ensure_column":
                violations.append(f"{path.relative_to(ROOT)} calls ensure_column()")
    assert not violations, "\n".join(sorted(set(violations)))
