from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.rules.rule_system import RuleSystem
from src.rulesets.dnd2024.runtime import Dnd2024Runtime
from src.rulesets.legacy_adapter import LegacyRulesetAdapter
from src.rulesets.registry import RulesetRuntimeRegistry
from src.webui.routes.rules import register_rules
from src.webui.services import ruleset_advancement, ruleset_rest

from dnd2024_http_common import quick_character


class _M4Api:
    def __init__(self, runtime: Dnd2024Runtime):
        self._ruleset_registry = RulesetRuntimeRegistry([LegacyRulesetAdapter(), runtime])
        self._professional_rule = RuleSystem({
            "rule_id": "test_dnd2024",
            "runtime": {"id": "core:dnd2024", "minimum_version": 1},
        })
        self._legacy_rule = RuleSystem({"rule_id": "legacy"})
        self._ruleset_rest_dependencies = ruleset_rest.RulesetRestDependencies(
            load_rule_by_id=self._load_rule_by_id,
            ruleset_registry=self._ruleset_registry,
        )
        self._ruleset_advancement_dependencies = (
            ruleset_advancement.RulesetAdvancementDependencies(
                load_rule_by_id=self._load_rule_by_id,
                ruleset_registry=self._ruleset_registry,
            )
        )

    def _load_rule_by_id(self, rule_id: str, language: str = ""):
        del language
        return {
            "test_dnd2024": self._professional_rule,
            "legacy": self._legacy_rule,
        }.get(rule_id)

    def ruleset_progression(
        self, rule_id: str, class_ref: str, start_level: int = 1,
        end_level: int = 20, language: str = "",
    ):
        return ruleset_advancement.progression(
            self._ruleset_advancement_dependencies,
            rule_id, class_ref, start_level, end_level, language,
        )

    def ruleset_advancement_preview(self, rule_id: str, body, language: str = ""):
        return ruleset_advancement.preview(
            self._ruleset_advancement_dependencies, rule_id, body, language,
        )

    def ruleset_advancement_apply(self, rule_id: str, body, language: str = ""):
        return ruleset_advancement.apply(
            self._ruleset_advancement_dependencies, rule_id, body, language,
        )

    def ruleset_rest_resolve(self, rule_id: str, body, language: str = ""):
        return ruleset_rest.resolve(
            self._ruleset_rest_dependencies, rule_id, body, language,
        )


def _quick_fighter(runtime: Dnd2024Runtime) -> dict:
    return quick_character(runtime, "stalwart_guardian", "HTTP M4")


@pytest.mark.asyncio
async def test_m4_stateless_http_contracts_and_legacy_boundary() -> None:
    runtime = Dnd2024Runtime()
    character = _quick_fighter(runtime)
    app = web.Application()
    app["api"] = _M4Api(runtime)
    register_rules(app)

    async with TestClient(TestServer(app)) as client:
        progression_response = await client.get(
            "/api/rules/test_dnd2024/progression",
            params={"class_ref": "class:fighter", "start_level": 1, "end_level": 2},
        )
        progression = await progression_response.json()
        preview_response = await client.post(
            "/api/rules/test_dnd2024/advancement/preview",
            json={"character": character, "choices": {}},
        )
        preview = await preview_response.json()
        rest_response = await client.post(
            "/api/rules/test_dnd2024/rest/resolve",
            json={"character": character, "rest": "short", "hit_die_rolls": {}},
        )
        rest = await rest_response.json()
        legacy_response = await client.post(
            "/api/rules/legacy/advancement/preview",
            json={"character": character, "choices": {}},
        )
        legacy = await legacy_response.json()

    assert progression_response.status == 200
    assert [row["level"] for row in progression["progression"]] == [1, 2]
    assert preview_response.status == 200
    assert preview["advancement"]["ok"] is True
    assert preview["advancement"]["to_level"] == 2
    assert rest_response.status == 200
    assert rest["rest"] == "short"
    assert legacy_response.status == 422
    assert legacy["code"] == "RULESET_ADVANCEMENT_UNAVAILABLE"
