"""Provider-neutral speech-to-text service."""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse

from .contracts import (
    MAX_TRANSCRIPTION_AUDIO_BYTES,
    SUPPORTED_ASR_PROVIDER_IDS,
    TranscriptionRequest,
    TranscriptionResult,
)
from .providers import AsrProvider, AsrProviderError, OpenAICompatibleAsrProvider, normalize_content_type


class AsrServiceError(RuntimeError):
    pass


class AsrService:
    def __init__(self, config: dict[str, Any], *, proxy_url: str = "") -> None:
        self.provider_id = str(config.get("asr_provider") or "disabled").strip()
        self.base_url = str(config.get("asr_base_url") or "").strip()
        self.api_key = str(config.get("asr_api_key") or "").strip()
        self.model = str(config.get("asr_model") or "whisper-1").strip()
        self.timeout_seconds = float(config.get("asr_timeout_seconds") or 60)
        self.proxy_url = "" if _is_local_endpoint(self.base_url) else proxy_url
        self._validate_config()

    @property
    def backend_enabled(self) -> bool:
        return self.provider_id != "disabled"

    def public_config(self) -> dict[str, Any]:
        return {
            "provider": self.provider_id,
            "backend_enabled": self.backend_enabled,
            "model": self.model,
            "max_audio_bytes": MAX_TRANSCRIPTION_AUDIO_BYTES,
        }

    async def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        if not self.backend_enabled:
            raise AsrServiceError("语音识别引擎未启用")
        if not request.audio:
            raise AsrServiceError("录音内容为空")
        if len(request.audio) > MAX_TRANSCRIPTION_AUDIO_BYTES:
            raise AsrServiceError(f"录音超过 {MAX_TRANSCRIPTION_AUDIO_BYTES // (1024 * 1024)} MB 限制")
        normalized = TranscriptionRequest(
            audio=request.audio,
            content_type=normalize_content_type(request.content_type),
            language=str(request.language or "").strip()[:16],
        )
        try:
            text = await self._provider().transcribe(normalized)
        except AsrProviderError as exc:
            raise AsrServiceError(str(exc)) from exc
        return TranscriptionResult(text=text, provider=self.provider_id, model=self.model)

    def _provider(self) -> AsrProvider:
        kwargs = {
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "proxy_url": self.proxy_url,
        }
        if self.provider_id == "openai-compatible":
            return OpenAICompatibleAsrProvider(**kwargs)
        raise AsrServiceError(f"不支持的 ASR provider：{self.provider_id}")

    def _validate_config(self) -> None:
        if self.provider_id not in SUPPORTED_ASR_PROVIDER_IDS:
            raise ValueError(f"不支持的 ASR provider：{self.provider_id}")
        if self.backend_enabled:
            parsed = urlparse(self.base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError("ASR Base URL 必须是无内嵌凭据的 http(s) 地址")


def _is_local_endpoint(value: str) -> bool:
    hostname = (urlparse(value).hostname or "").strip().lower()
    if hostname in {"localhost", "host.docker.internal"} or hostname.endswith(".local"):
        return True
    try:
        return ipaddress.ip_address(hostname).is_private
    except ValueError:
        return False
