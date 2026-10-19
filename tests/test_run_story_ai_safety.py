from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.engine.modules import run_finale
from tests.test_run_story_service import setup, GM


@pytest.mark.asyncio
async def test_whole_run_ai_uses_every_public_round_without_private_sources_or_old_recap_cutoff():
    from tests.test_run_story import adopt
    service, inst, _, model = setup()
    adopt(inst)
    for number in range(1, 151):
        inst.log.append({'round': number, 'gm_response': f'PUBLIC EVENT {number}: ' + 'x' * 250,
                         'actions': [{'user_id': 'alice', 'text': f'Public action {number}'}],
                         'story_recaps': [{'text': 'Earlier incremental recap'}],
                         'pre_state_snapshot': {'secret': 'SNAPSHOT SECRET'},
                         'private_messages': {'alice': 'ACTOR PRIVATE SECRET'}})
    prepared = await service.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    job = prepared['finale']['id']
    seen = []
    async def respond(**kwargs):
        seen.append(kwargs['user_message'])
        text = '{"epilogue":"Established ending","recap":"Whole-run recap"}' if 'Return JSON' in kwargs['system_prompt'] else 'Public segment summary with source rounds.'
        return SimpleNamespace(content=text, total_tokens=20)
    model.call.side_effect = respond
    result = await service.generate('key', GM, 'finale', {'run_id': inst.run_id, 'job_id': job, 'token_consent': True}, AsyncMock())
    source = '\n'.join(seen)
    assert 'PUBLIC EVENT 1:' in source and 'PUBLIC EVENT 150:' in source
    assert 'SNAPSHOT SECRET' not in source and 'ACTOR PRIVATE SECRET' not in source
    assert 'Meet the guide' in source and 'SECRET HOUSE' not in source and 'SECRET CLUE' not in source
    assert len(seen) > 2 and result['usage']['calls'] == len(seen)
    assert run_finale.view(inst)['archive'] is None
    assert run_finale.view(inst)['job']['epilogue'] == ''  # reviewable draft only


@pytest.mark.asyncio
async def test_finale_save_failure_never_publishes_ended_or_settlement_results():
    service, inst, save, _ = setup()
    prepared = await service.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    body = {'run_id': inst.run_id, 'job_id': prepared['finale']['id'], 'job_revision': 0, 'epilogue': 'End', 'recap': 'All'}
    await service.mutate('key', GM, 'materials', body)
    before = deepcopy(inst.to_dict()); save.side_effect = OSError('disk full')
    result = await service.mutate('key', GM, 'commit', {**body, 'job_revision': 1, 'confirmed': True})
    assert not result['ok'] and inst.to_dict() == before


@pytest.mark.asyncio
async def test_hierarchical_recap_never_drops_the_tail_of_long_segment_summaries():
    service, inst, _, model = setup()
    inst.log = [{'round': number, 'gm_response': f'PUBLIC ROUND {number} ' + 'x' * 8900}
                for number in range(1, 8)]
    prepared = await service.mutate('key', GM, 'prepare', {'run_id': inst.run_id})
    segment_tails = []
    reduction_inputs = []

    async def respond(**kwargs):
        prompt = kwargs['user_message']
        if 'Return JSON' in kwargs['system_prompt']:
            text = '{"epilogue":"End","recap":"All segments"}'
        elif 'Summarize these segment summaries' in kwargs['system_prompt'] or 'PUBLIC ROUND' not in prompt:
            reduction_inputs.append(prompt)
            text = 'Reduced complete summary'
        else:
            marker = f'SEGMENT_TAIL_{len(segment_tails)}'
            segment_tails.append(marker)
            text = 's' * (11000 - len(marker)) + marker
        return SimpleNamespace(content=text, total_tokens=20)

    model.call.side_effect = respond
    result = await service.generate('key', GM, 'finale', {
        'run_id': inst.run_id, 'job_id': prepared['finale']['id'], 'token_consent': True,
    }, AsyncMock())
    assert result['ok'] and len(segment_tails) >= 4
    combined = '\n'.join(reduction_inputs)
    assert all(marker in combined for marker in segment_tails)
    assert max(map(len, reduction_inputs)) <= 24001
