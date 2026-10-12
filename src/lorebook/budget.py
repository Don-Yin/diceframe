"""Lorebook 预算与排序。

两级预算，单位各自跟随自己的配置字段：

    per-book ``token_budget``  → 估算 token（``CHARS_PER_TOKEN`` 字符 ≈ 1 token）
    overall lore budget        → 字符，由 ``llm.context_builder.lore_char_budget``
                                 派生并由调用方传入

overall 预算的数值**不在这里推导**：provider context-window 的唯一 authority 在
``llm.context_builder``，这里只负责按给定预算裁剪，避免出现第二套窗口口径。
（lorebook 也不能 import context_builder —— 那条链经 engine 会成环。）
"""

from __future__ import annotations
from typing import Any, Callable

# ``apply_token_budget`` 默认估算口径：4 字符 ≈ 1 token。
CHARS_PER_TOKEN = 4


def estimate_entry_tokens(entry: dict[str, Any]) -> int:
    return max(1, len(str(entry.get("content", ""))) // CHARS_PER_TOKEN)


def estimate_entry_chars(entry: dict[str, Any]) -> int:
    return max(1, len(str(entry.get("content", ""))))


def max_entries_within_budget(
    entries: list[dict[str, Any]], budget: int | None,
    *, estimate: Callable[[dict[str, Any]], int] | None = None,
) -> int | None:
    """预算最多可能容纳多少个条目（按最便宜的排，故为上界）。

    用来给 recursion 一个 deterministic 的 candidate 上限：超过这个数量的激活无论
    如何都进不了最终预算，因此可以不再展开，而不是「先无限展开、最后才裁」。
    返回 ``None`` 表示没有预算约束。
    """

    if budget is None or budget <= 0:
        return None
    estimate = estimate or estimate_entry_chars
    used, count = 0, 0
    for cost in sorted(estimate(entry) for entry in entries):
        if used + cost > budget:
            break
        used += cost
        count += 1
    return count


def entry_sort_key(entry: dict[str, Any], *, recursive: bool = False, semantic_only: bool = False) -> tuple:
    return (0 if entry.get("is_constant") else 1, 0 if entry.get("_direct_match") else 1, -int(entry.get("priority", 0) or 0), int(entry.get("order", 100) or 100), 1 if recursive else 0, 1 if semantic_only else 0, str(entry.get("id", "")))


def annotated_entry_sort_key(entry: dict[str, Any]) -> tuple:
    """``entry_sort_key`` 读取条目自带的 direct / recursive / semantic-only 标注。

    matcher 在 activation 时写下这三个标注，因此预算排序不必再猜条目是怎么进来的。
    """

    return entry_sort_key(
        entry,
        recursive=bool(entry.get("_recursive")),
        semantic_only=bool(entry.get("_semantic_only")),
    )


def apply_token_budget(entries: list[dict[str, Any]], budget: int | None, *, estimate: callable | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    if budget is None or budget <= 0:
        return entries, []
    estimate = estimate or (lambda row: max(1, len(str(row.get("content", ""))) // 4))
    included, omitted, used = [], [], 0
    for entry in sorted(entries, key=annotated_entry_sort_key):
        cost = int(estimate(entry))
        if used + cost <= budget:
            included.append(entry); used += cost
        else:
            omitted.append(str(entry.get("id", "")))
    return included, omitted
