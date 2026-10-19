"""Author-facing static contracts for managed DiceFrame plugins.

These types describe data after the host has validated it.  JSON-RPC payloads
remain untrusted objects until the corresponding runtime validator accepts
them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypedDict


JsonObject = dict[str, Any]


class _RequiredToolDescriptor(TypedDict):
    name: str
    title: str
    description: str
    input_schema: JsonObject


class ToolDescriptor(_RequiredToolDescriptor, total=False):
    agent_effect: Literal["read_only", "mutation", "destructive"]


class BridgeExtensionDescriptor(TypedDict):
    name: str
    title: str
    description: str
    stages: list[str]
    priority: int
    timeout_sec: float
    platforms: list[str]
    kinds: list[str]


class ProviderCapabilityDescriptor(TypedDict):
    kind: str
    version: int
    methods: dict[str, str]
    title: str
    description: str


ToolHandler = Callable[[JsonObject, JsonObject], JsonObject]
ProviderHandler = Callable[[JsonObject, JsonObject], JsonObject]
BridgeHandler = Callable[[str, JsonObject], JsonObject]
