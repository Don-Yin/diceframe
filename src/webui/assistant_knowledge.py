"""DiceFrame 公开文档的轻量检索索引。

优先加载随程序打包的预建索引包（scripts/build_assistant_knowledge.py 生成），
不联网、不解析 markdown，秒检索。预建索引不存在时（开发环境）回退到运行时
解析本地 docs。便携版 / 源码发布包通过预建索引获得文档，无需打包原始 docs。

diceframe-content 仓库是用户文档的唯一来源：运行时后台从其 GitHub raw 拉取
docs/{lang}/*.md（TTL 缓存，失败静默回退内置索引），文档推送后无需发版，
各实例的助手在 TTL 内自动跟进。README 属于主程序仓库，只走内置索引。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("trpg")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_FILE = Path(__file__).parent / "assistant_knowledge_index.json"
_DOCUMENTS = {
    "zh": (
        "README.md",
        "docs/zh/updates.md",
    ),
    "en": (
        "README_EN.md",
        "docs/en/updates.md",
    ),
}

# diceframe-content 仓库 docs/ 下的文档清单（相对 docs/{lang}/），运行时拉取。
_CONTENT_DOC_PATHS = {
    "zh": (
        "guide.md",
        "deploy.md",
        "standalone-webui.md",
        "plugin-development.md",
        "plugin-registry.md",
        "scene-images.md",
        "voice-pack-publishing.md",
        "website.md",
        "bot-bridge-core.md",
    ),
    "en": (
        "guide.md",
        "deploy.md",
        "standalone-webui.md",
        "plugin-development.md",
        "plugin-registry.md",
        "voice-pack-publishing.md",
        "bot-bridge-core.md",
    ),
}
GITHUB_DOCS_BASE_URL = "https://raw.githubusercontent.com/diceframe/diceframe-content/main/docs"
_DOCS_BASE_URLS = tuple(dict.fromkeys(filter(None, (
    os.getenv("DICEFRAME_DOCS_BASE_URL", "").strip().rstrip("/"),
    GITHUB_DOCS_BASE_URL,
))))
_REMOTE_TTL_SECONDS = 3600
_REMOTE_FETCH_TIMEOUT = 8

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
_ASCII_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_.:/+-]*", re.IGNORECASE)
_CJK_RE = re.compile(r"[㐀-鿿]+")
_MAX_CHUNK_CHARS = 3600
_DEFAULT_CONTEXT_CHARS = 6_000


@dataclass(frozen=True)
class DocumentChunk:
    source: str
    heading: str
    text: str
    tokens: Counter[str]
    heading_tokens: frozenset[str]


@dataclass(frozen=True)
class KnowledgeResult:
    context: str
    sources: list[dict[str, str]]


_CACHE: dict[str, tuple[str, tuple[DocumentChunk, ...]]] = {}
_CACHE_LOCK = asyncio.Lock()
# 远程文档索引缓存: lang -> (过期时间戳, chunks 或 None)。None 也缓存，
# 离线时避免每条助手消息都重新撞网络。TTL 过期后下一次查询再试。
_REMOTE_CACHE: dict[str, tuple[float, tuple[DocumentChunk, ...] | None]] = {}


def _language_key(language: str) -> str:
    return "en" if (language or "").lower().startswith("en") else "zh"


def _tokens(text: str) -> list[str]:
    normalized = text.lower()
    result = _ASCII_WORD_RE.findall(normalized)
    for sequence in _CJK_RE.findall(normalized):
        result.append(sequence)
        if len(sequence) > 1:
            result.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return result


def _split_long_text(text: str, limit: int = _MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    paragraphs = re.split(r"\n{2,}", text)
    parts: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if not paragraph:
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
        while len(paragraph) > limit:
            parts.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph
    if current:
        parts.append(current)
    return parts


def _parse_markdown(source: str, text: str) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    headings: list[str] = []
    body: list[str] = []

    def flush() -> None:
        value = "\n".join(body).strip()
        if not value:
            return
        heading = " > ".join(headings) or source
        for part in _split_long_text(value):
            chunks.append(
                DocumentChunk(
                    source=source,
                    heading=heading,
                    text=part,
                    tokens=Counter(_tokens(f"{heading}\n{part}")),
                    heading_tokens=frozenset(_tokens(heading)),
                )
            )

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if not match:
            body.append(line)
            continue
        flush()
        body = []
        level = len(match.group(1))
        title = match.group(2).strip()
        headings = headings[: level - 1]
        headings.append(title)
    flush()
    return chunks


def _load_built_index(lang_key: str) -> tuple[DocumentChunk, ...] | None:
    """加载预建索引包；不存在或损坏返回 None，由调用方回退到运行时解析。"""
    if not INDEX_FILE.exists():
        return None
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    items = data.get(lang_key) if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    chunks: list[DocumentChunk] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        tokens = item.get("tokens")
        heading_tokens = item.get("heading_tokens")
        chunks.append(
            DocumentChunk(
                source=str(item.get("source") or ""),
                heading=str(item.get("heading") or ""),
                text=str(item.get("text") or ""),
                tokens=Counter(tokens if isinstance(tokens, dict) else {}),
                heading_tokens=frozenset(heading_tokens if isinstance(heading_tokens, list) else []),
            )
        )
    return tuple(chunks)


def _build_index_from_local(lang_key: str) -> tuple[DocumentChunk, ...]:
    """兜底：预建索引不存在时（开发环境），运行时解析本地 docs。"""
    chunks: list[DocumentChunk] = []
    for relative in _DOCUMENTS[lang_key]:
        try:
            text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        except OSError:
            continue
        chunks.extend(_parse_markdown(relative, text))
    return tuple(chunks)


def _local_signature(lang_key: str) -> str:
    """本地 docs 内容签名，内容变化才重建索引。"""
    digest = hashlib.sha256()
    for relative in _DOCUMENTS[lang_key]:
        try:
            text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        except OSError:
            text = ""
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _doc_source_name(lang_key: str, path: str) -> str:
    """远程文档在索引里的来源名，与预建索引中 trpg/docs 的相对路径写法一致。"""
    return f"docs/{lang_key}/{path}"


async def _fetch_remote_docs(lang_key: str) -> dict[str, str] | None:
    """从 diceframe-content 仓库拉取 docs/{lang}/*.md；全部失败返回 None。

    单个文件 404（文档被上游删除）不影响其他文件，按实际拉到的集合替换。
    aiohttp 延迟到函数内导入：本模块被 scripts/build_assistant_knowledge.py
    在无依赖的构建环境加载，顶层 import 会让发布打包直接崩（CI 不装 aiohttp）。
    """
    if not _DOCS_BASE_URLS:
        return None
    paths = _CONTENT_DOC_PATHS.get(lang_key) or ()
    if not paths:
        return None
    try:
        import aiohttp
    except ImportError:
        return None

    async def fetch_one(session: aiohttp.ClientSession, base: str, path: str) -> str | None:
        try:
            async with session.get(f"{base}/{lang_key}/{path}") as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()
                return text if text.strip() else None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

    try:
        timeout = aiohttp.ClientTimeout(total=_REMOTE_FETCH_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for base in _DOCS_BASE_URLS:
                results = await asyncio.gather(
                    *(fetch_one(session, base, path) for path in paths)
                )
                texts = {
                    path: text
                    for path, text in zip(paths, results)
                    if text is not None
                }
                if texts:
                    return texts
    except Exception:
        logger.debug("助手远程文档拉取异常", exc_info=True)
    return None


async def _remote_index(lang_key: str) -> tuple[DocumentChunk, ...] | None:
    """带 TTL 缓存的远程文档索引；离线/失败返回 None（用内置索引兜底）。"""
    now = time.monotonic()
    cached = _REMOTE_CACHE.get(lang_key)
    if cached and cached[0] > now:
        return cached[1]
    texts = await _fetch_remote_docs(lang_key)
    chunks: tuple[DocumentChunk, ...] | None = None
    if texts is not None:
        parsed: list[DocumentChunk] = []
        for path, text in texts.items():
            parsed.extend(_parse_markdown(_doc_source_name(lang_key, path), text))
        chunks = tuple(parsed)
        logger.info(
            "助手远程文档已加载 (%s): %d 个文件, %d 个片段",
            lang_key, len(texts), len(chunks),
        )
    _REMOTE_CACHE[lang_key] = (now + _REMOTE_TTL_SECONDS, chunks)
    return chunks


async def _index(language: str) -> tuple[DocumentChunk, ...]:
    lang_key = _language_key(language)
    built = _load_built_index(lang_key)
    if built is not None:
        signature = "built"
    else:
        signature = _local_signature(lang_key)
    cached = _CACHE.get(lang_key)
    if cached and cached[0] == signature:
        base = cached[1]
    else:
        async with _CACHE_LOCK:
            cached = _CACHE.get(lang_key)
            if cached and cached[0] == signature:
                base = cached[1]
            else:
                base = built if built is not None else _build_index_from_local(lang_key)
                _CACHE[lang_key] = (signature, base)
    remote = await _remote_index(lang_key)
    if remote is None:
        return base
    # 远程文档按 source 全量替换内置快照：上游删改即时生效，README 等
    # 主程序自有文档不受影响。
    replaced = {chunk.source for chunk in remote}
    return tuple(chunk for chunk in base if chunk.source not in replaced) + remote


async def prefetch_remote_indexes() -> None:
    """启动时预热远程文档缓存，避免首个助手问题在线等拉取。"""
    await asyncio.gather(
        *(_remote_index(lang_key) for lang_key in ("zh", "en")),
        return_exceptions=True,
    )


def _score(chunk: DocumentChunk, query_tokens: Counter[str], normalized_query: str) -> float:
    score = 0.0
    for token, query_count in query_tokens.items():
        count = chunk.tokens.get(token, 0)
        if not count:
            continue
        score += query_count * (1.0 + math.log1p(count))
        if token in chunk.heading_tokens:
            score += query_count * 3.5
    compact_query = re.sub(r"\s+", "", normalized_query.lower())
    compact_text = re.sub(r"\s+", "", f"{chunk.heading}\n{chunk.text}".lower())
    if len(compact_query) >= 3 and compact_query in compact_text:
        score += 8.0
    return score


async def search_knowledge(
    query: str,
    language: str,
    *,
    limit: int = 4,
    max_chars: int = _DEFAULT_CONTEXT_CHARS,
) -> KnowledgeResult:
    query_tokens = Counter(_tokens(query))
    if not query_tokens:
        return KnowledgeResult(context="", sources=[])
    scored = [
        (_score(chunk, query_tokens, query), chunk)
        for chunk in await _index(language)
    ]
    scored = [(score, chunk) for score, chunk in scored if score >= 2.0]
    scored.sort(key=lambda item: (-item[0], item[1].source, item[1].heading))

    selected: list[DocumentChunk] = []
    seen: set[tuple[str, str]] = set()
    used_chars = 0
    for _, chunk in scored:
        identity = (chunk.source, chunk.heading)
        if identity in seen:
            continue
        rendered = f"[来源: {chunk.source} > {chunk.heading}]\n{chunk.text}"
        if selected and used_chars + len(rendered) > max_chars:
            continue
        if not selected and len(rendered) > max_chars:
            rendered = rendered[:max_chars]
            chunk = DocumentChunk(
                source=chunk.source,
                heading=chunk.heading,
                text=rendered.split("\n", 1)[-1],
                tokens=chunk.tokens,
                heading_tokens=chunk.heading_tokens,
            )
        selected.append(chunk)
        seen.add(identity)
        used_chars += len(rendered)
        if len(selected) >= limit:
            break

    context_parts = [
        f"[来源: {chunk.source} > {chunk.heading}]\n{chunk.text}"
        for chunk in selected
    ]
    sources = [{"source": chunk.source, "heading": chunk.heading} for chunk in selected]
    return KnowledgeResult(context="\n\n".join(context_parts), sources=sources)
