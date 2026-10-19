from dataclasses import replace

import pytest

from src.application_actions import ActionRegistry, ApplicationAction


def action(name='read_world', **kwargs):
    return ApplicationAction(name, 'Read a world', {'type': 'object', 'properties': {}, 'additionalProperties': False},
                             lambda args, owner: {'ok': True}, domain='worlds', **kwargs)


def test_registered_actions_are_discoverable_without_agent_changes():
    registry = ActionRegistry()
    registry.register(action())
    before = registry.revision
    assert registry.search('world')['capabilities'][0]['name'] == 'read_world'
    registry.register(action('edit_world', mutation=True, effect='write', automatic=True, guard=lambda args, owner: 'v1'))
    assert before != registry.revision
    assert len(registry.search(domain='worlds')['capabilities']) == 2
    assert registry.describe('edit_world')['parameters']['type'] == 'object'
    with pytest.raises(ValueError, match='duplicate'):
        registry.register(action())


def test_action_contract_changes_invalidate_old_revision_and_removed_actions():
    registry = ActionRegistry([action()])
    revision = registry.revision
    registry.replace(replace(action(), version=2))
    assert registry.revision != revision
    registry.unregister('read_world')
    with pytest.raises(ValueError, match='unavailable'):
        registry.describe('read_world')


def test_catalog_does_not_expose_callbacks_and_validates_effect_metadata():
    registry = ActionRegistry([action()])
    assert 'handler' not in registry.describe('read_world')
    with pytest.raises(ValueError):
        registry.register(action('invalid', effect='whatever'))


def test_live_sources_refresh_and_fail_closed_without_overwriting_other_owners():
    registry = ActionRegistry([action()])
    current = [action('plugin_inspect')]
    registry.register_source('plugins', lambda: current)
    registry.refresh_sources()
    assert registry.get('plugin_inspect') is not None
    current.clear()
    registry.refresh_sources()
    assert registry.get('plugin_inspect') is None
    current.append(action())  # A provider may not replace a core action.
    registry.refresh_sources()
    assert registry.get('read_world') is not None
    assert registry.search()['unavailable_sources'] == ['plugins']
