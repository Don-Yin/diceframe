"""Application service for persisted character dialogue/story settings."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from src.engine import module_state
from src.engine.game_instance import GameState
from src.engine.modules import storytelling
from src.engine.story import public_story


@dataclass(frozen=True)
class StorytellingDependencies:
    parse_game_key: Callable[[str], tuple[str, ...]]
    get_instance: Callable[[tuple[str, ...]], Any | None]
    save_instance: Callable[[Any], Awaitable[None]]
    validate_portrait: Callable[[Any], dict[str, str] | None]


class StorytellingService:
    """Owns validation, authoritative fencing, and durable persistence."""

    def __init__(self, dependencies: StorytellingDependencies) -> None:
        self._dependencies = dependencies

    def _instance(self, game_key: str) -> Any | None:
        return self._dependencies.get_instance(
            self._dependencies.parse_game_key(game_key)
        )

    @staticmethod
    def _write_error(exc: Exception) -> dict[str, Any]:
        if isinstance(exc, module_state.ModuleStateError):
            return {
                "ok": False,
                "error_code": "UNSUPPORTED_STORYTELLING_SCHEMA",
                "error": "剧情模式设置版本不受当前运行时支持",
            }
        return {
            "ok": False,
            "error_code": "SAVE_FAILED",
            "error": "剧情模式设置保存失败",
        }

    async def set_mode(self, game_key: str, value: Any) -> dict[str, Any]:
        instance = self._instance(game_key)
        if instance is None:
            return {"ok": False, "error_code": "GAME_NOT_FOUND", "error": "游戏不存在"}
        if not isinstance(value, str) or value not in storytelling.MODES:
            return {
                "ok": False,
                "error_code": "INVALID_STORY_MODE",
                "error": "故事模式必须是 prose 或 dialogue",
            }
        async with instance.authoritative_write() as entered, instance._lock:
            if not entered:
                return {
                    "ok": False,
                    "error_code": "REWRITE_IN_PROGRESS",
                    "error": "GM 正在重写历史回合，请等待完成后重试",
                }
            if (
                instance.state == GameState.ACTIVE_JUDGMENT
                or instance.round_processing_in_flight()
            ):
                return {
                    "ok": False,
                    "error_code": "STORY_MODE_LOCKED",
                    "error": "回合生成进行中，暂时不能切换故事模式",
                }
            try:
                storytelling.require_writable(instance)
                before = storytelling.snapshot(instance)
                storytelling.replace_mode(instance, value)
                await self._dependencies.save_instance(instance)
            except asyncio.CancelledError:
                if "before" in locals():
                    storytelling.restore(instance, before)
                raise
            except Exception as exc:
                if "before" in locals():
                    storytelling.restore(instance, before)
                return self._write_error(exc)
        return {"ok": True, "story_mode": storytelling.mode(instance)}

    @staticmethod
    def _active_speaker_ids(instance: Any) -> set[str]:
        log = getattr(instance, "log", None)
        if not isinstance(log, list):
            return set()
        speaker_ids: set[str] = set()
        for entry in log:
            if not isinstance(entry, dict):
                continue
            story = entry.get("story")
            segments = story.get("segments") if isinstance(story, dict) else None
            if not isinstance(segments, list):
                continue
            speaker_ids.update(
                str(segment.get("speaker_id") or "")
                for segment in segments
                if isinstance(segment, dict) and isinstance(segment.get("speaker_id"), str)
            )
        aliases = storytelling.speaker_aliases(instance)
        return {aliases.get(speaker_id, speaker_id) for speaker_id in speaker_ids}

    async def set_portrait(
        self, game_key: str, speaker_id: str, value: Any,
    ) -> dict[str, Any]:
        instance = self._instance(game_key)
        if instance is None:
            return {"ok": False, "error_code": "GAME_NOT_FOUND", "error": "游戏不存在"}
        speaker_key = str(speaker_id or "")
        if storytelling.SPEAKER_ID_RE.fullmatch(speaker_key) is None:
            return {"ok": False, "error_code": "INVALID_SPEAKER_ID", "error": "说话人编号无效"}
        async with instance.authoritative_write() as entered, instance._lock:
            if not entered:
                return {
                    "ok": False,
                    "error_code": "REWRITE_IN_PROGRESS",
                    "error": "GM 正在重写历史回合，请等待完成后重试",
                }
            try:
                storytelling.require_writable(instance)
                if speaker_key not in self._active_speaker_ids(instance):
                    return {
                        "ok": False,
                        "error_code": "UNKNOWN_SPEAKER",
                        "error": "当前剧情中不存在该说话人",
                    }
                try:
                    normalized = self._dependencies.validate_portrait(value)
                except (TypeError, ValueError) as exc:
                    return {
                        "ok": False,
                        "error_code": "INVALID_PORTRAIT",
                        "error": str(exc),
                    }
                before = storytelling.snapshot(instance)
                storytelling.set_portrait(instance, speaker_key, normalized)
                await self._dependencies.save_instance(instance)
            except asyncio.CancelledError:
                if "before" in locals():
                    storytelling.restore(instance, before)
                raise
            except Exception as exc:
                if "before" in locals():
                    storytelling.restore(instance, before)
                return self._write_error(exc)
        return {"ok": True, "speaker_id": speaker_key, "portrait": normalized}

    def settings(self, instance: Any) -> dict[str, Any]:
        """Return a detached projection for game detail and lifecycle code."""
        return {
            "story_mode": storytelling.read_mode(instance),
            "story_portraits": deepcopy(storytelling.portrait_overrides(instance)),
        }

    async def merge_speakers(self, game_key: str, source: Any, target: Any) -> dict[str, Any]:
        instance = self._instance(game_key)
        if instance is None:
            return {"ok": False, "error_code": "GAME_NOT_FOUND", "error": "游戏不存在"}
        if (not isinstance(source, str) or not isinstance(target, str)
                or not source.startswith("g_") or source == target
                or storytelling.SPEAKER_ID_RE.fullmatch(source) is None
                or storytelling.SPEAKER_ID_RE.fullmatch(target) is None):
            return {"ok": False, "error_code": "INVALID_SPEAKER_MERGE", "error": "只能将临时人物合并到另一位已出场人物"}
        async with instance.authoritative_write() as entered, instance._lock:
            if not entered or instance.state == GameState.ACTIVE_JUDGMENT or instance.round_processing_in_flight():
                return {"ok": False, "error_code": "STORY_MODE_LOCKED", "error": "生成或重写进行中，请稍后重试"}
            try:
                storytelling.require_writable(instance)
                roster = self.list_speakers(game_key)
                if not roster.get("ok"):
                    return roster
                people = {item["id"]: item for item in roster["speakers"]}
                if source not in people or target not in people:
                    return {"ok": False, "error_code": "UNKNOWN_SPEAKER", "error": "人物列表已变化，请刷新后重试"}
                if people[source]["name"] != people[target]["name"]:
                    return {"ok": False, "error_code": "INVALID_SPEAKER_MERGE", "error": "不同公开身份不能合并"}
                overrides = storytelling.portrait_overrides(instance)
                portrait = overrides.get(target, overrides.get(source, people[target].get("portrait") or people[source].get("portrait")))
                before = storytelling.snapshot(instance)
                storytelling.merge_speaker(instance, source, target, portrait)
                await self._dependencies.save_instance(instance)
            except asyncio.CancelledError:
                if "before" in locals():
                    storytelling.restore(instance, before)
                raise
            except Exception as exc:
                if "before" in locals():
                    storytelling.restore(instance, before)
                return self._write_error(exc)
        return {"ok": True, "source_id": source, "speaker_id": target}

    def list_speakers(self, game_key: str) -> dict[str, Any]:
        """Return the bounded public cast from every selected story entry."""
        instance = self._instance(game_key)
        if instance is None:
            return {"ok": False, "error_code": "GAME_NOT_FOUND", "error": "游戏不存在"}
        roster: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        try:
            for entry in reversed(getattr(instance, "log", []) or []):
                raw_story = entry.get("story") if isinstance(entry, dict) else None
                projected = public_story(instance, raw_story)
                if not projected:
                    continue
                for segment in projected.get("segments", []):
                    if segment.get("kind") != "dialogue":
                        continue
                    speaker_id = segment.get("speaker_id")
                    name = segment.get("speaker_name")
                    if not isinstance(speaker_id, str) or not isinstance(name, str):
                        continue
                    if speaker_id in roster:
                        if isinstance(entry.get("round"), int):
                            roster[speaker_id]["first_round"] = entry["round"]
                        continue
                    item: dict[str, Any] = {"id": speaker_id, "name": name}
                    if isinstance(entry.get("round"), int):
                        item.update(first_round=entry["round"], last_round=entry["round"])
                    if "portrait" in segment:
                        item["portrait"] = deepcopy(segment["portrait"])
                    roster[speaker_id] = item
                    if speaker_id not in order:
                        order.append(speaker_id)
        except module_state.ModuleStateError:
            return {
                "ok": False,
                "error_code": "UNSUPPORTED_STORYTELLING_SCHEMA",
                "error": "剧情模式设置版本不受当前运行时支持",
            }
        speakers = [roster[speaker_id] for speaker_id in order]
        return {"ok": True, "speakers": speakers, "total": len(speakers)}
