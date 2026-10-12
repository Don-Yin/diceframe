"""Versioned runtimes must supply the identity used before game state writes."""

def test_all_versioned_runtimes_supply_game_binding():
    from src.rulesets.builtin import build_default_ruleset_registry
    from src.rulesets.contracts import VersionedStateRuntime

    registry = build_default_ruleset_registry()
    for runtime_id in registry.runtime_ids():
        runtime = registry.get(runtime_id)
        if runtime.capabilities.versioned_state:
            assert isinstance(runtime, VersionedStateRuntime), runtime_id
