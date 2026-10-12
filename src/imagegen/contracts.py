"""Stable contracts for DiceFrame image generation."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


IMAGE_PURPOSES = frozenset({"scene", "avatar", "item", "map", "freeform"})
IMAGE_PROVIDER_IDS = frozenset({"openai-compatible", "minimax"})
# 提示词模板变量是一份契约：配置校验、AI 优化和最终组合必须认同一套变量名，
# 否则会出现「设置页存得下、生图时替换不掉」这类只在运行时才暴露的偏差。
PROMPT_TEMPLATE_VARIABLES = frozenset({"scene", "narration", "actions", "panels"})
PROMPT_TEMPLATE_VARIABLE_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def game_image_owner_id(game_key: Any) -> str:
    if isinstance(game_key, (list, tuple)):
        return ":".join(str(part) for part in game_key)
    return str(game_key or "")


@dataclass(frozen=True)
class ImageReference:
    """Ephemeral image input; bytes never enter persisted generation records."""

    character_id: str
    content: bytes
    content_type: str = "image/webp"
    file_name: str = "reference.webp"


@dataclass(frozen=True)
class ImageGenerationRequest:
    prompt: str
    purpose: str = "freeform"
    owner_type: str = "system"
    owner_id: str = ""
    aspect_ratio: str = ""
    style: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    reference_images: tuple[ImageReference, ...] = ()


@dataclass(frozen=True)
class ImageGenerationResult:
    generation_id: str
    asset_id: str
    purpose: str
    prompt: str
    revised_prompt: str
    provider: str
    model: str
    created_at: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "generation_id": self.generation_id,
            "asset_id": self.asset_id,
            "purpose": self.purpose,
            "prompt": self.prompt,
            "revised_prompt": self.revised_prompt,
            "provider": self.provider,
            "model": self.model,
            "created_at": self.created_at,
        }
