"""PR-C：专业角色生命周期不得回滚 live 状态。

`project_legacy()` 按建卡装备包重建整张 legacy 角色卡——这在建卡/导入时是对的，
对已经玩过的角色则是错的：休息或升级会把开卡装备发回来、把卖掉的东西复活、
把花掉的钱补满。

测试矩阵（§53–§57）覆盖真实路径：

    穿戴 -> 存读档 -> 短休 -> 长休 -> 升级 -> 再读档

并明确验证 ownership 的两侧：装备/背包/货币属于 live，绝不回滚；
HP / 生命骰 / 法术位属于规则，休息与升级**必须**能改动它们（§34）。
"""

from __future__ import annotations

import json

import pytest

from src.rulesets.dnd2024.character.reconciliation import (
    LIVE_OWNED_FIELDS,
    merge_live_character_projection,
)
from src.rulesets.dnd2024.runtime import Dnd2024Runtime

from test_dnd2024_live_equipment_reconciliation import _Game


@pytest.fixture(scope="module")
def runtime() -> Dnd2024Runtime:
    return Dnd2024Runtime()


def _geared(runtime: Dnd2024Runtime) -> _Game:
    """A played character: starter armor removed, chain mail + shield bought."""

    game = _Game(runtime)
    game.strip()
    game.buy("Chain Mail")
    game.equip("Chain Mail")
    game.buy("Shield")
    game.equip("Shield")
    assert game.armor_class == 18
    return game


def _names(rows) -> set[str]:
    return {str(row.get("name") or "") for row in rows if isinstance(row, dict)}


def _save_load(sheet: dict) -> dict:
    """存读档：角色卡必须能无损地走一圈 JSON。"""

    return json.loads(json.dumps(sheet, ensure_ascii=False))


def _rest(runtime: Dnd2024Runtime, game: _Game, rest: str) -> None:
    result = runtime.complete_rest(None, game.sheet, rest)
    game.instance.set_character_sheet("p1", result["character"])


def _level_up(runtime: Dnd2024Runtime, game: _Game) -> None:
    advanced = runtime.apply_advancement(None, game.sheet, {})
    game.instance.set_character_sheet("p1", advanced)


# --------------------------------------------------------------------------
# §53 the full lifecycle matrix
# --------------------------------------------------------------------------

def test_gear_and_armor_class_survive_the_whole_lifecycle(runtime) -> None:
    game = _geared(runtime)

    game.instance.set_character_sheet("p1", _save_load(game.sheet))
    assert game.armor_class == 18, "存读档后 AC 不应变化"

    _rest(runtime, game, "short")
    assert game.armor_class == 18, "短休后 AC 不应回滚"
    assert {"Chain Mail", "Shield"} <= _names(game.sheet["equipment"])

    _rest(runtime, game, "long")
    assert game.armor_class == 18, "长休后 AC 不应回滚"
    assert {"Chain Mail", "Shield"} <= _names(game.sheet["equipment"])

    _level_up(runtime, game)
    assert game.armor_class == 18, "升级后 AC 不应回滚"
    assert {"Chain Mail", "Shield"} <= _names(game.sheet["equipment"])

    game.instance.set_character_sheet("p1", _save_load(game.sheet))
    assert game.armor_class == 18
    assert {"Chain Mail", "Shield"} <= _names(game.sheet["equipment"])


@pytest.mark.parametrize("rest", ["short", "long"])
def test_rest_does_not_resurrect_the_creation_equipment(runtime, rest) -> None:
    """§56：卸下/卖掉的开卡装备不能被休息重新发回来。"""

    game = _Game(runtime)
    starter = _names(game.sheet["equipment"])
    game.strip()
    game.sheet["inventory"] = []  # 模拟已全部卖出
    assert _names(game.sheet["equipment"]) == set()

    _rest(runtime, game, rest)

    assert _names(game.sheet["equipment"]) == set()
    assert not (starter & _names(game.sheet["inventory"]))


def test_level_up_does_not_resurrect_the_creation_equipment(runtime) -> None:
    game = _Game(runtime)
    game.strip()
    game.sheet["inventory"] = []

    _level_up(runtime, game)

    assert _names(game.sheet["equipment"]) == set()


# --------------------------------------------------------------------------
# §54 currency
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rest", ["short", "long"])
def test_rest_does_not_refill_the_purse(runtime, rest) -> None:
    game = _geared(runtime)
    game.sheet["gold"] = 3
    game.sheet["currency"] = {"amount": 3}

    _rest(runtime, game, rest)

    assert game.sheet["gold"] == 3
    assert game.sheet["currency"] == {"amount": 3}


def test_level_up_does_not_refill_the_purse(runtime) -> None:
    game = _geared(runtime)
    game.sheet["gold"] = 3
    game.sheet["currency"] = {"amount": 3}

    _level_up(runtime, game)

    assert game.sheet["gold"] == 3
    assert game.sheet["currency"] == {"amount": 3}


