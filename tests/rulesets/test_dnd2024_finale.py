from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.engine.game_state import GameState
from src.engine.modules import run_finale
from src.engine.run_carry import candidate_from_archive
from src.rulesets.dnd2024 import advancement_access
from src.rulesets.dnd2024.runtime import Dnd2024Runtime
from src.webui.services.run_story import RunStoryDependencies, RunStoryService
from tests.test_run_story_service import GM
from test_dnd2024_live_equipment_reconciliation import _Game


@pytest.mark.asyncio
async def test_professional_dnd_finale_preserves_live_character_and_awards_nothing_twice():
    runtime = Dnd2024Runtime()
    game = _Game(runtime)
    inst = game.instance
    inst.rule_id = 'dnd2024_srd'
    inst.gm_uid = 'gm'
    assert inst.bind_ruleset_runtime(inst.get_character_sheet('p1')['rule_binding'])
    runtime.initialize_new_run(inst, preserve_characters=True)
    game.buy('Chain Mail')
    game.equip('Chain Mail')
    original = deepcopy(inst.get_character_sheet('p1'))
    service = RunStoryService(RunStoryDependencies(lambda _: inst, AsyncMock(),
        lambda _: SimpleNamespace(growth_system='xp_level', template={}), lambda _: runtime, lambda: None))
    policy_before = advancement_access.snapshot(inst)
    advancement_access.grant(inst, 'p1', source='gm')
    denied = await service.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    assert not denied['ok'] and 'advancement' in denied['error']
    advancement_access.restore(inst, policy_before)
    prepared = await service.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    assert prepared['ok']
    body = {'run_id': inst.run_id, 'job_id': prepared['finale']['id'], 'job_revision': 0,
            'epilogue': 'Established ending', 'recap': 'Public recap'}
    assert (await service.mutate('key', GM, 'materials', body))['ok']
    committed = await service.mutate('key', GM, 'commit', {**body, 'job_revision': 1, 'confirmed': True})
    assert committed['ok'] and inst.state == GameState.ENDED
    assert inst.get_character_sheet('p1') == original
    receipt = run_finale.view(inst)['archive']['receipt']['ruleset']
    assert receipt['extra_xp'] == 0 and receipt['extra_loot'] == []
    carried = candidate_from_archive(inst, ['p1'], runtime)
    assert carried.get_character_sheet('p1') == original and carried.state == GameState.PAUSED
    assert not advancement_access.project(carried)['players'][0]['entitled']
