# -*- coding: utf-8 -*-
"""Web Transport 配置解析。

HTTP / HTTPS 只是不同的 Web Transport 配置，不属于业务层概念。
本模块负责 schema、旧配置默认值、环境变量覆盖、canonical identifier
校验和脱敏序列化，不得被游戏、规则、AI 等业务模块引用。
"""

from __future__ import annotations

import ipaddress
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Mapping

logger = logging.getLogger("trpg.web_transport")

# 公开支持的 TLS 模式。
TLS_MODE_OFF = "off"
TLS_MODE_SELF_SIGNED = "self_signed"
TLS_MODE_LETS_ENCRYPT = "lets_encrypt"
PUBLIC_TLS_MODES = (TLS_MODE_OFF, TLS_MODE_SELF_SIGNED, TLS_MODE_LETS_ENCRYPT)

# 当前版本实际可启用的模式。
AVAILABLE_TLS_MODES = (TLS_MODE_OFF, TLS_MODE_SELF_SIGNED, TLS_MODE_LETS_ENCRYPT)

IDENTIFIER_TYPE_DNS = "dns"
IDENTIFIER_TYPE_IP = "ip"
IDENTIFIER_TYPES = (IDENTIFIER_TYPE_DNS, IDENTIFIER_TYPE_IP)

ACME_DIRECTORY_PRODUCTION = "production"
ACME_DIRECTORY_STAGING = "staging"
ACME_DIRECTORIES = (ACME_DIRECTORY_PRODUCTION, ACME_DIRECTORY_STAGING)

# Let's Encrypt 公网 IP 证书强制使用的短期 profile（约 160 小时有效期）。
IP_CERTIFICATE_PROFILE = "shortlived"
DEFAULT_CHALLENGE_PORT = 80

_ENV_TLS_MODE = "TRPG_TLS_MODE"
_ENV_IDENTIFIER_TYPE = "TRPG_TLS_IDENTIFIER_TYPE"
_ENV_IDENTIFIER = "TRPG_TLS_IDENTIFIER"
_ENV_CONTACT_EMAIL = "TRPG_TLS_CONTACT_EMAIL"
_ENV_CHALLENGE_TYPE = "TRPG_TLS_CHALLENGE_TYPE"
_ENV_CERT_FILE = "TRPG_TLS_CERT_FILE"
_ENV_KEY_FILE = "TRPG_TLS_KEY_FILE"
_ENV_ACME_CHALLENGE_PORT = "TRPG_TLS_ACME_CHALLENGE_PORT"


@dataclass
class AcmeSettings:
    """canonical ACME 参数。identifier 只保存规范化后的 canonical 值。"""

    identifier_type: str = IDENTIFIER_TYPE_DNS
    identifier: str = ""
    contact_email: str = ""
    challenge_type: str = "http-01"
    directory: str = ACME_DIRECTORY_PRODUCTION
    certificate_profile: str = ""
    http_challenge_port: int = DEFAULT_CHALLENGE_PORT

    def redacted_view(self) -> dict[str, Any]:
        return {
            "identifier_type": self.identifier_type,
            "identifier": self.identifier,
            "contact_email": self.contact_email,
            "challenge_type": self.challenge_type,
            "directory": self.directory,
            "certificate_profile": self.certificate_profile,
            "http_challenge_port": self.http_challenge_port,
        }


