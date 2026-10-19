from __future__ import annotations

import pytest

from src.engine import module_hooks
from src.engine.game_instance import GameInstance


@pytest.mark.asyncio
async def test_reset_runs_optional_preflight_once_before_rotating_identity():
    instance = GameInstance(game_key=("web", "reset", "bot"))
    run_id = instance.run_id
    calls = []
    owner = "test.reset.once"
    module_hooks.register(module_hooks.INSTANCE_RESET_PREFLIGHT, owner, lambda inst: calls.append(inst.run_id))
    try:
        await instance.reset()
    finally:
        module_hooks.unregister_owner(owner)
    assert calls == [run_id]
    assert instance.run_id != run_id


@pytest.mark.asyncio
async def test_rejected_optional_reset_preflight_changes_nothing():
    instance = GameInstance(game_key=("web", "reset", "bot"))
    before = instance.to_dict()
    owner = "test.reset.reject"
    def reject(_inst):
        raise ValueError("unsupported test slot")
    module_hooks.register(module_hooks.INSTANCE_RESET_PREFLIGHT, owner, reject)
    try:
        with pytest.raises(ValueError, match="unsupported test slot"):
            await instance.reset()
    finally:
        module_hooks.unregister_owner(owner)
    assert instance.to_dict() == before
