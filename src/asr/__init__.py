"""Speech-to-text provider abstraction used by DiceFrame's WebUI."""

from .contracts import (
    MAX_TRANSCRIPTION_AUDIO_BYTES,
    SUPPORTED_ASR_PROVIDER_IDS,
    TranscriptionRequest,
    TranscriptionResult,
)
from .providers import AsrProviderError, OpenAICompatibleAsrProvider
from .service import AsrService, AsrServiceError

__all__ = [
    "MAX_TRANSCRIPTION_AUDIO_BYTES",
    "SUPPORTED_ASR_PROVIDER_IDS",
    "TranscriptionRequest",
    "TranscriptionResult",
    "AsrProviderError",
    "OpenAICompatibleAsrProvider",
    "AsrService",
    "AsrServiceError",
]
