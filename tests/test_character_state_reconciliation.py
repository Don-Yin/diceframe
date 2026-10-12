"""PR-A：Live Character State -> Ruleset Reconciliation 边界回归测试。

这一层只验证 seam 本身，不含任何 D&D 规则语义：

- generic mutation 结束后，按角色汇总 changed_domains；
- 同角色同一批状态更新只触发一次 reconciliation；
- 被拒绝的操作、纯读取、纯资源结算都不触发；
- 未实现 hook 的 legacy runtime 行为完全不变；
- reconciliation 失败时回滚该角色本轮的 live 物品变化，
  且不牵连同轮已结算的 HP / 资源。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.commands.game_handler import GameHandler
from src.commands.madness_tracker import MadnessTracker
from src.commands.player_state_applier import PlayerStateApplier
from src.commands.state_update_applier import StateUpdateApplier
from src.engine.game_instance import GameInstance, GameRegistry, GameState
from src.lorebook.matcher import KeywordMatcher
from src.rulesets.contracts import (
    CHARACTER_MUTATION_DOMAINS,
    CharacterStateReconciliationRuntime,
)


class _ReconcilingRuntime:
    """A runtime that opted into the reconciliation contract."""

    runtime_id = "test:reconciling"
    runtime_version = 1

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, frozenset[str]]] = []
        self._fail = fail

    def reconcile_character_state(self, instance, user_id, changed_domains):
        self.calls.append((user_id, changed_domains))
        if self._fail:
            raise RuntimeError("reconciliation exploded")
        return None


class _LegacyRuntime:
    """A runtime that never heard of reconciliation (dnd5e lite / freeform)."""

    runtime_id = "test:legacy"
    runtime_version = 1


class _Registry:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    def resolve(self, template):
        return self._runtime


def _instance() -> GameInstance:
    instance = GameInstance(("web", "reconcile", "bot"))
    instance.state = GameState.ACTIVE_ACTION
    instance.round_number = 1
    instance.players["p1"] = {"character_name": "小林", "character_sheet": {
        "hp": 30, "max_hp": 30,
        "inventory": [], "equipment": [], "key_items": [],
    }}
    instance.players["p2"] = {"character_name": "阿梅", "character_sheet": {
        "hp": 25, "max_hp": 25,
        "inventory": [], "equipment": [], "key_items": [],
    }}
    return instance


def _applier(runtime, monkeypatch) -> StateUpdateApplier:
    applier = StateUpdateApplier(
        Path("."), None, lambda *args, **kwargs: {},
        ruleset_registry=_Registry(runtime) if runtime is not None else None,
    )
    monkeypatch.setattr(
        applier, "_load_rule",
        lambda instance: SimpleNamespace(rule_id="test", template={}),
    )
    return applier


def _owned(name: str, qty: int = 1) -> dict:
    return {"name": name, "qty": qty, "category": "equipment"}


# --------------------------------------------------------------------------
# changed_domains collection
# --------------------------------------------------------------------------

def test_player_state_applier_reports_equipment_and_inventory_domains() -> None:
    instance = _instance()
    instance.players["p1"]["character_sheet"]["inventory"] = [_owned("链甲")]

    changed = PlayerStateApplier(MadnessTracker()).apply_players(
        instance, {"p1": {"equipment_ops": [{"op": "equip", "name": "链甲"}]}},
    )

    assert changed == {"p1": frozenset({"equipment", "inventory"})}


def test_reported_domains_stay_inside_the_declared_vocabulary() -> None:
    instance = _instance()
    instance.players["p1"]["character_sheet"]["inventory"] = [_owned("链甲")]

    changed = PlayerStateApplier(MadnessTracker()).apply_players(
        instance, {"p1": {
            "item_gains": [{"name": "药水", "qty": 2}],
            "equipment_ops": [{"op": "equip", "name": "链甲"}],
        }},
    )

    assert changed
    for domains in changed.values():
        assert domains <= CHARACTER_MUTATION_DOMAINS


def test_pure_resource_settlement_reports_no_domain() -> None:
    """HP 结算不是物品事实变化，本任务不发出 resources 提示。"""

    instance = _instance()

    changed = PlayerStateApplier(MadnessTracker()).apply_players(
        instance, {"p1": {"hp_change": -3}},
    )

    assert changed == {}
    assert instance.get_character_sheet("p1")["hp"] == 27


def test_rejected_equip_reports_no_domain() -> None:
    """装备未拥有的物品被拒绝，不能因此触发无谓的 reconciliation。"""

    instance = _instance()

    changed = PlayerStateApplier(MadnessTracker()).apply_players(
        instance, {"p1": {"equipment_ops": [{"op": "equip", "name": "板甲"}]}},
    )

    assert changed == {}
    assert instance.get_character_sheet("p1")["equipment"] == []


def test_rejected_unequip_and_unknown_item_use_report_no_domain() -> None:
    instance = _instance()

    changed = PlayerStateApplier(MadnessTracker()).apply_players(
        instance, {"p1": {
            "equipment_ops": [{"op": "unequip", "name": "链甲"}],
            "item_uses": [{"name": "不存在的药水"}],
        }},
    )

    assert changed == {}


# --------------------------------------------------------------------------
# reconciliation invocation
# --------------------------------------------------------------------------

def test_equip_triggers_reconciliation_once(monkeypatch) -> None:
    runtime = _ReconcilingRuntime()
    instance = _instance()
    instance.players["p1"]["character_sheet"]["inventory"] = [_owned("链甲")]

    _applier(runtime, monkeypatch).apply_state_update(instance, {
        "players": {"p1": {"equipment_ops": [{"op": "equip", "name": "链甲"}]}},
    })

    assert len(runtime.calls) == 1
    user_id, domains = runtime.calls[0]
    assert user_id == "p1"
    assert domains == frozenset({"equipment", "inventory"})


def test_many_mutations_for_one_player_reconcile_only_once(monkeypatch) -> None:
    """同一轮 获得 -> 装备 -> 卸下 -> 再装备 -> 战利品，只 reconcile 一次。"""

    runtime = _ReconcilingRuntime()
    instance = _instance()
    instance.players["p1"]["character_sheet"]["inventory"] = [_owned("链甲")]

    _applier(runtime, monkeypatch).apply_state_update(instance, {
        "players": {"p1": {
            "item_gains": [{"name": "盾牌", "category": "equipment"}],
            "equipment_ops": [
                {"op": "equip", "name": "链甲"},
                {"op": "equip", "name": "盾牌"},
                {"op": "unequip", "name": "盾牌"},
                {"op": "equip", "name": "盾牌"},
            ],
        }},
        "loot": [{"player": "p1", "item": "治疗药水", "qty": 2}],
    })

    assert len(runtime.calls) == 1
    assert runtime.calls[0][0] == "p1"


def test_each_changed_player_reconciles_once(monkeypatch) -> None:
    runtime = _ReconcilingRuntime()
    instance = _instance()
    for uid in ("p1", "p2"):
        instance.players[uid]["character_sheet"]["inventory"] = [_owned("链甲")]

    _applier(runtime, monkeypatch).apply_state_update(instance, {
        "players": {
            "p1": {"equipment_ops": [{"op": "equip", "name": "链甲"}]},
            "p2": {"equipment_ops": [{"op": "equip", "name": "链甲"}]},
        },
    })

    assert sorted(call[0] for call in runtime.calls) == ["p1", "p2"]


def test_loot_only_round_reports_inventory(monkeypatch) -> None:
    runtime = _ReconcilingRuntime()
    instance = _instance()

    _applier(runtime, monkeypatch).apply_state_update(instance, {
        "loot": [{"player": "p1", "item": "治疗药水", "qty": 1}],
    })

    assert len(runtime.calls) == 1
    assert runtime.calls[0][1] == frozenset({"inventory"})


def test_no_mutation_does_not_reconcile(monkeypatch) -> None:
    runtime = _ReconcilingRuntime()
    instance = _instance()

    _applier(runtime, monkeypatch).apply_state_update(instance, {
        "players": {"p1": {"hp_change": -3}},
    })

    assert runtime.calls == []


def test_read_only_update_does_not_reconcile(monkeypatch) -> None:
    runtime = _ReconcilingRuntime()
    instance = _instance()

    _applier(runtime, monkeypatch).apply_state_update(instance, {})
    _applier(runtime, monkeypatch).apply_state_update(instance, {"scene_change": "铁匠铺"})

    assert runtime.calls == []


def test_legacy_runtime_without_hook_keeps_previous_behaviour(monkeypatch) -> None:
    """dnd5e lite / freeform：没有 hook 就是 no-op，装备照常生效。"""

    instance = _instance()
    instance.players["p1"]["character_sheet"]["inventory"] = [_owned("链甲")]

    _applier(_LegacyRuntime(), monkeypatch).apply_state_update(instance, {
        "players": {"p1": {"equipment_ops": [{"op": "equip", "name": "链甲"}]}},
    })

    sheet = instance.get_character_sheet("p1")
    assert [item["name"] for item in sheet["equipment"]] == ["链甲"]
    assert not isinstance(_LegacyRuntime(), CharacterStateReconciliationRuntime)


def test_missing_registry_keeps_previous_behaviour(monkeypatch) -> None:
    """未注入 registry（旧构造方式）时 reconciliation 整体停用。"""

    instance = _instance()
    instance.players["p1"]["character_sheet"]["inventory"] = [_owned("链甲")]

    _applier(None, monkeypatch).apply_state_update(instance, {
        "players": {"p1": {"equipment_ops": [{"op": "equip", "name": "链甲"}]}},
    })

    assert [i["name"] for i in instance.get_character_sheet("p1")["equipment"]] == ["链甲"]


def test_reconciling_runtime_satisfies_the_protocol() -> None:
    assert isinstance(_ReconcilingRuntime(), CharacterStateReconciliationRuntime)


# --------------------------------------------------------------------------
# failure handling
# --------------------------------------------------------------------------

def test_reconciliation_failure_rolls_back_live_item_changes(monkeypatch) -> None:
    """§66：不允许「装备成功了但规则没看见」的半成功状态继续存在。"""

    runtime = _ReconcilingRuntime(fail=True)
    instance = _instance()
    instance.players["p1"]["character_sheet"]["inventory"] = [_owned("链甲")]

    _applier(runtime, monkeypatch).apply_state_update(instance, {
        "players": {"p1": {"equipment_ops": [{"op": "equip", "name": "链甲"}]}},
    })

    sheet = instance.get_character_sheet("p1")
    assert sheet["equipment"] == []
    assert [item["name"] for item in sheet["inventory"]] == ["链甲"]


def test_reconciliation_failure_keeps_same_round_resource_settlement(monkeypatch) -> None:
    """回滚范围限定在 live 物品字段：同轮扣血不做陪葬。"""

    runtime = _ReconcilingRuntime(fail=True)
    instance = _instance()
    instance.players["p1"]["character_sheet"]["inventory"] = [_owned("链甲")]

    _applier(runtime, monkeypatch).apply_state_update(instance, {
        "players": {"p1": {
            "hp_change": -5,
            "equipment_ops": [{"op": "equip", "name": "链甲"}],
        }},
    })

    sheet = instance.get_character_sheet("p1")
    assert sheet["hp"] == 25
    assert sheet["equipment"] == []


def test_reconciliation_failure_is_isolated_to_the_failing_character(monkeypatch) -> None:
    class _OnlyP1Fails(_ReconcilingRuntime):
        def reconcile_character_state(self, instance, user_id, changed_domains):
            self.calls.append((user_id, changed_domains))
            if user_id == "p1":
                raise RuntimeError("reconciliation exploded")
            return None

    runtime = _OnlyP1Fails()
    instance = _instance()
    for uid in ("p1", "p2"):
        instance.players[uid]["character_sheet"]["inventory"] = [_owned("链甲")]

    _applier(runtime, monkeypatch).apply_state_update(instance, {
        "players": {
            "p1": {"equipment_ops": [{"op": "equip", "name": "链甲"}]},
            "p2": {"equipment_ops": [{"op": "equip", "name": "链甲"}]},
        },
    })

    assert instance.get_character_sheet("p1")["equipment"] == []
    assert [i["name"] for i in instance.get_character_sheet("p2")["equipment"]] == ["链甲"]


def test_runtime_resolution_failure_does_not_break_the_round(monkeypatch) -> None:
    class _BrokenRegistry:
        def resolve(self, template):
            raise ValueError("ruleset runtime is not available")

    instance = _instance()
    instance.players["p1"]["character_sheet"]["inventory"] = [_owned("链甲")]
    applier = StateUpdateApplier(
        Path("."), None, lambda *args, **kwargs: {}, ruleset_registry=_BrokenRegistry(),
    )
    monkeypatch.setattr(
        applier, "_load_rule",
        lambda instance: SimpleNamespace(rule_id="t", template={}),
    )

    applier.apply_state_update(instance, {
        "players": {"p1": {"equipment_ops": [{"op": "equip", "name": "链甲"}]}},
    })

    assert [i["name"] for i in instance.get_character_sheet("p1")["equipment"]] == ["链甲"]


# --------------------------------------------------------------------------
# dependency injection
# --------------------------------------------------------------------------

def test_game_handler_injects_its_own_ruleset_registry(tmp_path) -> None:
    """§14：不允许 StateUpdateApplier 自己再 build 一份 registry。"""

    registry = _Registry(_ReconcilingRuntime())
    handler = GameHandler(
        registry=GameRegistry(tmp_path / "saves"),
        llm_client=SimpleNamespace(),
        lorebook_matcher=KeywordMatcher(),
        ruleset_registry=registry,
    )

    assert handler.ruleset_registry is registry
    assert handler._state_applier._ruleset_registry is registry
