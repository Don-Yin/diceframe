"""Recovery qualifications never become a second character balance or clock."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.engine.game_instance import GameInstance, GameState
from src.engine.module_state import ModuleStateError
from src.engine.modules import resource_recovery as recovery
from src.engine.world_events import advance_world_time
from src.rulesets.resource_recovery import managed_resources, policy


def fixture(profile="coc_light", luck="check"):
    instance = GameInstance(("test", "recovery"))
    instance.state = GameState.ACTIVE_ACTION
    instance.gm_uid = "gm"
    instance.players["alice"] = {"character_name": "Alice", "character_sheet": {
        "hp": 10, "max_hp": 10, "sanity": 40, "max_sanity": 99,
        "luck": 30, "max_luck": 99, "skills": [],
    }}
    instance.players["doctor"] = {"character_name": "Doctor", "character_sheet": {
        "hp": 10, "max_hp": 10, "sanity": 60, "max_sanity": 99,
        "skills": [{"id": "psychoanalysis", "name": "Treatment", "value": 75},
                   {"id": "psychology", "name": "Psychology", "value": 80}],
    }}
    rule = SimpleNamespace(template={
        "resource_recovery": {"version": 1, "policy": profile, "luck_recovery": luck},
        "special_stats": [{"key": "sanity", "max": 99}, {"key": "luck", "max": 99}],
        "skills": {"psychoanalysis": {"name": "Treatment"}, "psychology": {"name": "Psychology"}},
    })
    instance._recovery_test_policy = policy(rule)
    return instance, rule


def source(instance, kind="reward", **kwargs):
    kwargs.setdefault("policy_snapshot", instance._recovery_test_policy)
    item = recovery.new_source(instance, kind, "alice", **kwargs)
    recovery.approve_source(instance, item["id"], "gm")
    return item["id"]


def test_policy_is_explicit_and_manages_only_declared_resources():
    assert policy(SimpleNamespace(template={})) is None
    assert not managed_resources(SimpleNamespace(template={}))
    _, rule = fixture()
    assert managed_resources(rule) == {"sanity", "luck"}
    rule.template["special_stats"] = [{"key": "sanity"}]
    assert managed_resources(rule) == {"sanity"}


@pytest.mark.parametrize("definition", [None, {}, {"version": True, "policy": "coc_light", "luck_recovery": "check"},
    {"version": 2, "policy": "coc_light", "luck_recovery": "check"},
    {"version": 1, "policy": "official", "luck_recovery": "check"},
    {"version": 1, "policy": "coc_light", "luck_recovery": "always"}])
def test_invalid_declared_policy_fails_closed(definition):
    _, rule = fixture()
    rule.template["resource_recovery"] = definition
    with pytest.raises(ValueError):
        policy(rule)


def test_view_does_not_materialize_and_rejects_unknown_or_corrupt_module():
    instance, _ = fixture()
    instance.modules.pop("resource_recovery", None)
    before = deepcopy(instance.modules)
    assert recovery.view(instance)["receipts"] == {}
    assert instance.modules == before
    for bad in ({"schema_version": 2}, {**recovery.fresh(), "consumed": []},
                {**recovery.fresh(), "revision": True}):
        instance.modules["resource_recovery"] = bad
        before = deepcopy(instance.modules)
        with pytest.raises(ModuleStateError):
            recovery.view(instance)
        assert instance.modules == before


def test_pending_source_cannot_settle_and_reward_is_bounded_and_synchronized():
    instance, rule = fixture()
    item = recovery.new_source(instance, "reward", "alice", resource_key="sanity", resource_delta=99,
                               policy_snapshot=policy(rule))
    before = deepcopy(instance.to_dict())
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, item["id"], "op")
    assert instance.to_dict() == before
    recovery.approve_source(instance, item["id"], "gm")
    receipt = recovery.settle(instance, rule, item["id"], "op")
    assert receipt["before"] == 40 and receipt["after"] == 99 and receipt["delta"] == 59
    assert instance.get_character_sheet("alice")["resources"]["sanity"]["current"] == 99
    assert "sanity" not in recovery.view(instance)


def test_treatment_fumble_uses_existing_madness_state_machine_with_seeded_duration():
    instance, rule = fixture('coc7e_style')
    identity = source(instance, 'therapy', healer_uid='doctor', skill_id='psychoanalysis')
    for _ in range(30):
        advance_world_time(instance, 1440)
    with patch.object(recovery, '_source_rng') as factory:
        factory.return_value.randint.side_effect = [100, 6, 2]
        receipt = recovery.settle(instance, rule, identity, 'fumble')
    assert receipt['delta'] == -6 and receipt['fumble']
    assert instance.get_character_sheet('alice')['madness']['type'] == 'temporary'
    assert instance.get_character_sheet('alice')['madness']['remaining_rounds'] == 2


def test_seeded_outcome_idempotency_survives_roundtrip_and_old_operation_log_pruning():
    instance, rule = fixture()
    identity = source(instance, resource_key="sanity", resource_delta="1d6")
    seeded = deepcopy(instance.to_dict())
    first = recovery.settle(instance, rule, identity, "first")
    retry = GameInstance.from_dict(seeded)
    second = recovery.settle(retry, rule, identity, "different-operation")
    assert second["rolls"] == first["rolls"] and second["after"] == first["after"]
    loaded = GameInstance.from_dict(instance.to_dict())
    loaded.get_character_sheet("alice")["ruleset_operation_log"] = []
    assert recovery.settle(loaded, rule, identity, "first") == first
    assert recovery.settle(loaded, rule, identity, "other") == first


def test_overnight_consumes_one_day_qualification_without_advancing_clock_itself():
    instance, rule = fixture()
    identity = source(instance, "overnight", started_tick=0)
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, identity, "early")
    advance_world_time(instance, 480)
    world_before = deepcopy(instance.world_state)
    receipt = recovery.settle(instance, rule, identity, "rest")
    assert 1 <= receipt["delta"] <= 6
    assert instance.world_state == world_before
    another = source(instance, "overnight", started_tick=0)
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, another, "again")


def test_strict_profile_disallows_overnight_and_requires_month_of_psychoanalysis():
    instance, rule = fixture("coc7e_style")
    identity = source(instance, "overnight")
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, identity, "no-overnight")
    identity = source(instance, "therapy", healer_uid="doctor", skill_id="psychoanalysis")
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, identity, "too-soon")
    for _ in range(30):
        advance_world_time(instance, 1440)
    with patch.object(recovery, "_source_rng") as factory:
        factory.return_value.randint.side_effect = [25, 2]
        receipt = recovery.settle(instance, rule, identity, "therapy")
    assert receipt["delta"] == 2 and receipt["check_id"]
    assert receipt["healer_uid"] == "doctor" and receipt["purpose"] == "therapy"


@pytest.mark.parametrize("roll,expected", [(70, 2), (90, 0), (100, -4)])
def test_treatment_check_is_server_bound_and_failure_still_consumes_scope(roll, expected):
    instance, rule = fixture("coc7e_style")
    for _ in range(30):
        advance_world_time(instance, 1440)
    identity = source(instance, "therapy", healer_uid="doctor", skill_id="psychoanalysis")
    with patch.object(recovery, "_source_rng") as factory:
        factory.return_value.randint.side_effect = [roll, abs(expected)]
        receipt = recovery.settle(instance, rule, identity, "therapy")
    assert receipt["delta"] == expected
    other = source(instance, "therapy", healer_uid="doctor", skill_id="psychoanalysis")
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, other, "duplicate-scope")


def test_strict_therapy_rejects_psychology_without_rolls():
    instance, rule = fixture("coc7e_style")
    identity = source(instance, "therapy", healer_uid="doctor", skill_id="psychology")
    before = deepcopy(instance.to_dict())
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, identity, "psychology")
    assert instance.to_dict() == before


@pytest.mark.parametrize("roll,gain", [(31, 5), (30, 0)])
def test_luck_recovery_requires_roll_above_current_luck_and_unique_intermission(roll, gain):
    instance, rule = fixture()
    identity = source(instance, "luck", origin_id="intermission:1")
    with patch.object(recovery, "_source_rng") as factory:
        factory.return_value.randint.side_effect = [roll, gain]
        receipt = recovery.settle(instance, rule, identity, "luck")
    assert receipt["delta"] == gain and receipt["after"] == 30 + gain
    other = source(instance, "luck", origin_id="intermission:1")
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, other, "luck-again")


@pytest.mark.parametrize("change", ["dead", "san_zero", "away", "ended"])
def test_ineligible_character_never_consumes_or_recovers(change):
    instance, rule = fixture()
    identity = source(instance, resource_key="sanity", resource_delta=3)
    if change == "dead":
        instance.get_character_sheet("alice").update(deceased=True, death_cause="永久疯狂")
    elif change == "san_zero":
        instance.get_character_sheet("alice")["sanity"] = 0
    elif change == "away":
        instance.away_players.add("alice")
    else:
        instance.state = GameState.ENDED
    before = deepcopy(instance.to_dict())
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, identity, "ineligible")
    assert instance.to_dict() == before


def test_full_cap_consumes_source_and_operations_conflict_with_different_source():
    instance, rule = fixture()
    instance.get_character_sheet("alice")["sanity"] = 99
    identity = source(instance, resource_key="sanity", resource_delta=3)
    assert recovery.settle(instance, rule, identity, "one")["delta"] == 0
    other = source(instance, resource_key="sanity", resource_delta=1)
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, other, "one")


def test_luck_off_and_policy_changes_do_not_consume_pending_source():
    instance, rule = fixture(luck="off")
    identity = source(instance, "luck", origin_id="session")
    before = deepcopy(instance.to_dict())
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, identity, "off")
    assert instance.to_dict() == before
    rule.template["resource_recovery"]["luck_recovery"] = "check"
    with pytest.raises(ValueError, match="policy"):
        recovery.settle(instance, rule, identity, "changed")


def test_commands_are_durable_and_payload_conflicts_cannot_replace_them():
    instance, rule = fixture()
    identity = source(instance, resource_key="sanity", resource_delta=1)
    record = {"principal": "alice", "action": "request", "body": {"kind": "reward"}, "source_ids": [identity]}
    recovery.record_command(instance, "nonce", record)
    revision = recovery.view(instance)["revision"]
    recovery.record_command(instance, "nonce", deepcopy(record))
    assert recovery.view(instance)["revision"] == revision
    before = deepcopy(instance.to_dict())
    with pytest.raises(ValueError):
        recovery.record_command(instance, "nonce", {**record, "principal": "doctor"})
    assert instance.to_dict() == before
    loaded = GameInstance.from_dict(instance.to_dict())
    assert recovery.command(loaded, "nonce") == record
    returned = recovery.command(loaded, "nonce")
    returned["body"]["kind"] = "mutated"
    assert recovery.command(loaded, "nonce") == record


def test_round_logs_do_not_duplicate_the_permanent_consumption_ledger():
    instance, rule = fixture()
    identity = source(instance, resource_key='sanity', resource_delta=1)
    recovery.settle(instance, rule, identity, 'settled')
    instance.round_number = 2
    recovery._begin(instance)
    entry = {'round': 2}
    recovery._commit(instance, entry, None)
    assert 'pre_resource_recovery' not in entry
    assert identity not in str(entry)
    assert len(recovery.view(instance)['consumed']) == 1


def test_rewind_retains_old_receipts_but_rejects_pending_qualifications_from_the_cut():
    instance, rule = fixture()
    settled = source(instance, resource_key='sanity', resource_delta=1)
    recovery.settle(instance, rule, settled, 'settled')
    instance.round_number = 3
    pending = source(instance, resource_key='sanity', resource_delta=1)
    before = deepcopy(recovery.view(instance)['consumed'])
    recovery._rewind(instance, {'round': 2}, 2, 'rollback')
    state = recovery.view(instance)
    assert state['consumed'] == before and settled in state['receipts']
    assert state['sources'][pending]['status'] == 'rejected'


def test_rejected_source_cannot_be_approved_or_settled():
    instance, rule = fixture()
    identity = source(instance, resource_key="sanity", resource_delta=3)
    recovery.reject_source(instance, identity, "gm")
    before = deepcopy(instance.to_dict())
    with pytest.raises(ValueError):
        recovery.approve_source(instance, identity, "gm")
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, identity, "rejected")
    assert instance.to_dict() == before


def test_treatment_fumble_at_low_san_marks_permanent_madness_without_raising_balance():
    instance, rule = fixture("coc7e_style")
    instance.get_character_sheet("alice")["sanity"] = 2
    for _ in range(30):
        advance_world_time(instance, 1440)
    identity = source(instance, "therapy", healer_uid="doctor", skill_id="psychoanalysis")
    with patch.object(recovery, "_source_rng") as factory:
        factory.return_value.randint.side_effect = [100, 6]
        receipt = recovery.settle(instance, rule, identity, "fumble")
    assert receipt["after"] == 0 and receipt["delta"] == -2
    assert not instance.is_alive("alice")
    assert instance.get_character_sheet("alice")["death_cause"] == "永久疯狂"


@pytest.mark.parametrize("damage", ["lost_consumed", "lost_operation", "receipt_balance", "source_seed", "source_policy", "future_policy"])
def test_corrupt_persisted_qualifications_and_receipts_fail_closed(damage):
    instance, rule = fixture()
    identity = source(instance, resource_key="sanity", resource_delta=1)
    recovery.settle(instance, rule, identity, "settlement")
    state = instance.modules["resource_recovery"]
    if damage == "lost_consumed":
        state["consumed"].clear()
    elif damage == "lost_operation":
        state["operations"].clear()
    elif damage == "receipt_balance":
        state["receipts"][identity]["after"] += 1
    elif damage == "source_seed":
        state["sources"][identity]["seed"] = "invalid"
    elif damage == "source_policy":
        state["sources"][identity]["policy"]["policy"] = "coc7e_style"
    else:
        state["sources"][identity]["policy"]["version"] = 2
    before = deepcopy(instance.to_dict())
    with pytest.raises(ModuleStateError):
        recovery.view(instance)
    assert instance.to_dict() == before


def test_current_skill_value_and_explicit_legacy_alias_are_used_for_treatment():
    instance, rule = fixture()
    healer = instance.get_character_sheet("doctor")
    healer["skills"] = [{"name": "Known old label", "value": 80}]
    rule.template["skill_improvement"] = {"identity_aliases": {"psychoanalysis": ["Known old label"]}}
    identity = source(instance, "therapy", healer_uid="doctor", skill_id="psychoanalysis")
    with patch.object(recovery, "_source_rng") as factory:
        factory.return_value.randint.side_effect = [40, 2]
        receipt = recovery.settle(instance, rule, identity, "aliased-treatment")
    assert receipt["rolls"]["threshold"] == 80 and receipt["delta"] == 2


def test_same_display_name_with_conflicting_canonical_skill_does_not_authorize_treatment():
    instance, rule = fixture()
    instance.get_character_sheet("doctor")["skills"] = [{"id": "psychology", "name": "Treatment", "value": 99}]
    identity = source(instance, "therapy", healer_uid="doctor", skill_id="psychoanalysis")
    before = deepcopy(instance.to_dict())
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, identity, "wrong-canonical")
    assert instance.to_dict() == before


def test_future_world_clock_cannot_grant_recovery_duration():
    instance, rule = fixture()
    identity = source(instance, "overnight")
    instance.world_state["schema_version"] = 99
    before = deepcopy(instance.to_dict())
    with pytest.raises(ValueError, match="world clock"):
        recovery.settle(instance, rule, identity, "unknown-clock")
    assert instance.to_dict() == before


def test_source_and_consumption_ledger_are_not_truncated_after_32_claims():
    instance, rule = fixture()
    first = None
    for index in range(40):
        identity = source(instance, "luck", origin_id=f"intermission:{index}")
        receipt = recovery.settle(instance, rule, identity, f"claim:{index}")
        if first is None:
            first = receipt
    assert len(recovery.view(instance)["consumed"]) == 40
    again = source(instance, "luck", origin_id="intermission:0")
    with pytest.raises(ValueError):
        recovery.settle(instance, rule, again, "new-id")


@pytest.mark.asyncio
async def test_round_abort_restores_qualification_and_rewind_crossing_settlement_is_refused():
    from src.engine import module_hooks
    instance, rule = fixture()
    before = recovery.view(instance)
    module_hooks.run(module_hooks.ROUND_PROCESSING_BEGIN, instance)
    source(instance, resource_key="sanity", resource_delta=1)
    assert module_hooks.run_any(module_hooks.ROUND_ABORT, instance)
    assert recovery.view(instance) == before
    identity = source(instance, resource_key="sanity", resource_delta=1)
    recovery.settle(instance, rule, identity, "settled")
    instance.log.append({"round": 0, "gm_response": "Public"})
    with pytest.raises(ValueError, match="recovery"):
        await instance.rollback_last_round()
    recovery.reset(instance)
    assert recovery.view(instance) == recovery.fresh()
