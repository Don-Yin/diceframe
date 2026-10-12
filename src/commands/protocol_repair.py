"""One-shot repair for model replies that expose malformed state protocol."""

from __future__ import annotations

import logging
from typing import Any

from src.engine.language import localized_text
from src.llm.parser import has_malformed_protocol_leak


logger = logging.getLogger("trpg")


def append_protocol_repair_instruction(context: str, language: str) -> str:
    instruction = localized_text(language, {
        "en": (
            "Your previous response exposed a state tag in the narration or omitted the `---` separator. "
            "Rewrite the complete response once. Keep player-facing narration before `---`; put plain-text, "
            "uppercase state tags only after `---`, one per line. Do not use Markdown around tags or put tags "
            "on the same line as narration."
        ),
        "zh-CN": (
            "上一条回复把状态标签写进了正文，或遗漏了 `---` 分隔符。请完整重写一次：玩家可见正文放在 "
            "`---` 前；纯文本大写状态标签只能放在 `---` 后，每行一个；标签不得加 Markdown，也不得与正文同一行。"
        ),
        "ja": (
            "前回の応答で本文中に状態タグを露出したか、`---` 区切りを欠落させていました。回答全体を一度だけ書き直してください："
            "プレイヤー向けの本文は `---` の前に置き、プレーンテキストの大文字状態タグは `---` の後ろにのみ1行1つ置いてください。"
            "タグにMarkdownを使わず、本文と同じ行にも置かないでください。"
        ),
        "de": (
            "Deine vorherige Antwort hat einen Status-Tag im Fließtext offengelegt oder den `---`-Trenner "
            "ausgelassen. Schreibe die vollständige Antwort einmal neu: Spielersichtbarer Text steht vor "
            "`---`; reine, großgeschriebene Status-Tags stehen nur nach `---`, einer pro Zeile. Keine "
            "Markdown-Formatierung um Tags, und Tags nicht in derselben Zeile wie der Fließtext."
        ),
    })
    return f"{context}\n\n⚠️ {instruction}"


async def repair_malformed_protocol_response(
    llm_client: Any,
    response: Any,
    *,
    system_prompt: str,
    user_message: str,
    language: str,
    temperature: float,
    max_tokens: int,
) -> Any:
    """Retry once only when a tag-shaped leak is present without a safe separator."""
    if not has_malformed_protocol_leak(str(getattr(response, "content", "") or "")):
        return response
    logger.warning("检测到模型协议标签泄漏，按严格格式重试一次")
    repaired = await llm_client.call(
        system_prompt=system_prompt,
        user_message=append_protocol_repair_instruction(user_message, language),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    repaired.total_tokens = int(getattr(response, "total_tokens", 0) or 0) + int(
        getattr(repaired, "total_tokens", 0) or 0
    )
    return repaired
