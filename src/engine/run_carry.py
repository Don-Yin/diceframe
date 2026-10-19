"""Build a separate paused game from an immutable settled character snapshot."""
from copy import deepcopy
from typing import Any
from uuid import uuid4

from src.engine import module_hooks
from src.engine.game_instance import GameInstance
from src.engine.game_state import GameState
from src.engine.modules import content_binding, game_config, ruleset_runtime, run_finale, skill_growth
from src.rulesets.contracts import RunLifecycleRuntime


def candidate_from_archive(source: Any, actor_uids: list[str], runtime: Any) -> GameInstance:
    archive = run_finale.view(source)['archive']
    skill_growth.require_writable(source)
    if not archive or not actor_uids or len(set(actor_uids)) != len(actor_uids):
        raise ValueError('select at least one settled character exactly once')
    if any(uid not in archive['characters'] for uid in actor_uids):
        raise ValueError('character is not part of this settled run')
    module_hooks.run(module_hooks.INSTANCE_NEW_RUN_PREFLIGHT, source)
    candidate = GameInstance(game_key=('web', f'carry_{uuid4().hex}', 'web_bot'),
                             world_id=source.world_id, world_name=source.world_name,
                             rule_id=source.rule_id, gm_uid=source.gm_uid, language=source.language,
                             group_name=source.group_name)
    ruleset_runtime.copy_binding_for_new_run(candidate, source)
    content_binding.copy_for_new_game(candidate, source)
    module_hooks.run(module_hooks.INSTANCE_NEW_RUN, candidate, source)
    game_config.copy_for_carried_game(candidate, source)
    candidate.replace_players({uid: {'character_name': str(source.players.get(uid, {}).get('character_name') or uid),
                                     'character_sheet': deepcopy(archive['characters'][uid])} for uid in actor_uids})
    if isinstance(runtime, RunLifecycleRuntime):
        runtime.initialize_new_run(candidate, preserve_characters=True)
    if any(candidate.get_character_sheet(uid) != archive['characters'][uid] for uid in actor_uids):
        raise ValueError('runtime cannot carry settled character values without changing them')
    candidate.state = GameState.PAUSED
    return candidate
