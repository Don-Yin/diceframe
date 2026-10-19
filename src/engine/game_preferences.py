"""Compose preference owners without copying state or ruleset mechanics."""
from __future__ import annotations

from typing import Any

from src.engine import check_decisions, module_hooks
from src.engine.game_state import GameState
from src.game_preferences import validate_preferences
from src.rulesets.contracts import LiveAdvancementPolicyRuntime


def supports_push(rule: Any) -> bool:
    return bool(rule is not None and rule.template.get('pushed_rolls')
                and rule.advantage_mechanic.get('type') == 'coc_bonus_penalty')


def project(instance: Any, runtime: Any = None) -> dict:
    narrative = module_hooks.narration_preferences(instance)
    presentation = module_hooks.check_presentation(instance)
    result = {
        'push_enabled': module_hooks.ask(module_hooks.STATE_READ, instance, module_hooks.PUSH_ENABLED, default=True),
        'quick_actions_enabled': module_hooks.ask(module_hooks.STATE_READ, instance, module_hooks.QUICK_ACTIONS_ENABLED, default=True),
        'dice_reveal_mode': presentation['dice_reveal_mode'],
        'luck_timeout_seconds': presentation['luck_timeout_seconds'],
        'narrative_perspective': narrative['narrative_perspective'],
        'gm_style_override': narrative['gm_style_override'],
        'story_mode': module_hooks.ask(module_hooks.STATE_READ, instance, module_hooks.STORY_MODE, default='prose'),
    }
    if isinstance(runtime, LiveAdvancementPolicyRuntime):
        policy = runtime.live_advancement_policy(instance)
        result.update(advancement_mode=policy['mode'], advancement_authority=policy['authority'])
    return validate_preferences(result, partial=True)


def apply(instance: Any, raw: Any, runtime: Any = None) -> list[str]:
    """Caller stages/publishes atomically; this function never saves or resumes."""
    values = validate_preferences(raw, partial=True)
    if 'quick_actions_enabled' in values:
        module_hooks.preflight(instance, module_hooks.QUICK_ACTIONS_ENABLED)
        module_hooks.record(instance, module_hooks.QUICK_ACTIONS_ENABLED, values['quick_actions_enabled'])
    if 'push_enabled' in values:
        module_hooks.preflight(instance, module_hooks.PUSH_ENABLED)
        module_hooks.record(instance, module_hooks.PUSH_ENABLED, values['push_enabled'])
    presentation = {key: values[key] for key in ('dice_reveal_mode', 'luck_timeout_seconds', 'narrative_perspective') if key in values}
    instance.configure_session(**presentation)
    if 'gm_style_override' in values:
        instance.set_gm_style_override(values['gm_style_override'])
    if 'story_mode' in values:
        if values['story_mode'] != module_hooks.ask(module_hooks.STATE_READ, instance, module_hooks.STORY_MODE, default='prose'):
            if instance.state == GameState.ACTIVE_JUDGMENT:
                raise ValueError('Story mode cannot change during round judgment')
            module_hooks.record(instance, module_hooks.STORY_MODE, values['story_mode'])
    if isinstance(runtime, LiveAdvancementPolicyRuntime) and any(key in values for key in ('advancement_mode', 'advancement_authority')):
        current = runtime.live_advancement_policy(instance)
        runtime.configure_live_advancement(instance, values.get('advancement_mode', current['mode']),
                                           values.get('advancement_authority', current['authority']))
    return check_decisions.close_disabled(instance) if values.get('push_enabled') is False else []
