from dataclasses import replace

import pytest

from src.application_actions import ActionRegistry, ApplicationAction


def action(name='read_world', **kwargs):
    domain = kwargs.pop('domain', 'worlds')
    return ApplicationAction(name, 'Read a world', {'type': 'object', 'properties': {}, 'additionalProperties': False},
                             lambda args, owner: {'ok': True}, domain=domain, **kwargs)


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


def test_search_supports_offset_pages_and_reports_live_domain_directory():
    registry = ActionRegistry([
        action('alpha_read', domain='worlds'),
        action('bravo_read', domain='lorebook'),
        action('charlie_read', domain='worlds'),
    ])
    page = registry.search(limit=2, offset=2)
    assert [item['name'] for item in page['capabilities']] == ['charlie_read']
    assert page['offset'] == 2 and page['total'] == 3 and page['has_more'] is False
    assert page['domains'] == [
        {'domain': 'lorebook', 'count': 1}, {'domain': 'worlds', 'count': 2},
    ]


def test_empty_text_match_exposes_directory_hint_without_fabricating_matches():
    registry = ActionRegistry([action('read_world', domain='worlds')])
    result = registry.search('所有资料册的gm可见性')
    assert result['capabilities'] == []
    assert '没有文本匹配不代表没有能力' in result['discovery_hint']
    assert '空 query' in result['discovery_hint']
    assert result['domains'] == [{'domain': 'worlds', 'count': 1}]


@pytest.mark.parametrize('offset', [True, -1, 1_000_001, 1.5, '2'])
def test_search_rejects_invalid_offsets(offset):
    with pytest.raises(ValueError, match='offset'):
        ActionRegistry([action()]).search(offset=offset)


def test_directory_summary_contains_no_callbacks_or_schemas():
    registry = ActionRegistry([action('private_read')])
    summary = registry.search(limit=10)
    assert 'handler' not in repr(summary)
    assert 'schema' not in repr(summary)
    assert 'parameters' not in repr(summary)
