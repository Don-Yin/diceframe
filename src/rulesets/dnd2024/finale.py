"""D&D end-of-run audit; existing reward/level authorities remain exclusive."""
from copy import deepcopy
from typing import Any

from src.engine.modules import ruleset_runtime
from src.rulesets.dnd2024 import advancement_access


def preflight(instance: Any) -> list[str]:
    state = ruleset_runtime.state(instance)
    rest = state.get('rest_session') or {}
    problems = []
    if rest.get('status') == 'collecting':
        problems.append('rest: finish or cancel the shared rest session')
    campaign = state.get('campaign') or {}
    if any(proposal.get('status') == 'pending' for proposal in (campaign.get('proposals') or {}).values()):
        problems.append('campaign_proposals: resolve outstanding campaign proposals')
    if (campaign.get('party_decision') or {}).get('status') == 'open':
        problems.append('party_decision: finish or cancel the current shared decision')
    if (state.get('encounter_request') or {}).get('status') == 'pending':
        problems.append('encounter: resolve or cancel the requested encounter')
    if any(row['entitled'] for row in advancement_access.project(instance)['players']):
        problems.append('advancement: complete pending level choices')
    return problems


def settle(instance: Any, receipt_id: str) -> dict[str, Any]:
    problems = preflight(instance)
    if problems:
        raise ValueError('; '.join(problems))
    return {'receipt_id': receipt_id, 'status': 'audited_existing_rewards',
            'extra_xp': 0, 'extra_loot': [], 'advancement': deepcopy(advancement_access.project(instance))}
