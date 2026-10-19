"""Run-scoped story authority, not narrator-authored quest notes."""
from copy import deepcopy

import pytest

from src.engine.game_instance import GameInstance
from src.engine import module_hooks
from src.engine.modules import run_story


def game():
    inst = GameInstance(('test', 'story'))
    inst.npcs['guide'] = {'name': 'Guide'}
    return inst


def plan():
    return {'format_version': 1, 'theme': 'Investigation', 'party_goal': 'Find the missing scholar',
            'mode': 'guided', 'npc_policy': 'strict', 'core_npcs': ['guide'], 'start': 'station',
            'scenes': [
                {'id': 'station', 'title': 'Station', 'kind': 'transition', 'objective': 'Meet the guide',
                 'description': 'A rainy station', 'public': True, 'exit': 'The party agrees to leave',
                 'next_ids': ['house'], 'hints': ['The guide points to the street', 'A taxi offers a ride']},
                {'id': 'house', 'title': 'SECRET HOUSE', 'kind': 'investigation', 'objective': 'SECRET CLUE',
                 'description': '', 'public': True, 'exit': 'Search the study', 'next_ids': [], 'hints': []}]}


def adopt(inst):
    run_story.adopt(inst, plan(), expected_run=inst.run_id, expected_revision=0, source='gm')


def test_absent_plan_is_read_only_and_not_guessed_from_history():
    inst = game(); inst.modules.pop('run_story', None)
    before = deepcopy(inst.to_dict())
    assert run_story.project(inst, viewer_is_gm=False) == {}
    assert inst.to_dict() == before


def test_future_public_scenes_and_gm_conditions_never_reach_player_context():
    inst = game(); adopt(inst)
    public = run_story.project(inst, viewer_is_gm=False)
    assert public['objectives'][0]['name'] == 'Meet the guide'
    assert 'SECRET' not in str(public) and 'street' not in str(public)
    gm = run_story.project(inst, viewer_is_gm=True)
    assert gm['revision'] == 1 and gm['exit'] == 'The party agrees to leave'
    restored = GameInstance.from_dict(inst.to_dict())
    assert run_story.project(restored, viewer_is_gm=True) == gm


def test_transition_requires_gm_confirmed_existing_round_evidence_and_revision():
    inst = game(); adopt(inst)
    candidate = {'format_version': 1, 'run_id': inst.run_id, 'revision': 1,
                 'from_id': 'station', 'to_id': 'house', 'evidence_rounds': [1]}
    before = deepcopy(inst.to_dict())
    with pytest.raises(ValueError):
        run_story.advance(inst, candidate, confirmed=True)
    assert inst.to_dict() == before
    inst.log.append({'round': 1, 'gm_response': 'The party leaves with the guide'})
    with pytest.raises(PermissionError):
        run_story.advance(inst, candidate, confirmed=False)
    run_story.advance(inst, candidate, confirmed=True)
    assert run_story.project(inst, viewer_is_gm=True)['current_id'] == 'house'
    after = deepcopy(inst.to_dict())
    with pytest.raises(ValueError):
        run_story.advance(inst, candidate, confirmed=True)
    assert inst.to_dict() == after


def test_narrator_proposal_does_not_advance_and_unknown_npc_is_not_registered():
    from src.commands.npc_state_applier import NpcStateApplier
    inst = game(); adopt(inst)
    NpcStateApplier().apply_npcs(inst, {'invented mastermind': {'secret': 'controls the plot'}})
    assert 'invented mastermind' not in inst.npcs
    assert run_story.project(inst, viewer_is_gm=True)['warnings']
    module_hooks.record(inst, 'story_candidate', {'to_id': 'house'})
    assert run_story.project(inst, viewer_is_gm=True)['current_id'] == 'station'


def test_lifecycle_snapshots_stall_hints_and_no_secret_carry_to_new_run():
    inst = game(); adopt(inst)
    module_hooks.run(module_hooks.ROUND_PROCESSING_BEGIN, inst)
    entry = {'round': 1}
    module_hooks.run(module_hooks.ROUND_COMMIT, inst, entry, None)
    module_hooks.run(module_hooks.ROUND_PROCESSING_BEGIN, inst)
    module_hooks.run(module_hooks.ROUND_COMMIT, inst, {'round': 2}, None)
    assert run_story.project(inst, viewer_is_gm=True)['stall_hint']
    module_hooks.run(module_hooks.ROUND_REWIND_RESTORE, inst, entry, 1, module_hooks.REWIND_SOURCE_ROLLBACK)
    assert run_story.project(inst, viewer_is_gm=True)['stalled_rounds'] == 0
    candidate = game()
    module_hooks.run(module_hooks.INSTANCE_NEW_RUN, candidate, inst)
    assert run_story.project(candidate, viewer_is_gm=True) == {}
    module_hooks.run(module_hooks.INSTANCE_RESET, inst)
    assert run_story.project(inst, viewer_is_gm=True) == {}


def test_unknown_module_schema_and_invalid_reference_fail_without_mutation():
    inst = game(); bad = plan(); bad['core_npcs'] = ['not-existing']
    before = deepcopy(inst.to_dict())
    with pytest.raises(ValueError):
        run_story.adopt(inst, bad, expected_run=inst.run_id, expected_revision=0, source='gm')
    assert inst.to_dict() == before
    inst.modules['run_story'] = {'schema_version': 999, 'private': 'opaque'}
    before = deepcopy(inst.to_dict())
    with pytest.raises(ValueError):
        adopt(inst)
    assert inst.to_dict() == before
