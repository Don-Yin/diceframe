"""Host-level access password and Bot token lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import hmac
import json
import logging
from pathlib import Path
import secrets

from src.webui.access_password import (
    consume_reset_password,
    hash_access_password,
    is_hashed_access_password,
    is_valid_access_password,
    normalize_access_password,
    verify_access_password,
)


class HostCredentials:
    def __init__(
        self,
        *,
        state: dict,
        data_dir: Path,
        access_token_file: Path,
        environ: Mapping[str, str],
        save_config: Callable[[], None],
        logger: logging.Logger | None = None,
    ) -> None:
        self.state = state
        self.data_dir = data_dir
        self.access_token_file = access_token_file
        self.environ = environ
        self.save_config = save_config
        self.logger = logger or logging.getLogger("trpg")

    def legacy_plugin_bot_token(self) -> str:
        legacy_file = self.data_dir / "plugins" / "qq-napcat" / "secrets.json"
        if not legacy_file.exists():
            return ""
        try:
            data = json.loads(legacy_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            self.logger.warning("读取旧 QQ 插件 Bot Token 失败", exc_info=True)
            return ""
        return str(data.get("bot_token") or "").strip() if isinstance(data, dict) else ""

    def ensure_bot_token(self) -> str:
        current = str(self.state.get("bot_token") or "").strip()
        if current:
            return current
        current = self.legacy_plugin_bot_token() or secrets.token_urlsafe(32)
        self.state["bot_token"] = current
        self.save_config()
        self.logger.info("已生成全局 Bot API Token；可在设置 → Bot API 中复制")
        return current

    def initialize_access_password(self) -> None:
        reset_password = consume_reset_password(self.data_dir)
        configured_env_password = normalize_access_password(
            self.environ.get("TRPG_ACCESS_TOKEN")
        )
        stored_password = normalize_access_password(self.state.get("access_token"))
        self.state["access_token"] = stored_password
        if reset_password:
            self.state["access_token"] = hash_access_password(reset_password)
            self.save_config()
            self.delete_access_token_file()
            self.logger.warning(
                "访问密码已通过 data/reset_access_password.txt 重置，重置文件已删除。"
            )
        elif not is_valid_access_password(stored_password):
            if stored_password:
                self.logger.warning(
                    "保存的访问密码凭证无效，将重新生成首次启动密码。"
                )
            self.generate_initial_access_password()
        elif not is_hashed_access_password(stored_password) and not configured_env_password:
            self.state["access_token"] = hash_access_password(stored_password)
            self.save_config()
            password_file_value = self.read_access_token_file()
            if password_file_value and not hmac.compare_digest(
                password_file_value, stored_password
            ):
                self.delete_access_token_file()
                self.logger.warning(
                    "data/access_token.txt 与现有密码不一致，已删除过期文件。"
                )
            self.logger.info("已将旧版明文访问密码迁移为安全凭证。")
        elif configured_env_password:
            self.logger.info("使用环境变量 TRPG_ACCESS_TOKEN 配置的访问密码。")
        else:
            password_file_value = self.read_access_token_file()
            if password_file_value and not verify_access_password(
                password_file_value, stored_password
            ):
                self.delete_access_token_file()
                password_file_value = ""
                self.logger.warning(
                    "data/access_token.txt 与现有密码不一致，已删除过期文件。"
                )
            if password_file_value:
                self.logger.info(
                    "已加载访问密码；首次启动密码仍可在 data/access_token.txt 查看。"
                )
            else:
                self.logger.info(
                    "已加载访问密码安全凭证；忘记密码请使用 "
                    "data/reset_access_password.txt 重置。"
                )

    def write_access_token_file(self, password: str) -> None:
        temporary = self.access_token_file.with_suffix(
            self.access_token_file.suffix + ".tmp"
        )
        temporary.write_text(password + "\n", encoding="utf-8")
        temporary.replace(self.access_token_file)

    def delete_access_token_file(self) -> None:
        self.access_token_file.unlink(missing_ok=True)

    def read_access_token_file(self) -> str:
        try:
            return normalize_access_password(
                self.access_token_file.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError):
            return ""

    def generate_initial_access_password(self) -> None:
        generated_password = secrets.token_urlsafe(18)
        self.state["access_token"] = hash_access_password(generated_password)
        self.save_config()
        self.write_access_token_file(generated_password)
        print("\n" + "=" * 60, flush=True)
        print("  Initial access password: " + generated_password, flush=True)
        print("  Frontend will prompt for this on open.", flush=True)
        print("  It is also saved once to data/access_token.txt.", flush=True)
        print(
            "  If forgotten later: create data/reset_access_password.txt and restart.",
            flush=True,
        )
        print("=" * 60 + "\n", flush=True)
