"""前后端契约快照：后端关键端点返回的顶层字段必须被前端 types.ts 显式声明。

防止"后端加字段、前端漏改"导致的静默 undefined 漂移（types.ts 的 index
signature 会让 TS 永不报错，契约测试兜住）。

后端字段来自**真实调用** WebAPI.create_game 的运行时返回（覆盖多人/单人的
密码分支并集）——内部实现重构（拆变量、提函数、早退分支）都不影响结果；
前端字段来自 types.ts 这一公开契约面本身。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from webapi_harness import web_api, write_world  # noqa: F401  # pytest fixture

ROOT = Path(__file__).resolve().parents[1]


def _ts_interface_fields(path: Path, name: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"export interface {name} \{{(.*?)\n\}}", text, re.S)
    if not m:
        raise AssertionError(f"前端未找到 interface {name}")
    fields = set(re.findall(r"^\s{2}(\w+)\??:", m.group(1), re.M))
    fields.discard("key")  # [key: string] index signature
    return fields


@pytest.mark.asyncio
async def test_create_game_contract_snapshot(web_api):
    """create_game 运行时返回的顶层 key 并集 ⊆ 前端 GameMutationResponse 显式声明。"""
    api, _lorebook, _registry, _fake_llm, worlds_dir = web_api
    players = [{
        "character_name": "艾琳",
        "race": "精灵",
        "class": "游侠",
        "attributes": {"str": 12},
        "background": "来自银叶林地",
    }]

    party = await api.create_game(
        "template_world", "多人测试局",
        narrative_perspective="third_person", players=[dict(players[0])],
    )
    assert party["ok"] is True, party

    write_world(worlds_dir, "solo_world", starter_lorebook=[])
    solo = await api.create_game("solo_world", "单人测试局", players=[dict(players[0])], solo=True)
    assert solo["ok"] is True, solo

    backend_keys: set[str] = set(party) | set(solo)
    frontend = _ts_interface_fields(
        ROOT / "frontend-v2" / "src" / "api" / "types.ts", "GameMutationResponse"
    )
    missing = [k for k in sorted(backend_keys) if k not in frontend]
    assert not missing, (
        f"后端 create_game 返回了前端 GameMutationResponse 未声明的字段: {missing}\n"
        f"请在 frontend-v2/src/api/types.ts 补声明，否则前端会静默拿到 undefined。"
    )


def test_ts_interface_fields_extractor():
    """提取器自身冒烟：应抓到 GameMutationResponse 的已知字段。"""
    frontend = _ts_interface_fields(
        ROOT / "frontend-v2" / "src" / "api" / "types.ts", "GameMutationResponse"
    )
    for key in ("ok", "game_key", "world_name", "generated_password", "players"):
        assert key in frontend, f"前端 GameMutationResponse 应声明 {key}"
