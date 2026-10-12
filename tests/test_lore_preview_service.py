"""knowledge preview 服务测试：视角解析、错误路径与投影负载。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.webui.services.knowledge import (
    LorePreviewDependencies,
    LorePreviewService,
)


class _FakeLoreStore:
    def __init__(self) -> None:
        self.worlds = {"w1": {"id": "w1", "name": "测试世界"}}
        self.entries = [
            {"id": "a", "world_id": "w1", "visible_to": ["public"]},
            {"id": "b", "world_id": "w1", "visible_to": "莱拉"},
            {"id": "c", "world_id": "w1", "visible_to": []},
        ]

    def get_world(self, world_id: str):
        return self.worlds.get(world_id)

    def list_entries(self, world_id: str, entry_type=None):
        if world_id not in self.worlds:
            return []
        return list(self.entries)


def _make_service(players: dict | None = None) -> LorePreviewService:
    instance = SimpleNamespace(players=players or {})
    registry = SimpleNamespace(get=lambda _key: instance if players is not None else None)
    return LorePreviewService(LorePreviewDependencies(
        lorebook=_FakeLoreStore(),
        get_instance=registry.get,
        parse_game_key=lambda key: (key,),
    ))


def test_invalid_viewer_returns_400() -> None:
    result = _make_service(None).preview("w1", "")
    assert result["status"] == 400
    assert result["payload"]["code"] == "INVALID_VIEWER"


def test_unknown_world_returns_404() -> None:
    result = _make_service(None).preview("missing", "gm")
    assert result["status"] == 404
    assert result["payload"]["code"] == "WORLD_NOT_FOUND"


def test_character_viewer_requires_game_key() -> None:
    result = _make_service(None).preview("w1", "u1")
    assert result["status"] == 400
    assert result["payload"]["code"] == "INVALID_VIEWER"


def test_character_viewer_unknown_game_returns_404() -> None:
    result = _make_service(None).preview("w1", "u1", "g-missing")
    assert result["status"] == 404
    assert result["payload"]["code"] == "GAME_NOT_FOUND"


def test_character_viewer_not_in_game_returns_403() -> None:
    service = _make_service({"u1": {"user_id": "u1", "character_name": "莱拉"}})
    result = service.preview("w1", "uX", "g1")
    assert result["status"] == 403
    assert result["payload"]["code"] == "PLAYER_NOT_IN_GAME"


def test_gm_viewer_sees_all_entries() -> None:
    result = _make_service(None).preview("w1", "gm")
    assert result["status"] == 200
    payload = result["payload"]
    assert payload["ok"] is True
    assert payload["viewer"] == {"kind": "gm", "uid": "", "name": ""}
    assert payload["summary"] == {
        "total": 3,
        "visible": 3,
        "public": 1,
        "character_only": 1,
        "gm_secret": 1,
    }
    assert all(p["visible"] for p in payload["projections"].values())


def test_party_viewer_sees_only_public_entries() -> None:
    result = _make_service(None).preview("w1", "party")
    payload = result["payload"]
    assert payload["summary"]["visible"] == 1
    assert payload["projections"]["a"]["visible"] is True
    assert payload["projections"]["b"]["visible"] is False
    assert payload["projections"]["c"]["visible"] is False


def test_character_viewer_derives_name_from_instance() -> None:
    service = _make_service({"u1": {"user_id": "u1", "character_name": "莱拉"}})
    result = service.preview("w1", "u1", "g1")
    assert result["status"] == 200
    payload = result["payload"]
    assert payload["viewer"] == {"kind": "character", "uid": "u1", "name": "莱拉"}
    visible = {k for k, p in payload["projections"].items() if p["visible"]}
    assert visible == {"a", "b"}


def test_character_viewer_falls_back_to_uid_without_name() -> None:
    service = _make_service({"u1": {"user_id": "u1"}})
    result = service.preview("w1", "u1", "g1")
    assert result["status"] == 200
    assert result["payload"]["viewer"]["name"] == "u1"
