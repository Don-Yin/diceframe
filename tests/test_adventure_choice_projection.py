from src.engine.modules import adventure_runtime_state
from copy import deepcopy

from src.webui.services import adventures, adventure_runtime
from src.rulesets.registry import RulesetRuntimeRegistry
from tests.test_adventure_choices import installed_choice


def test_only_gm_and_requesting_player_receive_advisory_choices(tmp_path):
    runtime_deps, instance = installed_choice(tmp_path)
    # This explicit source is the fixture's native package owner.
    from src.adventures import AdventureResolver
    resolver = AdventureResolver.single_directory(tmp_path / 'adventures', source_kind='user')
    deps = adventures.AdventureDependencies(
        adventure_loader=resolver, adventure_resolver=resolver, list_instances=lambda: [instance],
        load_rule_by_id=lambda *_: None, ruleset_registry=RulesetRuntimeRegistry(), default_runtime_requirement=lambda: {},
    )
    adventure_runtime.request_adventure_choice(runtime_deps, instance, 'gate', 'bridge_route', 'alice')
    before = deepcopy(adventure_runtime_state.progress(instance))
    for uid, expected in [('alice', 1), ('bob', 0), ('outsider', 0)]:
        projection = adventures.game_adventure_projection(deps, instance, viewer_is_gm=False, viewer_uid=uid)
        progress = projection['adventure']['projection']['progress']
        assert len(progress['choice_requests']) == expected
        assert 'tunnel_route' not in str(projection) and 'world.fact_equals' not in str(projection)
    gm = adventures.game_adventure_projection(deps, instance, viewer_is_gm=True)
    assert gm['adventure']['projection']['progress']['choice_requests'][0]['actor_uid'] == 'alice'
    assert adventure_runtime_state.progress(instance) == before