@dataclass
class WebTransportConfig:
    """解析后的 Web Transport 配置。

    只保存 canonical 值；未知子字段在解析时被丢弃，旧版本回滚不会因
    陌生字段崩溃，新版本也不会把展示用文本误存为 identity。
    """

    tls_mode: str = TLS_MODE_OFF
    # 配置来源，用于 UI 说明当前模式来自环境变量还是用户设置。
    tls_mode_source: str = "default"
    acme: AcmeSettings = field(default_factory=AcmeSettings)
    # 阶段 D 预留：外部证书文件。出现非空值时在校验阶段显式拒绝。
    cert_file: str = ""
    key_file: str = ""
    reserved_rejects: list[str] = field(default_factory=list)

    @property
    def scheme(self) -> str:
        return "https" if self.tls_mode != TLS_MODE_OFF else "http"

    def redacted_view(self) -> dict[str, Any]:
        """对外（API / 日志）使用的脱敏视图，不含任何密钥材料或路径内容。"""
        return {
            "tls_mode": self.tls_mode,
            "scheme": self.scheme,
            "tls_mode_source": self.tls_mode_source,
            "lets_encrypt_available": True,
            "acme": self.acme.redacted_view() if self.tls_mode == TLS_MODE_LETS_ENCRYPT else None,
        }


