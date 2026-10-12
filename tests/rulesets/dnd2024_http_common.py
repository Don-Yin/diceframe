"""dnd2024 HTTP 契约测试共享 harness（m4/m5/m6 抽共享）。

只收敛真正重复的部分：ruleset_gameplay 服务所需的最小 WebAPI shim、
legacy adapter + runtime registry 组装、快速角色构建。各里程碑特有的
路由装配与探针仍留在各自测试文件里。
"""

from __future__ import annotations

from src.engine.game_instance import GameRegistry
from src.rules.rule_system import RuleSystem
from src.rulesets.dnd2024.runtime import Dnd2024Runtime
from src.rulesets.builtin import default_adventure_runtime_requirement
from src.rulesets.legacy_adapter import LegacyRulesetAdapter
from src.rulesets.registry import RulesetRuntimeRegistry
from src.webui.services import adventures, ruleset_gameplay
from src.webui.services._common import _parse_game_key


class GameplayApiShim:
    """走真实 ruleset_gameplay 服务与 HTTP 路由的最小 WebAPI 替身。"""

    def __init__(self, registry: GameRegistry, runtime: Dnd2024Runtime, memory=None):
        self._reg = registry
        self._mem = memory
        self._adventure_loader = runtime._adventure_loader
        self._ruleset_registry = RulesetRuntimeRegistry([LegacyRulesetAdapter(), runtime])
        self._rule = RuleSystem({
            "rule_id": "dnd2024_srd",
            "runtime": {"id": "core:dnd2024", "minimum_version": 1},
        })
        self._adventure_dependencies = adventures.AdventureDependencies(
            adventure_loader=self._adventure_loader,
            list_instances=self._reg.list_all,
            load_rule_by_id=lambda rule_id, _language: (
                self._rule if rule_id == self._rule.rule_id else None
            ),
            ruleset_registry=self._ruleset_registry,
            default_runtime_requirement=default_adventure_runtime_requirement,
        )
        self._gameplay_dependencies = (
            ruleset_gameplay.RulesetGameplayDependencies(
                get_instance=self._reg.get,
                parse_game_key=_parse_game_key,
                load_rule_for_game=self._load_rule_for_game,
                ruleset_registry=self._ruleset_registry,
                resolve_adventure_binding=lambda adventure_id, active_runtime, world_id, language: adventures.resolve_binding_for_runtime(
                    self._adventure_dependencies,
                    adventure_id,
                    active_runtime,
                    world_id,
                    language,
                ),
                save_instance=self._reg.save,
                apply_memory_delta=(
                    memory.apply_delta if memory is not None else None
                ),
            )
        )

    @staticmethod
    def _parse_key(game_key: str):
        return _parse_game_key(game_key)

    def get_game_instance(self, game_key: str):
        return self._reg.get(self._parse_key(game_key))

    def _load_rule_for_game(self, instance):
        del instance
        return self._rule

    async def ruleset_available_actions(
        self, game_key: str, requester_id: str, requester_is_gm: bool = False,
    ):
        return await ruleset_gameplay.available_actions(
            self._gameplay_dependencies,
            game_key,
            requester_id,
            requester_is_gm,
        )

    async def ruleset_submit_intent(
        self, game_key: str, requester_id: str, requester_is_gm: bool, body,
    ):
        return await ruleset_gameplay.submit_intent(
            self._gameplay_dependencies,
            game_key,
            requester_id,
            requester_is_gm,
            body,
        )


def quick_character(
    runtime: Dnd2024Runtime,
    preset_id: str = "stalwart_guardian",
    name: str = "HTTP Test",
) -> dict:
    """用真实 builder 从快速预设生成一个合法角色。"""
    choices = runtime.builder_choices(None, {"locale": "en"})
    preset = next(item for item in choices["quick_presets"] if item["id"] == preset_id)
    return runtime.finalize_character(
        None, {**preset["draft"], "locale": "en", "name": name},
    )
