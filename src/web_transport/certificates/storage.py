# -*- coding: utf-8 -*-
"""证书存储：目录布局、原子写入与私钥文件权限。

布局（DATA_DIR 为数据目录）：

    DATA_DIR/certs/
    ├─ self-signed/
    │  ├─ server.crt
    │  ├─ server.key
    │  └─ fingerprint.txt
    ├─ acme/
    │  ├─ account/
    │  │  └─ account.key      # ACME 账户密钥（ES256），复用避免重复注册
    │  ├─ live/
    │  │  └─ <stable-id>/     # 目录名不含原始 identifier（IPv6 冒号不可作路径）
    │  │     ├─ fullchain.pem
    │  │     ├─ privkey.pem
    │  │     └─ metadata.json
    │  └─ state.json
    └─ locks/                  # 多实例续期互斥

镜像与安装包不得内置任何共享私钥；本模块只操作运行期数据目录。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from src.web_transport.certificates.base import CertificateError


class CertificateStore:
    def __init__(self, data_dir: Path) -> None:
        self.certs_dir = data_dir / "certs"
        self.self_signed_dir = self.certs_dir / "self-signed"
        self.acme_dir = self.certs_dir / "acme"
        self.acme_account_dir = self.acme_dir / "account"
        self.acme_live_dir = self.acme_dir / "live"
        self.locks_dir = self.certs_dir / "locks"

    # ---- 自签路径 ----

    @property
    def self_signed_cert_path(self) -> Path:
        return self.self_signed_dir / "server.crt"

    @property
    def self_signed_key_path(self) -> Path:
        return self.self_signed_dir / "server.key"

    @property
    def self_signed_fingerprint_path(self) -> Path:
        return self.self_signed_dir / "fingerprint.txt"

    # ---- ACME 路径 ----

    @property
    def acme_account_key_path(self) -> Path:
        return self.acme_account_dir / "account.key"

    @property
    def acme_state_path(self) -> Path:
        return self.acme_dir / "state.json"

    def acme_live_dir_for(self, stable_id: str) -> Path:
        return self.acme_live_dir / stable_id

    @staticmethod
    def stable_identifier_id(identifier_type: str, identifier: str) -> str:
        """目录使用的稳定 ID：不含原始 identifier（其完整值保存在 metadata）。"""
        digest = hashlib.sha256(f"{identifier_type}:{identifier}".encode("utf-8")).hexdigest()[:16]
        prefix = "dns" if identifier_type == "dns" else "ip"
        return f"{prefix}-{digest}"

    # ---- 布局 ----

    def ensure_layout(self) -> None:
        directories = (
            self.self_signed_dir,
            self.locks_dir,
            self.acme_account_dir,
            self.acme_live_dir,
        )
        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise CertificateError(f"无法创建证书目录 {directory}：{exc}") from exc

    # ---- 写入 ----

    def atomic_write_bytes(self, path: Path, payload: bytes, private: bool = False) -> None:
        """临时文件 + 原子替换写入。private=True 时收紧私钥文件权限。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                if private:
                    _restrict_private_file(tmp_path)
                tmp_path.replace(path)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
        except OSError as exc:
            raise CertificateError(f"写入 {path.name} 失败：{exc}") from exc

    def atomic_write_json(self, path: Path, payload: dict) -> None:
        self.atomic_write_bytes(
            path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        )

    def read_json(self, path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            return {}

    def try_acquire_lock(self, name: str, stale_after_seconds: int = 3600) -> Path | None:
        """通过 O_EXCL 提供跨进程的轻量互斥锁；返回 None 表示已有持有者。"""
        self.ensure_layout()
        lock_path = self.locks_dir / f"{name}.lock"
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                handle.write(str(os.getpid()))
            return lock_path
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > stale_after_seconds:
                    lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        except OSError as exc:
            raise CertificateError(f"创建证书锁失败：{exc}") from exc

    @staticmethod
    def release_lock(lock_path: Path | None) -> None:
        if lock_path is None:
            return
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def _restrict_private_file(path: Path) -> None:
    """私钥权限：POSIX owner-only；Windows 无法可靠 chmod，依赖用户目录 ACL。"""
    if os.name == "posix":
        try:
            os.chmod(path, 0o600)
        except OSError:
            # 权限收紧失败不阻断写入：数据目录本身应已具备访问边界。
            pass
