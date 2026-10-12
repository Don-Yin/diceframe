"""语音识别（ASR）领域的稳定契约。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SUPPORTED_ASR_PROVIDER_IDS = frozenset({"disabled", "openai-compatible"})

MAX_TRANSCRIPTION_AUDIO_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class TranscriptionRequest:
    audio: bytes
    content_type: str = "audio/webm"
    language: str = ""


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    provider: str = ""
    model: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {"text": self.text, "provider": self.provider, "model": self.model}