# --------------------------------------------------------------------------
# §55 inventory
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rest", ["short", "long"])
def test_rest_keeps_items_gained_in_play(runtime, rest) -> None:
    game = _geared(runtime)
    game.apply({"loot": [{"player": "p1", "item": "治疗药水", "qty": 2}]})
    assert "治疗药水" in _names(game.sheet["inventory"])

    _rest(runtime, game, rest)

    assert "治疗药水" in _names(game.sheet["inventory"])


def test_level_up_does_not_resurrect_a_consumed_item(runtime) -> None:
    game = _geared(runtime)
    game.apply({"loot": [{"player": "p1", "item": "治疗药水", "qty": 1}]})
    game.apply({"players": {"p1": {"item_uses": [{"name": "治疗药水"}]}}})
    consumed = next(
        row for row in game.sheet["inventory"] if row.get("name") == "治疗药水"
    )
    assert int(consumed["qty"]) == 0

    _level_up(runtime, game)

    remaining = [
        int(row.get("qty") or 0)
        for row in game.sheet["inventory"] if row.get("name") == "治疗药水"
    ]
    assert remaining in ([], [0]), "用掉的药水不应在升级后复活"


def test_key_items_survive_a_long_rest(runtime) -> None:
    game = _geared(runtime)
    game.apply({"loot": [
        {"player": "p1", "item": "地窖钥匙", "category": "key_item"},
    ]})
    assert "地窖钥匙" in _names(game.sheet["key_items"])

    _rest(runtime, game, "long")

    assert "地窖钥匙" in _names(game.sheet["key_items"])


# --------------------------------------------------------------------------
# §34 ownership 的另一侧：规则字段必须还能动
# --------------------------------------------------------------------------

def test_a_long_rest_still_heals(runtime) -> None:
    """不能为了保住装备，把 HP 也一起冻结。"""

    game = _geared(runtime)
    canonical_resources = game.canonical["resources"]
    max_hp = int(canonical_resources["max_hp"])
    canonical_resources["hp"] = 1
    game.sheet["hp"] = 1

    _rest(runtime, game, "long")

    assert int(game.canonical["resources"]["hp"]) == max_hp
    assert int(game.sheet["hp"]) == max_hp


def test_level_up_still_advances_the_character(runtime) -> None:
    game = _geared(runtime)
    before_level = int(game.canonical["build"]["level"])
    before_max_hp = int(game.canonical["resources"]["max_hp"])

    _level_up(runtime, game)

    assert int(game.canonical["build"]["level"]) == before_level + 1
    assert int(game.canonical["resources"]["max_hp"]) > before_max_hp
    assert int(game.sheet["level"]) == before_level + 1


# --------------------------------------------------------------------------
# §57 item_grants stays provenance
# --------------------------------------------------------------------------

def test_item_grants_never_restore_gear_to_live_state(runtime) -> None:
    game = _Game(runtime)
    grants = [dict(g) for g in game.canonical["equipment"]["item_grants"]]
    assert grants, "开卡应当留下 provenance"
    game.strip()
    game.sheet["inventory"] = []

    _rest(runtime, game, "long")
    _level_up(runtime, game)

    # provenance 原样保留……
    assert game.canonical["equipment"]["item_grants"] == grants
    # ……但绝不因此把装备发回 live state。
    assert _names(game.sheet["equipment"]) == set()
    assert _names(game.sheet["inventory"]) == set()


# --------------------------------------------------------------------------
# merge helper 本身
# --------------------------------------------------------------------------

def test_merge_prefers_live_fields_and_projection_for_the_rest() -> None:
    current = {
        "inventory": [{"name": "药水"}], "equipment": [{"name": "盾牌"}],
        "key_items": [{"name": "钥匙"}], "currency": {"amount": 7}, "gold": 7,
        "hp": 1, "max_hp": 20,
    }
    projected = {
        "inventory": [{"name": "开卡药水"}], "equipment": [{"name": "开卡皮甲"}],
        "key_items": [], "currency": {"amount": 99}, "gold": 99,
        "hp": 20, "max_hp": 24, "level": 2,
    }

    merged = merge_live_character_projection(current, projected)

    for field in LIVE_OWNED_FIELDS:
        assert merged[field] == current[field], f"{field} 应来自 live 状态"
    # 资源与等级属于规则投影，必须采用新值（§34）。
    assert merged["hp"] == 20
    assert merged["max_hp"] == 24
    assert merged["level"] == 2


def test_merge_does_not_alias_live_containers() -> None:
    """合并结果被后续 reconcile 原地改写，不能反过来污染调用方的输入。"""

    current = {"inventory": [{"name": "药水"}]}
    merged = merge_live_character_projection(current, {"inventory": []})

    merged["inventory"].append({"name": "不该出现"})

    assert _names(current["inventory"]) == {"药水"}


def test_projection_only_fields_are_kept_when_live_state_lacks_them() -> None:
    merged = merge_live_character_projection({}, {"inventory": [{"name": "开卡药水"}]})

    assert _names(merged["inventory"]) == {"开卡药水"}