def _clean_mode(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _canonical_identifier(identifier_type: str, raw: str) -> tuple[str, str | None]:
    """规范化 identifier。返回 (canonical, 错误)。"""
    value = str(raw or "").strip()
    if not value:
        return "", "标识不能为空"
    if identifier_type == IDENTIFIER_TYPE_DNS:
        candidate = value.rstrip(".").lower()
        if not candidate or len(candidate) > 253 or "." not in candidate:
            return "", "域名格式不正确（需要完整的 FQDN，例如 game.example.com）"
        if candidate in {"localhost"} or candidate.endswith(".local") or candidate.endswith(".internal"):
            return "", "本地域名不能申请公共证书，请使用公网域名"
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            pass
        else:
            return "", "请使用公网 IP 模式填写 IP 地址"
        return candidate, None
    if identifier_type == IDENTIFIER_TYPE_IP:
        # 用标准 IP 库判断，不维护零散字符串前缀表。
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return "", "IP 地址格式不正确"
        if not address.is_global:
            return "", "必须是真正可路由的公网 IPv4 / IPv6 地址（私网、回环、链路本地等保留地址不可用）"
        return address.compressed, None
    return "", "identifier_type 必须是 dns 或 ip"


def _parse_acme_settings(raw: Mapping[str, Any]) -> tuple[AcmeSettings, list[str]]:
    """解析 acme 子配置。返回 (settings, 解析错误列表)。"""
    settings = AcmeSettings()
    errors: list[str] = []

    identifier_type = _clean_mode(raw.get("identifier_type")) or IDENTIFIER_TYPE_DNS
    if identifier_type not in IDENTIFIER_TYPES:
        errors.append("identifier_type 必须是 dns 或 ip")
        identifier_type = IDENTIFIER_TYPE_DNS
    settings.identifier_type = identifier_type

    canonical, error = _canonical_identifier(identifier_type, str(raw.get("identifier") or ""))
    if error:
        errors.append(error)
    settings.identifier = canonical

    email = str(raw.get("contact_email") or "").strip()
    if email and ("@" not in email or " " in email or len(email) > 254):
        errors.append("联系邮箱格式不正确")
    settings.contact_email = email

    challenge = _clean_mode(raw.get("challenge_type")) or "http-01"
    if challenge != "http-01":
        errors.append("第一版只支持 http-01 验证（DNS-01 将通过独立验证器扩展）")
    settings.challenge_type = challenge

    directory = _clean_mode(raw.get("directory")) or ACME_DIRECTORY_PRODUCTION
    if directory not in ACME_DIRECTORIES:
        errors.append("directory 必须是 production 或 staging")
    settings.directory = directory

    profile = _clean_mode(raw.get("certificate_profile"))
    if identifier_type == IDENTIFIER_TYPE_IP:
        # CA 要求：公网 IP 证书必须使用短期 profile。
        profile = IP_CERTIFICATE_PROFILE
    settings.certificate_profile = profile

    port = raw.get("http_challenge_port", DEFAULT_CHALLENGE_PORT)
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 0
    if not 1 <= port <= 65535:
        errors.append("ACME 验证端口必须在 1-65535 之间")
        port = DEFAULT_CHALLENGE_PORT
    settings.http_challenge_port = port

    return settings, errors


def parse_web_transport(saved: Mapping[str, Any] | None, env: Mapping[str, str] | None = None) -> WebTransportConfig:
    """从保存的配置与环境变量解析 Web Transport 配置。

    环境变量优先级高于保存的配置（与现有 env > saved config 约定一致）。
    无效 tls_mode 不抛异常：记录 warning 并按 off 处理，保证旧配置或
    手工编辑后的 config.json 仍能启动（回滚安全）。acme 字段的解析错误
    收集到 reserved_rejects 由调用方决定是否阻断。
    """
    saved = saved if isinstance(saved, Mapping) else {}
    env = env if env is not None else os.environ

    config = WebTransportConfig()

    config_mode = _clean_mode(saved.get("tls_mode"))
    if config_mode in PUBLIC_TLS_MODES:
        config.tls_mode = config_mode
        config.tls_mode_source = "config"
    elif config_mode:
        logger.warning("web_transport.tls_mode=%r 不是有效值，已按 HTTP 处理", config_mode)

    env_mode = _clean_mode(env.get(_ENV_TLS_MODE))
    if env_mode:
        if env_mode in PUBLIC_TLS_MODES:
            config.tls_mode = env_mode
            config.tls_mode_source = "env"
        else:
            logger.warning("%s=%r 不是有效值，已忽略", _ENV_TLS_MODE, env_mode)

    # ACME 子配置：env 与 saved 合并（env 字段优先），再统一解析。
    if config.tls_mode == TLS_MODE_LETS_ENCRYPT:
        raw_acme = dict(saved.get("acme") or {}) if isinstance(saved.get("acme"), Mapping) else {}
        env_map = (
            (_ENV_IDENTIFIER_TYPE, "identifier_type"),
            (_ENV_IDENTIFIER, "identifier"),
            (_ENV_CONTACT_EMAIL, "contact_email"),
            (_ENV_CHALLENGE_TYPE, "challenge_type"),
            (_ENV_ACME_CHALLENGE_PORT, "http_challenge_port"),
        )
        for env_name, key in env_map:
            env_value = str(env.get(env_name) or "").strip()
            if env_value:
                raw_acme[key] = env_value
        settings, errors = _parse_acme_settings(raw_acme)
        config.acme = settings
        for error in errors:
            config.reserved_rejects.append(error)

    # 阶段 D 预留：外部证书文件。出现即显式拒绝，避免用户误以为已生效。
    for name, attr in ((_ENV_CERT_FILE, "cert_file"), (_ENV_KEY_FILE, "key_file")):
        env_value = str(env.get(name) or "").strip()
        saved_value = str(saved.get(attr) or "").strip()
        value = env_value or saved_value
        if value:
            setattr(config, attr, value)
            config.reserved_rejects.append(name if env_value else f"web_transport.{attr}")

    return config


def validate_activation(config: WebTransportConfig) -> str | None:
    """返回阻止启用该配置的中文错误；None 表示可以启用。"""
    # 阶段 D 预留：外部证书文件。出现即显式拒绝，避免用户误以为已生效。
    if config.cert_file or config.key_file:
        return "自定义证书文件尚未开放（暂不支持 TRPG_TLS_CERT_FILE / TRPG_TLS_KEY_FILE）"
    if config.tls_mode in AVAILABLE_TLS_MODES:
        if config.tls_mode == TLS_MODE_LETS_ENCRYPT:
            for rejection in config.reserved_rejects:
                return f"Let's Encrypt 配置无效：{rejection}"
            if not config.acme.identifier:
                return "Let's Encrypt 需要填写域名或公网 IP"
        return None
    return f"不支持的连接模式：{config.tls_mode or '(空)'}"


def web_transport_config_from_state(state: Mapping[str, Any], env: Mapping[str, str] | None = None) -> WebTransportConfig:
    """从 web_server STATE 中的 web_transport 字段重建配置（用于运行期切换）。"""
    return parse_web_transport(state.get("web_transport") or {}, env)
