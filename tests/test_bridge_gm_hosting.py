"""Bot-side GM AI-hosting controls (AI teammate PR6).

PR5 gave the Web UI "set to AI / stop AI hosting" and the room an
``away_control_policy``.  Chat tables had no way to reach the same control, even
though the bridge already drives the identical HTTP endpoint shape for away
(``set_player_away``).  This file locks down the chat entry point:

* ``托管 角色名`` hands a seat to the server AI, ``取消托管 角色名`` takes it back;
* the command is GM/authorized-only, exactly like switching someone else's away
  state, and it is submitted *as the GM* because it changes another seat's
  controller;
* the target must match exactly one roster character, otherwise the bot explains
  what is available instead of guessing;
* the bridge keeps no local control state -- one HTTP call, and the server stays
  the only authority;
* a round in flight surfaces as a friendly "try after this round" reply rather
  than a raw failure;
* ordinary narration that merely contains the word is not a hosting command.

The tests drive the real ``DiceFrameBridgeService`` with a fake client that
records the control calls it received.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.bots.bridge_core.commands import (
    hosting_target_query,
    is_host_ai,
    is_stop_hosting,
)
from src.bots.bridge_core.errors import DiceFrameHTTPError
from src.bots.bridge_core.models import BridgeInput
from src.bots.bridge_core.service import DiceFrameBridgeService
from src.bots.bridge_core.store import JsonBridgeStore


class HostingBridgeClient:
    """Fake DiceFrame client: records control calls, can fail with 409."""

    def __init__(self, *, busy: bool = False) -> None:
        self.control_calls: list[tuple[str, str, str, str]] = []
        self.away_calls: list[tuple[str, str, str, bool]] = []
        self.busy = busy

    async def bind_game(self, game_key: str, bind_token: str) -> dict:
        return {
            "ok": True,
            "game_key": game_key,
            "gm_uid": "gm-1",
            "world_name": "长夜",
            "language": "zh-CN",
            "players": [
                {"user_id": "gm-1", "character_name": "主持人"},
                {"user_id": "player-1", "character_name": "阿岚"},
                {"user_id": "player-2", "character_name": "米拉"},
            ],
        }

    async def characters(self, game_key: str, actor: str) -> dict:
        return {"players": []}

    async def build_join_link(self, game_key: str, user: str = "") -> str:
        return f"https://table.example/#/join?game={game_key}&user={user}"

    async def set_player_control(
        self, game_key: str, actor: str, user_id: str, *, mode: str,
    ) -> dict:
        if self.busy:
            raise DiceFrameHTTPError("正在推进剧情", status=409, code="CONTROL_CHANGE_BUSY")
        self.control_calls.append((game_key, actor, user_id, mode))
        return {"ok": True, "user_id": user_id, "character_name": "阿岚", "mode": mode}

    async def set_player_away(
        self, game_key: str, actor: str, user_id: str, *, away: bool,
    ) -> dict:
        self.away_calls.append((game_key, actor, user_id, away))
        return {"ok": True, "user_id": user_id, "character_name": "阿岚", "away": away}


async def _bound_service(tmp_path: Path, client: HostingBridgeClient) -> DiceFrameBridgeService:
    store = JsonBridgeStore(tmp_path / "bridge.json")
    service = DiceFrameBridgeService(client, store)  # type: ignore[arg-type]
    bound = await service.handle(BridgeInput("chan-1", "gm-platform", "/df bind game-1 bind-ok"))
    assert bound.replies
    return service


# ---- 1. 指令识别 -------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "托管 阿岚", "托管阿岚", "交给AI 阿岚", "设为AI 阿岚", "ai托管 阿岚", "host 阿岚",
])
def test_host_commands_are_recognised(text: str) -> None:
    assert is_host_ai(text) is True
    assert is_stop_hosting(text) is False


@pytest.mark.parametrize("text", [
    "取消托管 阿岚", "停止托管 阿岚", "解除托管 阿岚", "交回真人 阿岚", "unhost 阿岚",
])
def test_stop_hosting_commands_are_recognised(text: str) -> None:
    assert is_stop_hosting(text) is True
    assert is_host_ai(text) is False


@pytest.mark.parametrize("text", [
    "我观察四周", "我去托管所打听消息", "攻击守卫", "暂离", "回来", "推进",
])
def test_ordinary_text_is_not_a_hosting_command(text: str) -> None:
    """日常叙事里出现「托管」二字不算指令——指令必须以动词开头。"""

    assert is_host_ai(text) is False
    assert is_stop_hosting(text) is False


def test_the_target_is_extracted_from_the_command() -> None:
    assert hosting_target_query("托管 阿岚") == "阿岚"
    assert hosting_target_query("取消托管 阿岚") == "阿岚"
    assert hosting_target_query("unhost 阿岚") == "阿岚"
    assert hosting_target_query("托管") == ""


# ---- 2. GM 托管 / 取消托管 ---------------------------------------------------


@pytest.mark.asyncio
async def test_gm_can_host_a_character_from_chat(tmp_path: Path) -> None:
    client = HostingBridgeClient()
    service = await _bound_service(tmp_path, client)

    result = await service.handle(BridgeInput("chan-1", "gm-platform", "/df 托管 阿岚"))

    assert client.control_calls == [("game-1", "gm-1", "player-1", "ai")]
    assert "阿岚" in result.replies[0]
    assert "AI" in result.replies[0]


@pytest.mark.asyncio
async def test_gm_can_stop_hosting_from_chat(tmp_path: Path) -> None:
    client = HostingBridgeClient()
    service = await _bound_service(tmp_path, client)

    result = await service.handle(BridgeInput("chan-1", "gm-platform", "/df 取消托管 阿岚"))

    assert client.control_calls == [("game-1", "gm-1", "player-1", "human")]
    assert "阿岚" in result.replies[0]


@pytest.mark.asyncio
async def test_hosting_is_submitted_as_the_gm_not_the_target(tmp_path: Path) -> None:
    """改变别人席位的控制器属于 GM 权限，必须以 GM 身份提交。"""

    client = HostingBridgeClient()
    service = await _bound_service(tmp_path, client)

    await service.handle(BridgeInput("chan-1", "gm-platform", "/df 托管 米拉"))

    _game_key, actor, target, mode = client.control_calls[0]
    assert actor == "gm-1"
    assert target == "player-2"
    assert mode == "ai"


@pytest.mark.asyncio
async def test_a_non_gm_player_cannot_host_someone_elses_character(tmp_path: Path) -> None:
    client = HostingBridgeClient()
    store = JsonBridgeStore(tmp_path / "bridge.json")
    service = DiceFrameBridgeService(client, store)  # type: ignore[arg-type]
    await service.handle(BridgeInput("chan-1", "gm-platform", "/df bind game-1 bind-ok"))
    # 该玩家确实认领了米拉，所以拦住他的必须是托管权限，而不是「还没认领角色」。
    await store.bind_player("chan-1", "player-platform", "player-2")

    result = await service.handle(BridgeInput("chan-1", "player-platform", "/df 托管 阿岚"))

    assert client.control_calls == []
    assert "GM" in result.replies[0]


@pytest.mark.asyncio
async def test_a_missing_target_is_explained_instead_of_guessed(tmp_path: Path) -> None:
    client = HostingBridgeClient()
    service = await _bound_service(tmp_path, client)

    result = await service.handle(BridgeInput("chan-1", "gm-platform", "/df 托管"))

    assert client.control_calls == []
    assert "角色名" in result.replies[0]


@pytest.mark.asyncio
async def test_an_ambiguous_target_lists_what_is_available(tmp_path: Path) -> None:
    client = HostingBridgeClient()
    service = await _bound_service(tmp_path, client)

    result = await service.handle(BridgeInput("chan-1", "gm-platform", "/df 托管 不存在"))

    assert client.control_calls == []
    assert "不存在" in result.replies[0]


# ---- 3. 安全边界与失败表现 ----------------------------------------------------


@pytest.mark.asyncio
async def test_a_round_in_flight_becomes_a_friendly_retry_reply(tmp_path: Path) -> None:
    """服务端 409 CONTROL_CHANGE_BUSY 不该以原始失败文案抛给群里。"""

    client = HostingBridgeClient(busy=True)
    service = await _bound_service(tmp_path, client)

    result = await service.handle(BridgeInput("chan-1", "gm-platform", "/df 托管 阿岚"))

    assert client.control_calls == []
    assert "本轮" in result.replies[0]
    assert "失败" not in result.replies[0]


# ---- 4. 与本 PR 无关的旧行为不受影响 ------------------------------------------


@pytest.mark.asyncio
async def test_the_away_command_still_uses_the_away_endpoint(tmp_path: Path) -> None:
    """托管指令不能把「暂离」抢走：两者走的是不同的服务端契约。"""

    client = HostingBridgeClient()
    service = await _bound_service(tmp_path, client)

    await service.handle(BridgeInput("chan-1", "gm-platform", "/df 暂离 阿岚"))

    assert client.away_calls == [("game-1", "gm-1", "player-1", True)]
    assert client.control_calls == []


@pytest.mark.asyncio
async def test_help_mentions_the_hosting_commands(tmp_path: Path) -> None:
    client = HostingBridgeClient()
    service = await _bound_service(tmp_path, client)

    result = await service.handle(BridgeInput("chan-1", "gm-platform", "/df 帮助"))

    assert "托管" in result.replies[0]
