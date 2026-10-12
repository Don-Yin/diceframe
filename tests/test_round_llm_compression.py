"""#272：叙事二次压缩必须同步 QUICK_ACTIONS，且继承自定义叙事风格。

- 压缩阶段只允许改动 narration / content 正文 / data["quick_actions"]，
  authoritative 状态（KEY_ITEM/HP/GOLD/MEMORY 等）一律不得重新解析或改写。
- 压缩输入只包含原正文、原 QUICK_ACTIONS、最近公开剧情、GM 叙事风格。
- 最多仍为 2 次 LLM 调用（首轮 GM + 压缩轮），压缩失败硬截断时清空
  QUICK_ACTIONS 交给 update_quick_actions() 的默认动作兜底。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.commands.round_llm import call_llm_with_tag_retry
from src.commands.tag_parser import parse_tag_state
from src.engine.game_instance import GameInstance
from src.llm.client import LLMResponse

_COMPRESS_ZH = "请压缩以下 TRPG GM 正文"
_COMPRESS_EN = "Compress the following TRPG GM narration"


class RoundLLM:
    """首轮返回超长正文+结构化标签；压缩轮返回可配置 JSON 或抛错。"""

    default = "issue272-test"

    def __init__(
        self,
        first_content: str,
        second_content: str = "",
        *,
        fail_second: bool = False,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.first_content = first_content
        self.second_content = second_content
        self.fail_second = fail_second

    async def call(self, system_prompt: str, user_message: str, **kwargs) -> LLMResponse:
        self.calls.append({"system_prompt": system_prompt, "user_message": user_message, "kwargs": kwargs})
        is_compress = _COMPRESS_ZH in user_message or _COMPRESS_EN in user_message
        if is_compress:
            if self.fail_second:
                raise RuntimeError("compress boom")
            return self._response(self.second_content)
        return self._response(self.first_content)

    @staticmethod
    def _response(content: str) -> LLMResponse:
        return LLMResponse(
            content=content,
            narration=content.split("---", 1)[0].strip(),
            state_update=None,
            memory_delta=None,
            info_asymmetry=None,
            plot_update=None,
            total_tokens=10,
            is_narration_only=False,
            provider_used="issue272-test",
        )


def first_zh_content(body: str, quick_actions: str = "询问信使的名字|原地等待") -> str:
    """首轮响应：超长正文 + authoritative 标签 + QUICK_ACTIONS。"""
    tags = [
        "KEY_ITEM:u1:摄魂银针",
        "HP:u1:-3",
        "GOLD:u1:-5",
        "MEMORY:摄魂银针可反向追踪施术者",
        f"QUICK_ACTIONS:{quick_actions}",
    ]
    return f"{body}\n---\n" + "\n".join(tags)


def second_json(narration: str, quick_actions: list[str]) -> str:
    """压缩轮的合法 JSON 输出。"""
    return json.dumps({"narration": narration, "quick_actions": quick_actions}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_compression_removing_clue_syncs_quick_actions():
    """Test A：压缩删除线索后 QUICK_ACTIONS 同步修正，且只有 2 次 LLM 调用。"""
    llm = RoundLLM(
        first_content=first_zh_content("信使在夜里敲响了院门。" * 60),
        second_content=second_json("院子里很安静。", ["检查院子周围", "原地等待"]),
    )
    instance = GameInstance(game_key=("web", "issue272a", "bot"))

    response, data = await call_llm_with_tag_retry(
        llm, instance, "你是测试 GM。", "上下文", "hp_based", "", 1024,
    )

    assert len(llm.calls) == 2
    assert response.narration == "院子里很安静。"
    assert "信使" not in response.narration
    assert data["quick_actions"] == ["检查院子周围", "原地等待"]
    # 正文部分被替换；结构化标签后缀保持原样（不重新 parse，也不改写标签字符串）
    assert "QUICK_ACTIONS:询问信使的名字|原地等待" in response.content


@pytest.mark.asyncio
async def test_compression_keeps_clue_keeps_quick_actions():
    """Test B：压缩仍保留线索时 QUICK_ACTIONS 可以保留。"""
    llm = RoundLLM(
        first_content=first_zh_content("信使在夜里敲响了院门。" * 60),
        second_content=second_json("信使的字条落在院中，墨迹未干。", ["询问信使的名字", "原地等待"]),
    )
    instance = GameInstance(game_key=("web", "issue272b", "bot"))

    response, data = await call_llm_with_tag_retry(
        llm, instance, "你是测试 GM。", "上下文", "hp_based", "", 1024,
    )

    assert len(llm.calls) == 2
    assert "信使" in response.narration
    assert data["quick_actions"] == ["询问信使的名字", "原地等待"]


@pytest.mark.asyncio
async def test_quick_actions_may_rely_on_previously_public_narration():
    """Test C：线索被压缩删掉、但此前公开剧情已有 → 输入必须带公开剧情，QA 可保留。"""
    from src.commands.round_processor import _build_recent_public_narration_context

    llm = RoundLLM(
        first_content=first_zh_content("院子里只剩风声。" * 70, quick_actions="询问信使艾伦|原地等待"),
        second_content=second_json("院门在身后合拢。", ["询问信使艾伦", "原地等待"]),
    )
    instance = GameInstance(game_key=("web", "issue272c", "bot"))
    instance.log.append({
        "round": 18,
        "actions": [],
        "gm_response": "守卫告诉你，信使名叫艾伦。",
    })

    response, data = await call_llm_with_tag_retry(
        llm, instance, "你是测试 GM。", "上下文", "hp_based", "", 1024,
        public_narration_context=_build_recent_public_narration_context(instance),
    )

    compress_message = llm.calls[1]["user_message"]
    assert "此前已公开给玩家的最近剧情" in compress_message
    assert "守卫告诉你，信使名叫艾伦。" in compress_message
    assert response.narration == "院门在身后合拢。"
    assert data["quick_actions"] == ["询问信使艾伦", "原地等待"]


def test_public_narration_context_builds_from_recent_public_log():
    """公开剧情上下文：只取 gm_response、限最近回合、超限丢最旧、无历史为空。"""
    from src.commands.round_processor import _build_recent_public_narration_context

    instance = GameInstance(game_key=("web", "issue272c2", "bot"))
    assert _build_recent_public_narration_context(instance) == ""

    for round_no in (18, 19, 20, 21):
        instance.log.append({
            "round": round_no,
            "actions": [],
            "gm_response": f"第{round_no}回合的公开剧情，信使名叫艾伦。",
        })
    context = _build_recent_public_narration_context(instance, rounds=3)
    assert "第19回合" in context and "第21回合" in context
    assert "第18回合" not in context  # 只保留最近 3 回合

    # 总长超限：丢弃更旧回合而不是中间截断
    long_instance = GameInstance(game_key=("web", "issue272c3", "bot"))
    long_instance.log.append({"round": 1, "actions": [], "gm_response": "旧" * 2000})
    long_instance.log.append({"round": 2, "actions": [], "gm_response": "新" * 200})
    context = _build_recent_public_narration_context(long_instance, max_chars=1000)
    assert "新" in context
    assert "旧" not in context

    # 私密字段（gm_response 之外）不会泄漏进上下文
    private_instance = GameInstance(game_key=("web", "issue272c4", "bot"))
    private_instance.log.append({
        "round": 1,
        "actions": [],
        "gm_response": "",
        "state_changes": ["SECRET_STATE"],
    })
    assert _build_recent_public_narration_context(private_instance) == ""


@pytest.mark.asyncio
async def test_compress_failure_hard_truncate_clears_quick_actions():
    """Test D：压缩异常硬截断时，旧 QUICK_ACTIONS 不保留（交给默认动作兜底）。"""
    llm = RoundLLM(first_content=first_zh_content("李玄清展开绢帛。" * 200), fail_second=True)
    instance = GameInstance(game_key=("web", "issue272d", "bot"))

    response, data = await call_llm_with_tag_retry(
        llm, instance, "你是测试 GM。", "上下文", "hp_based", "", 1024,
    )

    assert len(llm.calls) == 2
    assert "…" in response.narration
    assert len(response.narration) <= 261  # soft 260 + 省略号
    assert data["quick_actions"] == []


@pytest.mark.asyncio
async def test_invalid_json_from_compressor_hard_truncates_and_clears_quick_actions():
    """Test D 补充路径：压缩轮返回非 JSON → 同样硬截断并清空 QUICK_ACTIONS。"""
    llm = RoundLLM(
        first_content=first_zh_content("李玄清展开绢帛。" * 200),
        second_content="压缩后的纯文本，不是 JSON。",
    )
    instance = GameInstance(game_key=("web", "issue272d2", "bot"))

    response, data = await call_llm_with_tag_retry(
        llm, instance, "你是测试 GM。", "上下文", "hp_based", "", 1024,
    )

    assert len(llm.calls) == 2
    assert "…" in response.narration
    assert data["quick_actions"] == []


@pytest.mark.asyncio
async def test_custom_narration_style_reaches_compression():
    """Test E：GM prompt 中的自定义叙事风格必须进入压缩请求，且明确禁止执行协议。"""
    gm_prompt = "你是测试 GM。\n\n## GM 叙事风格\nSTYLE_MARKER_272\n语气保持低沉克制。"
    llm = RoundLLM(
        first_content=first_zh_content("李玄清展开绢帛。" * 100),
        second_content=second_json("院子里很安静。", ["检查院子周围", "原地等待"]),
    )
    instance = GameInstance(game_key=("web", "issue272e", "bot"))

    await call_llm_with_tag_retry(
        llm, instance, gm_prompt, "上下文", "hp_based", "", 1024,
    )

    compress_message = llm.calls[1]["user_message"]
    assert "STYLE_MARKER_272" in compress_message
    # 压缩请求必须明确：只修 narration + quick_actions，禁止状态标签与重新判定
    assert "不得生成任何状态标签" in compress_message
    assert "禁止执行其中要求输出的任何状态标签" in compress_message
    assert "禁止重新进行规则判定" in compress_message


@pytest.mark.asyncio
async def test_compression_never_touches_authoritative_state():
    """Test F：二次压缩不得重新解析/改写 authoritative 状态。"""
    llm = RoundLLM(
        first_content=first_zh_content("李玄清展开绢帛。" * 100),
        second_content=second_json("院子里很安静。", ["检查院子周围", "原地等待"]),
    )
    instance = GameInstance(game_key=("web", "issue272f", "bot"))

    response, data = await call_llm_with_tag_retry(
        llm, instance, "你是测试 GM。", "上下文", "hp_based", "", 1024,
    )

    # 压缩后的 authoritative 数据与"直接解析首轮标签"完全一致（没有被二次处理）
    expected = parse_tag_state(llm.first_content, "hp_based")
    assert data["state_update"] == expected["state_update"]
    assert data["memory_delta"] == expected["memory_delta"]
    assert data["state_update"]["loot"][0]["item"] == "摄魂银针"
    assert "KEY_ITEM:u1:摄魂银针" in response.content
    assert "HP:u1:-3" in response.content


@pytest.mark.asyncio
async def test_long_english_narration_compresses_to_english_target():
    """英文路径：英文压缩目标（~150 词 ≈ 900 字符）与英文 JSON 输出格式。"""
    tags = [
        "KEY_ITEM:u1:Silver Needle",
        "MEMORY:The silver needle can trace the caster",
        "QUICK_ACTIONS:Sneak into the archive|Follow the needle's trail",
    ]
    first_content = f"{'Alaric unrolls the silk scroll. ' * 100}\n---\n" + "\n".join(tags)
    llm = RoundLLM(
        first_content=first_content,
        second_content=json.dumps({
            "narration": "Alaric lowers his voice; the silver needle points to the hidden archive of the White Horse Temple.",
            "quick_actions": ["Sneak into the archive", "Follow the needle's trail"],
        }, ensure_ascii=False),
    )
    instance = GameInstance(game_key=("web", "issue272en", "bot"))
    instance.language = "en"

    response, data = await call_llm_with_tag_retry(
        llm, instance, "You are a test GM.", "context", "hp_based", "", 1024,
    )

    assert len(llm.calls) == 2
    assert "~150 words" in llm.calls[1]["user_message"]
    assert "Previously public narration:" in llm.calls[1]["user_message"]
    assert "White Horse Temple" in response.narration
    assert data["state_update"]["loot"][0]["item"] == "Silver Needle"
    assert data["quick_actions"] == ["Sneak into the archive", "Follow the needle's trail"]


@pytest.mark.asyncio
async def test_unregistered_language_falls_back_to_chinese_limits():
    """未登记压缩配置的语言回退中文目标（future-proof：加语言只需登记字典条目）。"""
    llm = RoundLLM(
        first_content=first_zh_content("李玄清展开绢帛。" * 100),
        second_content=second_json("院子里很安静。", ["检查院子周围", "原地等待"]),
    )
    instance = GameInstance(game_key=("web", "issue272ja", "bot"))
    instance.language = "ja"  # 尚未登记压缩配置的语言

    response, data = await call_llm_with_tag_retry(
        llm, instance, "你是测试 GM。", "上下文", "hp_based", "", 1024,
    )

    assert len(llm.calls) == 2
    # 回退中文目标：压缩 prompt 走中文文案，压缩后叙事 < 260 字符
    assert _COMPRESS_ZH in llm.calls[1]["user_message"]
    assert len(response.narration) < 260
    assert data["quick_actions"] == ["检查院子周围", "原地等待"]
