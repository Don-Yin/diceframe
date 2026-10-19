"""Read-only, GM-authorized bridge from a run plan to the content review owner."""
from __future__ import annotations

from typing import Any, Callable

from src.adventures.story_draft import from_plan
from src.engine.modules import run_story
from src.engine.participant_view import Viewer
from src.webui.services.adventures import validate_directory_id


async def prepare(get_instance: Callable[[str], Any], reviewer: Callable[[dict], dict] | None,
                  key: str, viewer: Viewer, body: Any) -> dict:
    if not viewer.is_gm:
        raise PermissionError('GM only')
    if reviewer is None:
        raise ValueError('Adventure draft review is unavailable')
    if not isinstance(body, dict):
        raise ValueError('Adventure draft request must be an object')
    directory = validate_directory_id(body.get('directory_id'))
    instance = get_instance(key)
    if instance is None:
        raise ValueError('game not found')
    async with instance._lock:
        state = run_story.snapshot(instance)
        if (get_instance(key) is not instance or body.get('run_id') != instance.run_id
                or type(body.get('revision')) is not int or body['revision'] != state['revision']
                or state.get('run_id') != instance.run_id):
            raise ValueError('stale run or story plan; refresh before copying')
        if instance.adventure_binding:
            raise ValueError('bound adventures already own their reusable package')
        plan = run_story.validate_plan(state.get('plan'), set(instance.npcs))
        draft = from_plan(plan, directory, instance.language)
    return reviewer(draft)
