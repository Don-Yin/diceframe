"""Exercise neutral packages through real creation, commands and lifecycle owners."""
from pathlib import Path
import shutil

import pytest

from src.engine.game_instance import GameInstance
from src.engine.modules import adventure_runtime_state
from tests.test_webui_create_flow import web_api  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize('rule_id', ['freeform_fantasy', 'freeform_coc'])
async def test_neutral_adventure_creates_plays_restores_and_restarts_with_legacy_rules(web_api, rule_id):
    api, _lorebook, registry, _llm, _worlds = web_api
    if rule_id == 'freeform_coc':
        shutil.copyfile(Path('templates/rules/freeform_coc.json'), api._rules_dir / 'freeform_coc.json')
        shutil.copyfile(Path('templates/rules/intents_base.json'), api._rules_dir / 'intents_base.json')
    created_package = api.create_adventure({'directory_id': f'shared_{rule_id}', 'name': 'Shared story'}, 'en')
    game = await api.create_game('template_world', rule_id=rule_id, gm_uid='gm',
                                 adventure_id=created_package['adventure_id'], play_mode='adventure',
                                 language='en', players=[{'user_id': 'gm', 'character_name': 'Investigator', 'attributes': {'str': 10}}])
    assert game['ok'], game
    key = game['game_key']
    instance = registry.get(tuple(key.split('|')))
    assert adventure_runtime_state.progress(instance)['active_nodes'] == ['opening']
    result = await api.ruleset_submit_intent(key, 'gm', True, {'type': 'adventure.node.complete', 'node_id': 'opening'})
    assert result['ok'], result
    saved = GameInstance.from_dict(instance.to_dict())
    assert adventure_runtime_state.progress(saved)['completed_nodes'] == ['opening']
    old_run = instance.run_id
    reset = await api.reset_game(key)
    assert reset['ok'], reset
    fresh = registry.get(tuple(key.split('|')))
    assert fresh.run_id != old_run
    assert fresh.adventure_binding == saved.adventure_binding
    assert adventure_runtime_state.progress(fresh)['active_nodes'] == ['opening']
    assert adventure_runtime_state.progress(fresh)['completed_nodes'] == []
