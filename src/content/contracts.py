"""Stable identity and resource contracts for Content V2."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any

_ID = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")


def canonical_id(value: str) -> str:
    result = str(value or "").strip().lower().replace(" ", "_")
    if not _ID.fullmatch(result):
        raise ValueError(f"invalid canonical id: {value!r}")
    return result


def asset_local_id(value: str) -> str:
    """资产文件名 → 合法 canonical id（自动规范化，不做命名强制）。

    资产是被**路径**引用的叶子资源（``scene_image.path`` 等按原样解析），
    文件名由作者随意起：哈希、原名、中文都应能安装。已经合法的名字原样
    保留（存量身份不漂移）；非法的名字沿用历史清洗规则（非法字符转
    ``_``、小写、去首尾 ``_``）后做最小修复：空名回退 ``asset``，非字母
    开头加 ``n`` 前缀，并追加原名的短哈希后缀，避免不同文件规范化后互相
    覆盖。
    """
    raw = str(value or "").strip()
    try:
        return canonical_id(raw)
    except ValueError:
        pass
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", raw).lower().strip("_") or "asset"
    if not re.match(r"^[a-z]", cleaned):
        cleaned = f"n{cleaned}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[:87]}-{digest}"


@dataclass(frozen=True)
class ResourceRef:
    owner: str
    kind: str
    local_id: str

    def __post_init__(self) -> None:
        if not str(self.owner).strip() or not str(self.kind).strip():
            raise ValueError("resource owner and kind are required")
        object.__setattr__(self, "owner", str(self.owner).strip())
        object.__setattr__(self, "kind", canonical_id(self.kind))
        object.__setattr__(self, "local_id", canonical_id(self.local_id))

    def __str__(self) -> str:
        return f"{self.owner}:{self.kind}:{self.local_id}"

    @classmethod
    def parse(cls, value: str) -> "ResourceRef":
        parts = str(value or "").split(":")
        if len(parts) < 3:
            raise ValueError("resource reference must be owner:kind:local_id")
        return cls(":".join(parts[:-2]), parts[-2], parts[-1])


@dataclass(frozen=True)
class ContentResource:
    ref: ResourceRef
    data: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.data, dict):
            raise TypeError("content resource data must be an object")
