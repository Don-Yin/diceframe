"""Injected model-generation contract shared by seat action adapters."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class SeatGeneration:
    client: Any
    style_prompt: str
    reason: str
    admission_check: Callable[[], str]
    finish: Callable[[dict[str, Any]], bool]

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()


class SeatRuntime(Protocol):
    def begin(self, instance: Any, uid: str) -> SeatGeneration: ...
