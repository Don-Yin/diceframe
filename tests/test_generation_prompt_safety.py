"""生成 prompt 的安全约束契约：public 授权整段 content，秘密 fail-closed。

这不是 prompt 排版锁——是安全约束测试。约束语句的措辞允许演进，
但四条不变量必须在 zh/en/ja 三语的「条目生成」与「世界生成」prompt
中始终存在（真实捕获发给 LLM 的 system prompt，而非扫描源码常量）：

1. visibility="public" 授权整段 entry content；
2. public 中禁止混入秘密信息（隐藏动机/底牌/线索/GM-only）；
3. 公开+秘密混合时必须拆成独立条目；
4. 任何一句不该让玩家立即知道 → 整条 secret。
"""

from __future__ import annotations

import pytest

from webapi_harness import web_api  # noqa: F401  # pytest fixture

REQUIRED_INVARIANTS = {
    "zh-CN": ["整段 content 的整体授权", "禁止混入", "两个独立条目", "整条就必须是 secret"],
    "en": ["ENTIRE entry content", "Never mix", "two separate entries", "whole entry must be secret"],
    "ja": ["content 全体への許可", "混ぜてはいけない", "2 つの独立したエントリ", "エントリ全体を secret"],
}

LORE_MARKERS = ("世界书编辑", "lorebook editor", "ロアブック編集者")
WORLD_MARKERS = ("starter_lorebook",)


def _prompt_with(markers: tuple[str, ...], prompts: list[str]) -> str:
    for prompt in prompts:
        if any(marker in prompt for marker in markers):
            return prompt
    raise AssertionError(f"未捕获到目标生成 prompt，实际捕获 {len(prompts)} 条")


def _assert_invariants(prompt: str, lang: str) -> None:
    for invariant in REQUIRED_INVARIANTS[lang]:
        assert invariant in prompt, f"{lang} 生成 prompt 缺少安全约束: {invariant}"


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh-CN", "en", "ja"])
async def test_lore_generation_prompt_carries_safety_invariants(web_api, lang):
    api, lorebook, _registry, fake_llm, _worlds_dir = web_api
    lorebook.create_world("template_world", "测试世界", description="prompt 安全契约测试")
    await api.generate_lorebook_entries("template_world", "一座雾港城市与走私集团", language=lang)
    prompts = [c["system_prompt"] for c in fake_llm.calls]
    _assert_invariants(_prompt_with(LORE_MARKERS, prompts), lang)


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh-CN", "en", "ja"])
async def test_world_generation_prompt_carries_safety_invariants(web_api, lang):
    api, _lorebook, _registry, fake_llm, _worlds_dir = web_api
    await api.generate_world("一座被雾笼罩的港口城市", language=lang)
    prompts = [c["system_prompt"] for c in fake_llm.calls]
    _assert_invariants(_prompt_with(WORLD_MARKERS, prompts), lang)
