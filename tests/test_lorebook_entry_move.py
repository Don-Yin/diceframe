"""§12 支撑能力 — canonical entry 跨 Book 移动。

粗粒度批量操作（bulk move）需要一个后端能力：把条目从一个 Book 移到另一个 Book，
同时**保持同一个 canonical entry.id**（避免 id 变动破坏引用），并让两个 Book 的
revision 都 +1（否则各自的 matcher 缓存指纹不会失效）。
"""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.lorebook.store import LorebookStore
from src.webui.api import WebAPI
from src.webui.routes.lorebooks import register_lorebooks


@pytest.fixture()
def store(tmp_path):
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    store.create_lorebook({"id": "b1", "name": "One"})
    store.create_lorebook({"id": "b2", "name": "Two"})
    store.add_entry({
        "id": "e1", "book_id": "b1", "name": "E", "content": "c", "keywords": ["k"],
    })
    try:
        yield store
    finally:
        store.close()


def _api(store: LorebookStore) -> WebAPI:
    api = WebAPI.__new__(WebAPI)
    api._lore = store
    return api


# ---- store 层 --------------------------------------------------------------


def test_move_entry_keeps_canonical_id_and_bumps_both_revisions(store):
    r1 = store.get_lorebook("b1")["revision"]
    r2 = store.get_lorebook("b2")["revision"]

    assert store.move_entry("b1", "b2", "e1") is True

    moved = store.get_entry("e1")
    assert moved["id"] == "e1", "canonical id 必须保持不变"
    assert moved["book_id"] == "b2"
    assert store.list_book_entries("b1") == []
    assert [e["id"] for e in store.list_book_entries("b2")] == ["e1"]
    # 两边都要失效缓存，否则源 Book 仍会匹配到已移走的条目。
    assert store.get_lorebook("b1")["revision"] == r1 + 1
    assert store.get_lorebook("b2")["revision"] == r2 + 1


def test_move_entry_enforces_ownership_and_target_existence(store):
    # 条目不在源 Book：拒绝，且不做任何改动。
    assert store.move_entry("b2", "b1", "e1") is False
    assert store.get_entry("e1")["book_id"] == "b1"
    # 目标 Book 不存在：拒绝。
    assert store.move_entry("b1", "nope", "e1") is False
    assert store.get_entry("e1")["book_id"] == "b1"
    # 空 id：拒绝。
    assert store.move_entry("", "b2", "e1") is False
    assert store.move_entry("b1", "", "e1") is False


def test_move_entry_to_the_same_book_is_a_noop_but_still_validates(store):
    assert store.move_entry("b1", "b1", "e1") is True
    assert store.get_entry("e1")["book_id"] == "b1"
    assert store.move_entry("b2", "b2", "e1") is False


# ---- API 层 ----------------------------------------------------------------


def test_api_move_entry_reports_explicit_error_codes(store):
    api = _api(store)

    missing_book = api.move_lorebook_entry("nope", "e1", "b2")
    assert missing_book["ok"] is False and missing_book["error_code"] == "book_not_found"

    missing_target = api.move_lorebook_entry("b1", "e1", "nope")
    assert missing_target["ok"] is False
    assert missing_target["error_code"] == "target_book_not_found"

    not_owned = api.move_lorebook_entry("b2", "e1", "b1")
    assert not_owned["ok"] is False
    assert not_owned["error_code"] == "entry_book_mismatch", (
        "条目存在但不属于这个 Book：是所有权冲突，不是 404"
    )

    ok = api.move_lorebook_entry("b1", "e1", "b2")
    assert ok["ok"] is True
    assert ok["entry_id"] == "e1" and ok["book_id"] == "b2"
    assert ok["entry"]["book_id"] == "b2"


# ---- 路由层 ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_move_route_maps_errors_to_404_and_409(store):
    app = web.Application()
    app["api"] = _api(store)
    register_lorebooks(app)

    async with TestClient(TestServer(app)) as client:
        # 源 Book 不存在 -> 404
        response = await client.post(
            "/api/lorebooks/nope/entries/e1/move", json={"target_book_id": "b2"},
        )
        assert response.status == 404

        # 条目不属于 URL 里的 Book -> 409（所有权隔离）
        response = await client.post(
            "/api/lorebooks/b2/entries/e1/move", json={"target_book_id": "b1"},
        )
        assert response.status == 409

        # 成功 -> 200，且 canonical id 不变
        response = await client.post(
            "/api/lorebooks/b1/entries/e1/move", json={"target_book_id": "b2"},
        )
        assert response.status == 200
        body = await response.json()
        assert body["ok"] is True and body["entry_id"] == "e1"
        assert store.get_entry("e1")["book_id"] == "b2"


@pytest.mark.asyncio
async def test_move_route_rejects_a_non_object_body(store):
    app = web.Application()
    app["api"] = _api(store)
    register_lorebooks(app)

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/lorebooks/b1/entries/e1/move", json=["not", "an", "object"],
        )
        assert response.status == 400
