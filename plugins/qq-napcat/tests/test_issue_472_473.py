"""Regression coverage for QQ web-sync and private character drafting."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, filename: str, class_name: str):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "plugins" / "qq-napcat" / "src" / "bots" / "qq" / filename,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


QQCharacterFlowMixin = _load("qq_character_flow_issue_tests", "character_flow.py", "QQCharacterFlowMixin")
QQWebSyncMixin = _load("qq_web_sync_issue_tests", "web_sync.py", "QQWebSyncMixin")


class _CharacterBot(QQCharacterFlowMixin):
    def __init__(self) -> None:
        self.character_wizards = {}
        self.api = SimpleNamespace()
        self._send_private_text = AsyncMock()
        self._send_private_card = AsyncMock()
        self._send_group_card = AsyncMock()
        self.logger = SimpleNamespace(warning=lambda *_args, **_kwargs: None)

    _character_draft_lines = staticmethod(lambda draft, _language: [draft["character_name"]])
    _character_public_lines = _character_draft_lines
    _character_draft_text = staticmethod(lambda *_args, **_kwargs: "preview")
    _link_reminders_enabled = staticmethod(lambda: False)
    _link_text = staticmethod(lambda *_args: "")
    _link_suffix = staticmethod(lambda *_args: "")
    _group_language = staticmethod(lambda _group: "en")


@pytest.mark.asyncio
async def test_late_character_generation_cannot_replace_newer_draft_or_preview() -> None:
    bot = _CharacterBot()
    bot.character_wizards["player"] = {
        "language": "en", "game_key": "game", "group_id": "group", "state": "awaiting_prompt",
    }
    started, release = asyncio.Event(), asyncio.Event()

    async def generate(prompt: str, **_kwargs):
        if prompt == "original":
            started.set()
            await release.wait()
            return {"ok": True, "character": {"character_name": "Late original"}}
        return {"ok": True, "character": {"character_name": "Newest draft"}}

    bot.api.generate_character = generate
    old_request = asyncio.create_task(bot._handle_character_wizard_private("player", "original"))
    await started.wait()
    await bot._handle_character_wizard_private("player", "revision")
    release.set()
    await old_request

    assert bot.character_wizards["player"]["draft"]["character_name"] == "Newest draft"
    assert bot._send_private_card.await_count == 1


@pytest.mark.asyncio
async def test_restart_invalidates_inflight_character_generation() -> None:
    bot = _CharacterBot()
    await bot._start_character_creation_wizard("group", "player", "game", "", [], "en")
    started, release = asyncio.Event(), asyncio.Event()

    async def generate(_prompt: str, **_kwargs):
        started.set()
        await release.wait()
        return {"ok": True, "character": {"character_name": "Discard me"}}

    bot.api.generate_character = generate
    request = asyncio.create_task(bot._handle_character_wizard_private("player", "old request"))
    await started.wait()
    await bot._start_character_creation_wizard("group", "player", "game", "", [], "en")
    release.set()
    await request

    assert bot.character_wizards["player"]["state"] == "awaiting_prompt"
    assert bot._send_private_card.await_count == 0


@pytest.mark.asyncio
async def test_concurrent_confirmations_publish_a_draft_once() -> None:
    bot = _CharacterBot()
    bot.character_wizards["player"] = {
        "language": "en", "group_id": "group", "state": "draft",
        "draft": {"character_name": "Only once"},
    }
    await asyncio.gather(
        bot._handle_character_wizard_private("player", "confirm"),
        bot._handle_character_wizard_private("player", "confirm"),
    )
    assert bot._send_group_card.await_count == 1
    assert "player" not in bot.character_wizards


@pytest.mark.asyncio
async def test_failed_character_publish_keeps_current_draft_for_retry() -> None:
    bot = _CharacterBot()
    bot.character_wizards["player"] = {
        "language": "en", "group_id": "group", "state": "draft", "draft_version": 3,
        "draft": {"character_name": "Retry me"},
    }
    bot._send_group_card.side_effect = [RuntimeError("temporary"), None]

    await bot._handle_character_wizard_private("player", "confirm")
    assert bot.character_wizards["player"]["state"] == "draft"
    assert bot.character_wizards["player"]["draft_version"] == 3

    await bot._handle_character_wizard_private("player", "confirm")
    assert "player" not in bot.character_wizards


@pytest.mark.asyncio
async def test_confirmation_during_revision_cannot_publish_the_previous_draft():
    bot = _CharacterBot()
    bot.character_wizards["player"] = {
        "language": "en", "group_id": "group", "state": "draft",
        "draft": {"character_name": "Old"},
    }
    started, release = asyncio.Event(), asyncio.Event()

    async def generate(*_args, **_kwargs):
        started.set()
        await release.wait()
        return {"ok": True, "character": {"character_name": "New"}}

    bot.api.generate_character = generate
    task = asyncio.create_task(bot._handle_character_wizard_private("player", "revision"))
    await started.wait()
    await bot._handle_character_wizard_private("player", "confirm")
    assert bot._send_group_card.await_count == 0
    release.set()
    await task
    await bot._handle_character_wizard_private("player", "confirm")
    assert bot._send_group_card.await_count == 1
    assert bot._send_group_card.await_args.kwargs["subtitle"] == "New"


@pytest.mark.asyncio
async def test_cancel_discards_late_generation_and_generation_failure_is_retryable():
    bot = _CharacterBot()
    await bot._start_character_creation_wizard("group", "player", "game", "", [], "en")
    started, release = asyncio.Event(), asyncio.Event()

    async def generate(*_args, **_kwargs):
        started.set()
        await release.wait()
        return {"ok": True, "character": {"character_name": "Discard"}}

    bot.api.generate_character = generate
    task = asyncio.create_task(bot._handle_character_wizard_private("player", "original"))
    await started.wait()
    await bot._handle_character_wizard_private("player", "cancel")
    release.set()
    await task
    assert "player" not in bot.character_wizards
    assert not bot._send_private_card.await_count

    await bot._start_character_creation_wizard("group", "player", "game", "", [], "en")
    bot.api.generate_character = AsyncMock(side_effect=RuntimeError("offline"))
    await bot._handle_character_wizard_private("player", "retryable")
    assert bot.character_wizards["player"]["state"] == "awaiting_prompt"


@pytest.mark.asyncio
async def test_private_ack_failure_does_not_republish_a_committed_public_draft():
    bot = _CharacterBot()
    bot.character_wizards["player"] = {
        "language": "en", "group_id": "group", "state": "draft",
        "draft": {"character_name": "Only once"},
    }
    bot._send_private_text.side_effect = RuntimeError("private chat closed")
    await bot._handle_character_wizard_private("player", "confirm")
    await bot._handle_character_wizard_private("player", "confirm")
    assert bot._send_group_card.await_count == 1
    assert "player" not in bot.character_wizards


class _SyncStore:
    def __init__(self) -> None:
        self.groups = {
            "group-a": {"game_key": "game", "gm_uid": "gm", "language": "en"},
            "group-b": {"game_key": "other-game", "gm_uid": "other-gm", "language": "en"},
        }
        self.players = {
            "group-a:qq-payer": {"game_key": "game", "user_id": "payer"},
            "group-a:qq-other": {"game_key": "game", "user_id": "other"},
            "group-b:qq-payer": {"game_key": "other-game", "user_id": "payer"},
        }

    def group(self, group_id: str):
        return self.groups.get(group_id)

    async def unbind_group(self, group_id: str) -> None:
        self.groups.pop(group_id, None)


class _SyncBot(QQWebSyncMixin):
    def __init__(self, details: list[dict]) -> None:
        self.store = _SyncStore()
        self.api = SimpleNamespace(game_detail=AsyncMock(side_effect=details))
        self.logger = SimpleNamespace(info=lambda *_args, **_kwargs: None, warning=lambda *_args, **_kwargs: None)
        self._web_sync_failures = {}
        self._web_sync_last_round = {"group-a:game": 5, "group-b:other-game": 1}
        self._web_sync_run_ids = {}
        self._web_sync_seen_actions = {}
        self._web_sync_seen_luck = {}
        self._web_sync_seen_payments = {}
        self._web_sync_scene_images = {}
        self._group_action_inflight = {}
        self._send_private_payment_prompt = AsyncMock()
        self._send_scene_image_update = AsyncMock()
        self._send_group_text = AsyncMock()

    _group_language = staticmethod(lambda group: str(group.get("language") or "en"))


def _detail(*, proposals=None, scene_image=None, round_number=5) -> dict:
    return {
        "round_number": round_number,
        "recap": {"pending_actions": [], "recent_rounds": []},
        "pending_luck_decisions": [],
        "economy_proposals": proposals or [],
        "scene_image": scene_image or {},
    }


@pytest.mark.asyncio
async def test_same_round_payment_and_scene_changes_sync_once_to_their_authorized_targets() -> None:
    proposal = {"id": "pay-1", "status": "pending", "approval_policy": "payer", "payer_uid": "payer"}
    bot = _SyncBot([
        _detail(proposals=[], scene_image={"asset_id": "old"}),
        _detail(round_number=1),
        _detail(proposals=[proposal], scene_image={"asset_id": "new"}),
        _detail(round_number=1),
    ])
    bot._web_sync_scene_images["group-a:game"] = '{"asset_id":"old"}'
    bot._web_sync_scene_images["group-b:other-game"] = "{}"

    await bot._poll_web_notifications()
    await bot._poll_web_notifications()

    bot._send_private_payment_prompt.assert_awaited_once_with("qq-payer", "game", "payer")
    bot._send_scene_image_update.assert_awaited_once_with("group-a", "game")
    assert bot._send_group_text.await_count == 0


@pytest.mark.asyncio
async def test_failed_payment_and_scene_sync_are_retried_without_cross_group_delivery() -> None:
    proposal = {"id": "pay-1", "status": "pending", "approval_policy": "payer", "payer_uid": "payer"}
    bot = _SyncBot([
        _detail(proposals=[proposal], scene_image={"asset_id": "new"}),
        _detail(round_number=1),
        _detail(proposals=[proposal], scene_image={"asset_id": "new"}),
        _detail(round_number=1),
    ])
    bot._web_sync_scene_images["group-a:game"] = '{"asset_id":"old"}'
    bot._web_sync_scene_images["group-b:other-game"] = "{}"
    bot._send_private_payment_prompt.side_effect = [RuntimeError("temporary"), None]
    bot._send_scene_image_update.side_effect = [RuntimeError("temporary"), None]

    await bot._poll_web_notifications()
    await bot._poll_web_notifications()

    assert bot._send_private_payment_prompt.await_count == 2
    assert bot._send_private_payment_prompt.await_args_list[0].args[0] == "qq-payer"
    assert bot._send_scene_image_update.await_count == 2
    assert all(call.args[0] == "group-a" for call in bot._send_scene_image_update.await_args_list)


@pytest.mark.asyncio
async def test_scene_sync_sends_the_authorized_current_image_not_only_a_text_notice(tmp_path):
    bot = _SyncBot([])
    del bot._send_scene_image_update
    bot.card_dir = tmp_path
    bot.api.download_scene_image = AsyncMock(return_value=tmp_path / "scene.png")
    bot.sender = SimpleNamespace(send_group_image=AsyncMock())
    bot._reply_delay = AsyncMock()
    bot._web_sync_scene_images["group-a:game"] = '{}'
    await bot._sync_scene_image("group-a", "game", _detail(scene_image={"kind": "generated", "asset_id": "new"}))
    bot.api.download_scene_image.assert_awaited_once_with("game", "gm", tmp_path)
    bot.sender.send_group_image.assert_awaited_once()
    assert bot.sender.send_group_image.await_args.args[:2] == ("group-a", str(tmp_path / "scene.png"))
    assert not bot._send_group_text.await_count


@pytest.mark.asyncio
async def test_gm_only_payment_proposals_never_prompt_the_payer():
    bot = _SyncBot([])
    await bot._sync_pending_payments("group-a", "game", _detail(proposals=[{
        "id": "secret", "status": "pending", "approval_policy": "gm", "payer_uid": "payer",
    }]))
    bot._send_private_payment_prompt.assert_not_awaited()


@pytest.mark.asyncio
async def test_each_group_receives_same_game_round_and_failed_delivery_retries():
    detail = _detail(round_number=6)
    detail["recap"]["recent_rounds"] = [{"gm_response": "public"}]
    bot = _SyncBot([detail, detail, detail, detail])
    bot.store.groups["group-b"]["game_key"] = "game"
    bot._web_sync_last_round["group-b:game"] = 5
    bot._send_web_round_to_group = AsyncMock(side_effect=[RuntimeError("offline"), None, None])
    await bot._poll_web_notifications()
    await bot._poll_web_notifications()
    assert [call.args[0] for call in bot._send_web_round_to_group.await_args_list] == ["group-a", "group-b", "group-a"]


@pytest.mark.asyncio
async def test_new_run_resets_old_round_cursor_and_image_baseline():
    detail = {**_detail(round_number=1), "run_id": "new-run"}
    bot = _SyncBot([detail, _detail(round_number=1)])
    bot._web_sync_run_ids["group-a:game"] = "old-run"
    bot._web_sync_scene_images["group-a:game"] = '{"asset_id":"old-run-image"}'
    await bot._poll_web_notifications()
    assert bot._web_sync_last_round["group-a:game"] == 1
    bot._send_scene_image_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_rebinding_while_detail_is_in_flight_discards_the_old_projection():
    bot = _SyncBot([])
    bot.store.groups.pop("group-b")
    bot._send_web_action_to_group = AsyncMock()
    async def detail(*_args):
        bot.store.groups["group-a"]["game_key"] = "new-game"
        result = _detail(proposals=[{"id": "old", "status": "pending", "approval_policy": "payer", "payer_uid": "payer"}])
        result["recap"]["pending_actions"] = [{"signature": "old-action", "text": "old game"}]
        return result
    bot.api.game_detail.side_effect = detail
    await bot._poll_web_notifications()
    bot._send_web_action_to_group.assert_not_awaited()
    bot._send_private_payment_prompt.assert_not_awaited()


@pytest.mark.asyncio
async def test_in_place_gm_rebind_during_scene_download_prevents_delivery(tmp_path):
    bot = _SyncBot([])
    del bot._send_scene_image_update
    bot.card_dir = tmp_path
    bot.sender = SimpleNamespace(send_group_image=AsyncMock())
    bot._reply_delay = AsyncMock()
    async def download(*_args):
        bot.store.groups["group-a"]["gm_uid"] = "new-gm"
        return tmp_path / "old-scene.png"
    bot.api.download_scene_image = AsyncMock(side_effect=download)
    with pytest.raises(ValueError, match="binding changed"):
        await bot._send_scene_image_update("group-a", "game")
    bot.sender.send_group_image.assert_not_awaited()


@pytest.mark.asyncio
async def test_false_private_delivery_is_not_counted_as_a_delivered_payment_prompt():
    bot = _SyncBot([])
    del bot._send_private_payment_prompt
    bot._send_payment_list_private = AsyncMock(return_value=False)
    with pytest.raises(RuntimeError, match="delivery"):
        await bot._send_private_payment_prompt("qq-payer", "game", "payer")
