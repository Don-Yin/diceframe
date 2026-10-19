"""Web-to-QQ synchronization helpers."""

from __future__ import annotations

import json

from src.bots.bridge_core.errors import DiceFrameHTTPError
from src.bots.bridge_core.language import bridge_is_english
from src.bots.bridge_core.presenters import luck_prompt_lines

_STALE_BINDING_FAILURE_LIMIT = 3


class QQWebSyncMixin:
    async def _poll_web_notifications(self) -> None:
        """轮询 web 端游戏进度：实时转发网页新提交的行动，推进时发叙事+状态变动。"""
        for group_id, group in list(self.store.groups.items()):
            game_key = str(group.get("game_key") or "")
            gm_uid = str(group.get("gm_uid") or "")
            if not game_key or not gm_uid:
                continue
            try:
                detail = await self.api.game_detail(game_key, gm_uid)
            except DiceFrameHTTPError as exc:
                if not self._web_binding_matches(group_id, game_key, gm_uid):
                    continue
                stale_binding = (
                    exc.code in {"GAME_NOT_FOUND", "BOT_ACTOR_INVALID"}
                    or exc.status == 404
                    or (exc.status == 403 and str(exc) == "Bot 代表玩家无效")
                )
                if stale_binding:
                    failures = self._web_sync_failures.get(group_id, 0) + 1
                    self._web_sync_failures[group_id] = failures
                    if failures >= _STALE_BINDING_FAILURE_LIMIT:
                        await self.store.unbind_group(group_id)
                        self._web_sync_failures.pop(group_id, None)
                        sync_key = self._web_sync_key(group_id, game_key)
                        self._clear_web_sync_cursor(sync_key)
                        self._web_sync_run_ids.pop(sync_key, None)
                        self.logger.warning(
                            "Web 同步绑定已失效并自动解除: group=%s game=%s code=%s status=%s",
                            group_id, game_key, exc.code or "-", exc.status or "-",
                        )
                        continue
                    self.logger.warning(
                        "Web 同步绑定校验失败（%d/%d）: group=%s game=%s code=%s status=%s",
                        failures, _STALE_BINDING_FAILURE_LIMIT,
                        group_id, game_key, exc.code or "-", exc.status or "-",
                    )
                    continue
                self.logger.warning("Web 同步轮询 game_detail 失败: %s", game_key, exc_info=True)
                continue
            except Exception:
                self.logger.warning("Web 同步轮询 game_detail 失败: %s", game_key, exc_info=True)
                continue
            if not self._web_binding_matches(group_id, game_key, gm_uid):
                continue
            self._web_sync_failures.pop(group_id, None)
            if not isinstance(detail, dict):
                continue
            # Every QQ group has an independent delivery cursor. A reset may
            # keep the same game key while returning its round counter to one.
            sync_key = self._web_sync_key(group_id, game_key)
            run_id = str(detail.get("run_id") or "")
            previous_run = self._web_sync_run_ids.get(sync_key)
            if previous_run is not None and previous_run != run_id:
                self._clear_web_sync_cursor(sync_key)
            self._web_sync_run_ids[sync_key] = run_id
            recap = detail.get("recap") or {}
            seen = self._web_sync_seen_actions.setdefault(sync_key, set())

            pending = recap.get("pending_actions") if isinstance(recap.get("pending_actions"), list) else []
            for action in pending:
                if not isinstance(action, dict):
                    continue
                sig = str(action.get("signature") or "")
                if not sig or sig in seen:
                    continue
                try:
                    await self._send_web_action_to_group(group_id, action)
                    seen.add(sig)
                except Exception:
                    self.logger.warning("Web 同步实时转发行动失败: group=%s sig=%s", group_id, sig, exc_info=True)

            pending_luck = detail.get("pending_luck_decisions") if isinstance(detail.get("pending_luck_decisions"), list) else []
            seen_luck = self._web_sync_seen_luck.setdefault(sync_key, set())
            current_luck_ids = {
                str(check.get("check_id") or "")
                for check in pending_luck
                if isinstance(check, dict) and str(check.get("check_id") or "")
            }
            seen_luck.intersection_update(current_luck_ids)
            if not self._group_action_inflight.get(game_key):
                for check in pending_luck:
                    if not isinstance(check, dict):
                        continue
                    check_id = str(check.get("check_id") or "")
                    if not check_id or check_id in seen_luck:
                        continue
                    language = self._group_language(group)
                    try:
                        await self._send_group_text(
                            group_id,
                            "\n".join(luck_prompt_lines([check], language, command_prefix="@我")),
                        )
                        seen_luck.add(check_id)
                    except Exception:
                        self.logger.warning("Web 同步幸运选择提示失败: group=%s check=%s", group_id, check_id, exc_info=True)

            await self._sync_pending_payments(group_id, game_key, detail)
            await self._sync_scene_image(group_id, game_key, detail)

            current_round = int(detail.get("round_number") or 0)
            last = self._web_sync_last_round.get(sync_key)
            if last is None:
                self._web_sync_last_round[sync_key] = current_round
                self.logger.info("Web 同步基线: game=%s round=%d（之后网页推进新轮将转发到群）", game_key, current_round)
                continue
            if current_round <= last or self._group_action_inflight.get(game_key):
                continue
            self.logger.info("Web 同步检测到新轮: game=%s round=%d，转发到群 %s", game_key, current_round, group_id)
            rounds = recap.get("recent_rounds") if isinstance(recap.get("recent_rounds"), list) else []
            if not rounds:
                continue
            latest = rounds[-1] if isinstance(rounds[-1], dict) else {}
            try:
                await self._send_web_round_to_group(group_id, latest, current_round, seen, quick_actions=detail.get("quick_actions"))
            except Exception:
                self.logger.warning("Web 同步转发到群失败: group=%s round=%s", group_id, current_round, exc_info=True)
                continue
            self._web_sync_last_round[sync_key] = current_round
            seen.clear()
            self._web_sync_seen_luck.pop(sync_key, None)

    def _clear_web_sync_cursor(self, sync_key: str) -> None:
        for cache in (
            self._web_sync_last_round, self._web_sync_seen_actions,
            self._web_sync_seen_luck, self._web_sync_seen_payments,
            self._web_sync_scene_images,
        ):
            cache.pop(sync_key, None)

    async def _sync_pending_payments(self, group_id: str, game_key: str, detail: dict) -> None:
        """Prompt only the QQ identity bound to a pending payer proposal.

        ``economy_proposals`` is already the server's viewer-filtered payment
        contract.  The group poll uses the GM actor to observe new proposals,
        but never forwards proposal fields into the group: the payer receives
        a fresh actor-scoped private projection instead.
        """

        proposals = detail.get("economy_proposals")
        if not isinstance(proposals, list):
            return
        seen = self._web_sync_seen_payments.setdefault(self._web_sync_key(group_id, game_key), set())
        current: set[str] = set()
        for proposal in proposals:
            if (
                not isinstance(proposal, dict)
                or str(proposal.get("status") or "") != "pending"
                or str(proposal.get("approval_policy") or "") != "payer"
            ):
                continue
            payer_uid = str(proposal.get("payer_uid") or "")
            proposal_id = str(proposal.get("id") or "")
            if not payer_uid or not proposal_id:
                continue
            for platform_user_id in self._platform_users_for_actor(group_id, game_key, payer_uid):
                signature = f"{proposal_id}:{platform_user_id}"
                current.add(signature)
                if signature in seen:
                    continue
                try:
                    await self._send_private_payment_prompt(platform_user_id, game_key, payer_uid)
                except Exception:
                    self.logger.warning(
                        "Web 同步支付私聊提示失败: group=%s payment=%s user=%s",
                        group_id, proposal_id, platform_user_id, exc_info=True,
                    )
                    continue
                seen.add(signature)
        seen.intersection_update(current)

    def _platform_users_for_actor(self, group_id: str, game_key: str, actor_uid: str) -> list[str]:
        """Return only bindings from this QQ group for the requested actor."""

        prefix = f"{group_id}:"
        players = getattr(self.store, "players", {})
        if not isinstance(players, dict):
            return []
        return [
            key[len(prefix):]
            for key, binding in players.items()
            if key.startswith(prefix)
            and isinstance(binding, dict)
            and str(binding.get("game_key") or "") == game_key
            and str(binding.get("user_id") or "") == actor_uid
            and key[len(prefix):]
        ]

    async def _send_private_payment_prompt(self, platform_user_id: str, game_key: str, actor_uid: str) -> None:
        """Use the payer's own projection so private proposal fields stay private."""

        delivered = await self._send_payment_list_private(platform_user_id, game_key, actor_uid, announce=False)
        if not delivered:
            raise RuntimeError("private payment prompt delivery failed")

    async def _sync_scene_image(self, group_id: str, game_key: str, detail: dict) -> None:
        reference = detail.get("scene_image")
        if not isinstance(reference, dict):
            reference = {}
        signature = json.dumps(reference, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        sync_key = self._web_sync_key(group_id, game_key)
        previous = self._web_sync_scene_images.get(sync_key)
        if previous is None:
            self._web_sync_scene_images[sync_key] = signature
            return
        if previous == signature:
            return
        try:
            await self._send_scene_image_update(group_id, game_key)
        except Exception:
            self.logger.warning("Web 同步场景图提示失败: group=%s", group_id, exc_info=True)
            return
        self._web_sync_scene_images[sync_key] = signature

    @staticmethod
    def _web_sync_key(group_id: str, game_key: str) -> str:
        return f"{group_id}:{game_key}"

    def _web_binding_matches(self, group_id: str, game_key: str, gm_uid: str) -> bool:
        current = self.store.group(group_id) or {}
        return str(current.get("game_key") or "") == game_key and str(current.get("gm_uid") or "") == gm_uid

    async def _send_scene_image_update(self, group_id: str, game_key: str) -> None:
        group = self.store.group(group_id) or {}
        if str(group.get("game_key") or "") != game_key:
            raise ValueError("group binding changed during scene sync")
        gm_uid = str(group.get("gm_uid") or "")
        image = await self.api.download_scene_image(
            game_key, gm_uid, self.card_dir,
        )
        await self._reply_delay()
        if not self._web_binding_matches(group_id, game_key, gm_uid):
            raise ValueError("group binding changed before scene delivery")
        await self.sender.send_group_image(group_id, str(image))

    async def _send_web_action_to_group(self, group_id: str, action: dict) -> None:
        """网页玩家行动实时转发：纯文本「角色名：行动」，像群友发言。"""
        if str(action.get("source") or "") == "group":
            return
        language = self._group_language(self.store.group(group_id))
        english = bridge_is_english(language)
        name = str(action.get("character_name") or ("Adventurer" if english else "冒险者"))
        text = str(action.get("text") or "").strip()
        if not text:
            return
        await self._send_group_text(group_id, f"{name}: {text}" if english else f"{name}：{text}")

    async def _send_web_round_to_group(self, group_id: str, round_entry: dict, round_number: int, seen: set[str], *, quick_actions: list[str] | None = None) -> None:
        """轮次推进时：补发未被实时转发的行动 + 合并卡。"""
        actions = round_entry.get("actions") or []
        for action in actions:
            if not isinstance(action, dict):
                continue
            sig = str(action.get("signature") or "")
            if sig and sig not in seen:
                await self._send_web_action_to_group(group_id, action)
                seen.add(sig)
        await self._send_round_summary_card(
            group_id,
            round_number,
            str(round_entry.get("gm_response") or ""),
            round_entry.get("state_changes"),
            quick_actions=quick_actions,
        )
