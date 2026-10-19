"""Member-safe recovery projections; no entropy or command ledger crosses HTTP."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.engine import module_hooks
from src.engine.game_state import GameState
from src.engine.modules import progression_state, resource_recovery, run_finale, skill_growth
from src.engine.participant_view import Viewer
from src.rulesets.resource_recovery import managed_resources, policy, requirements, skill_value

SOURCE_FIELDS = frozenset({
    'id', 'source_id', 'run_id', 'kind', 'actor_uid', 'healer_uid', 'skill_id',
    'resource_key', 'resource_delta', 'reason', 'origin_id', 'started_tick', 'status',
})
RECEIPT_FIELDS = SOURCE_FIELDS | frozenset({
    'operation_id', 'before', 'after', 'delta', 'rolls', 'success', 'fumble', 'check_id',
    'round', 'time_advanced_minutes',
})


def public_receipt(receipt: dict) -> dict:
    return {key: deepcopy(value) for key, value in receipt.items() if key in RECEIPT_FIELDS}


def eligibility(instance: Any, uid: str) -> str:
    if uid not in instance.players or uid in instance.away_players:
        return '角色必须在场 / Character must be present'
    sheet = instance.get_character_sheet(uid)
    if not instance.is_alive(uid) or ('sanity' in sheet and (type(sheet['sanity']) is not int or sheet['sanity'] <= 0)):
        return '死亡或永久疯狂的角色不能恢复 / Deceased or permanently insane characters cannot recover'
    if type(sheet.get('hp')) is not int or sheet['hp'] <= 0:
        return '角色需要清醒 / Character must be conscious'
    return ''


def blockers(instance: Any) -> list[str]:
    if instance.state == GameState.ENDED or not run_finale.writable(instance):
        return ['对局已结束或正在结团 / Run ended or finale pending']
    if instance.state not in {GameState.ACTIVE_ACTION, GameState.PAUSED}:
        return ['请在行动阶段或暂停时操作 / Use at an action boundary or while paused']
    if instance.round_processing_in_flight() or instance._process_lock.locked():
        return ['请等待本轮处理完成 / Wait for round processing']
    if instance.action_queue or instance.pending_actions or instance.ready_players:
        return ['请先完成或撤回排队中的行动 / Resolve or withdraw queued actions first']
    combat = module_hooks.combat_view(instance)
    if combat['combat_active'] or combat['combat_state'] == 'active':
        return ['请先结束战斗 / Finish combat first']
    # Recovery must not race a pending dice or push/Luck decision. These views
    # are read-only and never create qualifications from narrative output.
    from src.engine import check_decisions
    from src.engine.modules import checks
    if any(row.get('status') in {'pending', 'rolling'} for row in checks.manual_roll_requests(instance)) or check_decisions.pending_any(instance):
        return ['请先完成待处理的检定 / Resolve pending checks first']
    return []


def intermissions(instance: Any) -> list[dict]:
    """Only an existing server settlement after an actually played round."""
    played: list[int] = []
    for entry in instance.log:
        number = entry.get('round') if isinstance(entry, dict) else None
        if isinstance(number, int) and not isinstance(number, bool) and number > 0:
            played.append(number)
    result = []
    for identity, receipt in skill_growth.view(instance)['receipts'].items():
        number = receipt.get('round')
        if (receipt.get('run_id') == instance.run_id and type(number) is int
                and number <= progression_state.round_value(instance) and any(value <= number for value in played)):
            result.append({'id': identity, 'round': number})
    return result


def project(instance: Any, rule: Any, viewer: Viewer) -> dict:
    state = resource_recovery.view(instance)
    selected = policy(rule)
    resources = managed_resources(rule)
    actions = []
    if selected and 'sanity' in resources:
        for kind, amount in (('overnight', '1d6'), ('therapy', '1d3')):
            if kind == 'overnight' and selected['policy'] == 'coc7e_style':
                continue
            contract = requirements(rule, kind)
            actions.append({'id': kind, 'resource_key': 'sanity', 'amount': amount,
                            'duration_minutes': contract['duration']})
    actors = []
    definitions = getattr(rule, 'template', {}).get('skills') or {}
    if selected and not isinstance(definitions, dict):
        raise ValueError('Treatment skill metadata requires a declared object')
    for uid, player in instance.players.items():
        skills = []
        if selected:
            contract = requirements(rule, 'therapy')
            for skill in contract['skills']:
                try:
                    skill_value(rule, instance.get_character_sheet(uid), skill)
                except ValueError:
                    continue
                definition = definitions.get(skill, {})
                if not isinstance(definition, dict):
                    raise ValueError('Treatment skill metadata must be a declared object')
                skills.append({'id': skill, 'name': str(definition.get('name') or skill)})
        reason = eligibility(instance, uid)
        actors.append({'uid': uid, 'name': str(player.get('character_name') or uid),
                       'eligible': not reason, 'reason': reason, 'skills': skills})
    visible = lambda row: viewer.is_gm or row['actor_uid'] == viewer.uid
    return {'ok': True, 'supported': selected is not None and bool(resources),
            'run_id': instance.run_id, 'revision': state['revision'], 'is_gm': viewer.is_gm,
            'policy': selected, 'actions': actions, 'actors': actors,
            'sources': [{key: deepcopy(value) for key, value in row.items() if key in SOURCE_FIELDS}
                        for row in state['sources'].values() if visible(row)],
            'receipts': [public_receipt(row) for row in state['receipts'].values() if visible(row)],
            'intermissions': intermissions(instance) if viewer.is_gm else [],
            'blockers': blockers(instance)}
