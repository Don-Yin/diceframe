# -*- coding: utf-8 -*-
"""证书提供器公共接口。

提供器只负责证书的生成、复用与元数据，不启动游戏、不操作 Web Server、
不感知业务层。API 与日志只允许出现 CertificateMetadata 级别的公开信息。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # 避免与 metadata 模块形成循环导入。
    from src.web_transport.certificates.metadata import CertificateMetadata


@dataclass(frozen=True)
class PreparedCertificate:
    """一次可用的证书材料。cert/key 路径只在服务端内部流转。"""

    cert_path: Path
    key_path: Path
    metadata: "CertificateMetadata"


@runtime_checkable
class CertificateProvider(Protocol):
    def prepare(self) -> PreparedCertificate:
        """确保证书可用（懒生成或复用），失败抛出带有中文说明的异常。"""
        ...

    def metadata(self) -> "CertificateMetadata | None":
        """当前已存在证书的元数据；不存在时返回 None，不触发生成。"""
        ...


class CertificateError(RuntimeError):
    """证书生成 / 读取失败。message 面向用户，可直接返回给 API。"""
