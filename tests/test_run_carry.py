from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from src.engine.game_instance import GameInstance, GameState
from src.engine.modules import run_finale
from tests.test_run_story_service import setup, GM, PLAYER


@pytest.mark.asyncio
async def test_settled_characters_carry_to_separate_game_once_without_old_secrets_or_tokens():
    service, inst, save, _ = setup()
    prepared = await service.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    job = prepared['finale']['id']; body = {'run_id': inst.run_id, 'job_id': job, 'job_revision': 0, 'epilogue': 'End', 'recap': 'All'}
    await service.mutate('key', GM, 'materials', body)
    await service.mutate('key', GM, 'commit', {**body, 'job_revision': 1, 'confirmed': True})
    archive = deepcopy(run_finale.view(inst)['archive'])
    created = {}
    service.deps = replace(service.deps,
        get_instance=lambda key: inst if key == 'key' else created.get(key),
        register_instance=lambda candidate: created.setdefault('|'.join(candidate.game_key), candidate))
    carry = {'run_id': inst.run_id, 'delivery_id': 'next-adventure'}
    assert not (await service.mutate('key', PLAYER, 'carry', carry))['ok']
    result = await service.mutate('key', GM, 'carry', carry)
    assert result['ok']
    next_game = created[result['game_key']]
    assert next_game.run_id != inst.run_id and next_game.game_key != inst.game_key
    assert next_game.get_character_sheet('alice') == archive['characters']['alice']
    assert not next_game.log and not next_game.npcs
    assert next_game.state == GameState.PAUSED
    assert next_game.modules['run_story']['plan'] is None
    assert run_finale.view(next_game)['archive'] is None
    assert run_finale.view(inst)['archive'] == archive
    assert (await service.mutate('key', GM, 'carry', carry))['game_key'] == result['game_key']
    assert len(created) == 1


@pytest.mark.asyncio
async def test_carry_delivery_recovers_after_second_store_failure():
    service, inst, save, _ = setup()
    result = await service.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    job = result['finale']['id']; body = {'run_id': inst.run_id, 'job_id': job, 'job_revision': 0, 'epilogue': 'End', 'recap': 'All'}
    await service.mutate('key', GM, 'materials', body); await service.mutate('key', GM, 'commit', {**body, 'job_revision': 1, 'confirmed': True})
    created = {}
    service.deps = replace(service.deps, get_instance=lambda key: inst if key == 'key' else created.get(key),
                           register_instance=lambda candidate: created.setdefault('|'.join(candidate.game_key), candidate))
    call_count = 0
    async def fail_candidate(candidate):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError('second store unavailable')
    save.side_effect = fail_candidate
    carry = {'run_id': inst.run_id, 'delivery_id': 'retry-next'}
    assert not (await service.mutate('key', GM, 'carry', carry))['ok']
    pending = deepcopy(run_finale.view(inst)['deliveries']['retry-next'])
    save.side_effect = None
    result = await service.mutate('key', GM, 'carry', carry)
    assert result['ok'] and result['game_key'] == '|'.join(pending['candidate']['game_key'])
    assert inst.state == GameState.ENDED and len(created) == 1
