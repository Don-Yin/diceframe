"""已配对设备的独立 owner 凭据。

为什么不是「扫码换回访问密码」：访问密码在 STATE 里是 PBKDF2 哈希，服务端
自己也不知道明文，换不出来。更重要的是即便能换，把主密码分发到每台手机上
也是错的——一台设备丢失就只能整体改密码，其它设备跟着全掉线。

所以配对成功签发的是设备令牌：
- 与访问密码平级的 owner 凭据，同样走 ``Authorization: Bearer``；
- 高熵随机串，落盘只存 sha256 摘要（随机 token 不需要 KDF，而且它要在每个
  请求上验证，慢哈希会直接变成每请求成本）；
- 可逐台吊销，吊销后该设备立即失去 owner 权限，不影响其它设备与主密码。
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web


logger = logging.getLogger("trpg")

MAX_DEVICES = 64
MAX_LABEL_CHARS = 40
# last_seen 每个请求都会变；按秒落盘会把设备清单写成热点文件，这里做节流。
LAST_SEEN_FLUSH_SECONDS = 60


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _digest(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def sanitize_label(value: object) -> str:
    text = " ".join(str(value or "").split())[:MAX_LABEL_CHARS]
    return text


class InstallIdInUse(ValueError):
    """Another paired device is already bound to this install id."""


def normalize_install_id(value: object) -> str:
    """A client install id (canonical id) or ``""``; never a guess."""
    from src.engine.world.contracts import CANONICAL_ID_PATTERN

    text = value if isinstance(value, str) else ""
    return text if CANONICAL_ID_PATTERN.fullmatch(text) else ""


class DeviceTokenStore:
    """已配对设备清单；令牌只以摘要形式落盘，明文只在签发响应里出现一次。"""

    def __init__(self, data_dir: Path, max_devices: int = MAX_DEVICES) -> None:
        self.path = Path(data_dir) / "paired_devices.json"
        self.max_devices = max(1, int(max_devices))
        self._devices: list[dict] = self._load()
        self._last_flush = 0.0

    # ---- 查询 ----

    def entries(self) -> list[dict]:
        """给设置页用的清单；不含任何可用于鉴权的字段。"""
        return [
            {
                "id": device["id"],
                "label": device["label"],
                "created_at": device["created_at"],
                "last_seen_at": device["last_seen_at"],
                "install_id": device.get("install_id", ""),
            }
            for device in sorted(
                self._devices,
                key=lambda item: item["created_at"],
                reverse=True,
            )
        ]

    def verify(self, token: str) -> dict | None:
        """校验 Bearer 是否为有效设备令牌；命中时顺带记录活跃时间。"""
        candidate = str(token or "").strip()
        if not candidate:
            return None
        digest = _digest(candidate)
        for device in self._devices:
            if secrets.compare_digest(device["digest"], digest):
                self._touch(device)
                return device
        return None

    # ---- 变更 ----

    def issue(self, label: str = "", install_id: str = "") -> tuple[str, dict]:
        if self.install_id_holder(install_id):
            raise InstallIdInUse(install_id)
        token = secrets.token_urlsafe(32)
        device = {
            "id": secrets.token_hex(8),
            "label": sanitize_label(label),
            "digest": _digest(token),
            "created_at": _now_iso(),
            "last_seen_at": "",
            "install_id": normalize_install_id(install_id),
        }
        self._devices.append(device)
        # 超额时淘汰最久未活跃的设备，避免清单被无限撑大。
        while len(self._devices) > self.max_devices:
            self._devices.remove(
                min(
                    self._devices,
                    key=lambda item: item["last_seen_at"] or item["created_at"],
                )
            )
        self._save()
        return token, device

    # ---- 内容同步身份 ----

    def bind_install_id(self, device_id: str, install_id: str) -> str:
        """Return the install id this device is bound to, binding it on first use.

        A device paired before install ids existed has none; its first
        declared content push binds the id it declares. Afterwards the device
        may only declare that id. Returns ``""`` for an unknown device.
        """
        target = str(device_id or "").strip()
        wanted = normalize_install_id(install_id)
        for device in self._devices:
            if device["id"] != target:
                continue
            if not device.get("install_id") and wanted:
                if self.install_id_holder(wanted, excluding=target):
                    raise InstallIdInUse(wanted)
                device["install_id"] = wanted
                self._save()
            return str(device.get("install_id") or "")
        return ""

    def install_id_holder(self, install_id: str, *, excluding: str = "") -> str:
        """The paired device already bound to ``install_id`` (``""`` if none)."""
        wanted = normalize_install_id(install_id)
        if not wanted:
            return ""
        for device in self._devices:
            if device["id"] != excluding and device.get("install_id") == wanted:
                return str(device["id"])
        return ""

    def clear_install_id(self, device_id: str) -> bool:
        """Owner action: let the device bind a new install id (e.g. after a reinstall)."""
        target = str(device_id or "").strip()
        for device in self._devices:
            if device["id"] == target:
                device["install_id"] = ""
                self._save()
                return True
        return False

    def revoke(self, device_id: str) -> bool:
        target = str(device_id or "").strip()
        remaining = [device for device in self._devices if device["id"] != target]
        if len(remaining) == len(self._devices):
            return False
        self._devices = remaining
        self._save()
        return True

    def revoke_all(self) -> int:
        count = len(self._devices)
        self._devices = []
        self._save()
        return count

    # ---- 持久化 ----

    def _touch(self, device: dict) -> None:
        device["last_seen_at"] = _now_iso()
        now = time.monotonic()
        if now - self._last_flush < LAST_SEEN_FLUSH_SECONDS:
            return
        self._last_flush = now
        self._save()

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            with self.path.open(encoding="utf-8") as file:
                payload = json.load(file)
            raw = payload.get("devices", []) if isinstance(payload, dict) else []
            if not isinstance(raw, list):
                raise ValueError("devices is not a list")
        except (OSError, ValueError, json.JSONDecodeError, KeyError):
            # 清单损坏时按「无已配对设备」继续：宁可让用户重新配对，
            # 也不能把无法解析的内容当成有效凭据放行。
            logger.warning("已配对设备清单损坏，按空清单继续", exc_info=True)
            return []
        devices: list[dict] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            digest = str(entry.get("digest") or "")
            if len(digest) != 64:
                continue
            devices.append(
                {
                    "id": str(entry.get("id") or secrets.token_hex(8)),
                    "label": sanitize_label(entry.get("label")),
                    "digest": digest,
                    "created_at": str(entry.get("created_at") or ""),
                    "last_seen_at": str(entry.get("last_seen_at") or ""),
                    "install_id": normalize_install_id(entry.get("install_id")),
                }
            )
        return devices[-self.max_devices:]

    def _save(self) -> None:
        payload = json.dumps({"devices": self._devices}, ensure_ascii=False, indent=2)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            logger.exception("已配对设备清单写入失败")


DEVICE_TOKENS_KEY = web.AppKey("device_tokens", DeviceTokenStore)
