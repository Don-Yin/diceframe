"""开发者公告拉取：复用公共内容服务的网络访问、磁盘缓存、单飞与失败退避。

公告不再维护独立的网络下载器；主机限制、大小限制、单飞、失败退避和磁盘缓存
全部由 `content.py` 经显式公共内容回调提供。本模块只保留
中英文文件选择、公告散列、短命中缓存和“缓存内容”标记。
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger("trpg")

ANNOUNCEMENT_DIR = "announcements"
_SUCCESS_TTL = 600
_STALE_TTL = 86_400

_CACHE: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class AnnouncementDependencies:
    fetch_public_text: Callable[[str], Awaitable[str]]
    disk_cache_age: Callable[[str], float | None]


def _file_for_language(language: str) -> str:
    return "zh.md" if (language or "").lower().startswith("zh") else "en.md"


def _payload(cached: dict[str, Any], *, stale: bool = False) -> dict[str, Any]:
    return {"content": cached["content"], "hash": cached["hash"], "fetched": True, "stale": stale}


def _stale_payload(key: str, now: float) -> dict[str, Any] | None:
    cached = _CACHE.get(key)
    if cached and now - float(cached["fetched_at"]) <= _STALE_TTL:
        return _payload(cached, stale=True)
    return None


async def fetch_official_announcement(
    dependencies: AnnouncementDependencies,
    language: str,
) -> dict[str, Any]:
    """返回公告正文与散列；成功在线获取后 content.py 会更新磁盘缓存。

    失败时返回陈旧缓存并标记 stale；从未成功且离线时返回空公告，不弹错误死循环。
    """
    key = _file_for_language(language)
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and now - float(cached["fetched_at"]) < _SUCCESS_TTL:
        return _payload(cached)

    path = f"{ANNOUNCEMENT_DIR}/{key}"
    try:
        text = await dependencies.fetch_public_text(path)
    except Exception:
        logger.exception("公告内容拉取异常")
        text = ""

    now = time.monotonic()
    if text:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        _CACHE[key] = {"content": text, "hash": digest, "fetched_at": now}
        return _payload(
            _CACHE[key], stale=_is_cached_served(dependencies, path, text),
        )

    return _stale_payload(key, now) or _empty()


def _is_cached_served(
    dependencies: AnnouncementDependencies, path: str, text: str,
) -> bool:
    """判断返回正文是否来自 content.py 的磁盘缓存（例如重启后断网场景）。"""
    if not text:
        return False
    age = dependencies.disk_cache_age(path)
    if age is None:
        return False
    return age > _SUCCESS_TTL


def _empty() -> dict[str, Any]:
    return {"content": "", "hash": "", "fetched": False, "stale": False}


class AnnouncementService:
    """Official announcement retrieval over the public-content boundary."""

    def __init__(self, dependencies: AnnouncementDependencies) -> None:
        self._dependencies = dependencies

    async def fetch(self, language: str) -> dict[str, Any]:
        return await fetch_official_announcement(self._dependencies, language)
