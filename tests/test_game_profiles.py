import asyncio
from copy import deepcopy

import pytest

from src.engine.game_instance import GameRegistry, GameInstance
from src.engine.player_control import set_control
from src.game_profiles.service import ProfileService, ProfileDependencies


def service(tmp_path, *, roll=6, save=None):
    registry = GameRegistry(save_dir=tmp_path)
    return ProfileService(
        ProfileDependencies(
            get=registry.get,
            register=registry.register,
            save=save or registry.save,
            roll=lambda: roll,
        )
    ), registry


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile,mode", [("core:demo-heist", "phase"), ("core:demo-survival", "calendar")]
)
async def test_profiles_use_native_save_controls_and_non_narrative_progression(
    tmp_path, profile, mode
):
    profiles, registry = service(tmp_path)
    result = await profiles.create(
        {"profile_id": profile, "names": ["Leader", "Scout"], "language": "en"}
    )
    instance = registry.get(tuple(result["game_key"].split("|")))
    assert instance.modules["profile_progression"]["mode"] == mode
    assert instance.players[instance.gm_uid]["character_sheet"].get("hp") is None
    view = profiles.view(instance, instance.gm_uid, True)
    assert view["profile"]["id"] == profile
    assert not await instance.advance_round()
    move = view["actions"][0]["id"]
    receipt = await profiles.act(
        instance,
        instance.gm_uid,
        True,
        {
            "type": "move",
            "move_id": move,
            "actor_uid": instance.gm_uid,
            "expected_run_id": instance.run_id,
            "expected_revision": view["revision"],
            "expected_control_revision": 0,
        },
    )
    assert receipt["ok"] and receipt["view"]["revision"] == 1
    restored = GameInstance.from_dict(instance.to_dict())
    assert (
        profiles.view(restored, restored.gm_uid, True)["history"]
        == receipt["view"]["history"]
    )
    assert restored.modules["profile_progression"]["mode"] == mode


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "slot", [None, {}, {"schema_version": 1, "mode": "unconfigured"}]
)
async def test_incomplete_bound_profile_cannot_fall_back_to_narrative_advancement(
    tmp_path, slot
):
    profiles, registry = service(tmp_path)
    created = await profiles.create(
        {"profile_id": "core:demo-heist", "names": ["Leader"]}
    )
    instance = registry.get(tuple(created["game_key"].split("|")))
    if slot is None:
        instance.modules.pop("profile_progression")
    else:
        instance.modules["profile_progression"] = deepcopy(slot)
    before = deepcopy(instance.modules)
    assert not await instance.advance_round()
    assert not await instance.try_advance()
    assert instance.round_number == 0 and instance.modules == before


@pytest.mark.asyncio
async def test_profile_action_identity_concurrency_and_save_failure_leave_no_partial_resources(
    tmp_path,
):
    async def fail_save(_instance):
        raise RuntimeError("save failed")

    profiles, registry = service(tmp_path)
    created = await profiles.create(
        {
            "profile_id": "core:demo-survival",
            "names": ["Leader", "Scout"],
            "language": "en",
        }
    )
    instance = registry.get(tuple(created["game_key"].split("|")))
    uid = next(uid for uid in instance.players if uid != instance.gm_uid)
    view = profiles.view(instance, uid, False)
    body = {
        "type": "move",
        "move_id": view["actions"][0]["id"],
        "actor_uid": uid,
        "expected_run_id": instance.run_id,
        "expected_revision": 0,
        "expected_control_revision": 0,
    }
    before = deepcopy(instance.modules)
    with pytest.raises(ValueError):
        await profiles.act(instance, uid, False, {**body, "actor_uid": instance.gm_uid})
    set_control(instance, uid, "ai")
    with pytest.raises(ValueError):
        await profiles.act(instance, uid, False, body)
    set_control(instance, uid, "human")
    body["expected_control_revision"] = 2
    profiles.deps = ProfileDependencies(
        get=registry.get, register=registry.register, save=fail_save, roll=lambda: 6
    )
    before = deepcopy(instance.modules)
    with pytest.raises(RuntimeError):
        await profiles.act(instance, uid, False, body)
    assert instance.modules == before
    profiles.deps = ProfileDependencies(
        get=registry.get, register=registry.register, save=registry.save, roll=lambda: 6
    )
    results = await asyncio.gather(
        *(profiles.act(instance, uid, False, body) for _ in range(2)),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, ValueError) for result in results) == 1


@pytest.mark.asyncio
async def test_survival_calendar_consumes_resources_once_and_failed_upkeep_restores_both_modules(
    tmp_path,
):
    profiles, registry = service(tmp_path)
    created = await profiles.create(
        {"profile_id": "core:demo-survival", "names": ["Leader"], "language": "en"}
    )
    instance = registry.get(tuple(created["game_key"].split("|")))
    before = profiles.view(instance, instance.gm_uid, True)
    result = await profiles.act(
        instance,
        instance.gm_uid,
        True,
        {"type": "advance", "expected_run_id": instance.run_id, "expected_revision": 0},
    )
    assert result["view"]["progression"]["day"] == 2
    assert result["view"]["resources"]["food"] == before["resources"]["food"] - 1
    assert instance.round_number == 0
    with pytest.raises(ValueError):
        await profiles.act(
            instance,
            instance.gm_uid,
            True,
            {
                "type": "advance",
                "expected_run_id": instance.run_id,
                "expected_revision": 0,
            },
        )


@pytest.mark.asyncio
async def test_unknown_profile_or_state_schema_fails_closed_without_narrative_fallback(
    tmp_path,
):
    profiles, registry = service(tmp_path)
    with pytest.raises(ValueError):
        await profiles.create(
            {"profile_id": "unknown", "names": ["Leader"], "language": "en"}
        )
    created = await profiles.create(
        {"profile_id": "core:demo-heist", "names": ["Leader"], "language": "en"}
    )
    instance = registry.get(tuple(created["game_key"].split("|")))
    instance.modules["profile_run"]["schema_version"] = 99
    before = deepcopy(instance.to_dict())
    with pytest.raises(ValueError):
        profiles.view(instance, instance.gm_uid, True)
    with pytest.raises(ValueError):
        await profiles.act(
            instance,
            instance.gm_uid,
            True,
            {
                "type": "advance",
                "expected_run_id": instance.run_id,
                "expected_revision": 0,
            },
        )
    assert instance.to_dict() == before


@pytest.mark.asyncio
async def test_heist_completes_a_whole_phase_run_and_rule_controller_uses_the_same_move_authority(
    tmp_path,
):
    profiles, registry = service(tmp_path)
    created = await profiles.create(
        {"profile_id": "core:demo-heist", "names": ["Leader"], "language": "en"}
    )
    instance = registry.get(tuple(created["game_key"].split("|")))
    uid = instance.gm_uid

    async def act(kind, move="study"):
        view = profiles.view(instance, uid, True)
        body = {
            "type": kind,
            "expected_run_id": instance.run_id,
            "expected_revision": view["revision"],
        }
        if kind != "advance":
            body.update(
                move_id=move,
                actor_uid=uid,
                expected_control_revision=view["control_revision"],
            )
        return await profiles.act(instance, uid, True, body)

    await act("move")
    await act("move")
    await act("advance")
    set_control(instance, uid, "ai")
    automatic = await act("auto")
    assert automatic["result"]["move_id"] == "sneak"
    assert automatic["view"]["clocks"]["loot"] == 2
    set_control(instance, uid, "human")
    await act("move", "force")
    assert (await act("advance"))["view"]["status"] == "won"
    assert (
        instance.round_number == 0
        and len(instance.modules["profile_run"]["history"]) == 6
    )


@pytest.mark.asyncio
async def test_survival_full_calendar_has_a_terminal_goal_and_upkeep_is_not_replayed_on_reload(
    tmp_path,
):
    profiles, registry = service(tmp_path)
    created = await profiles.create(
        {"profile_id": "core:demo-survival", "names": ["Leader"], "language": "en"}
    )
    instance = registry.get(tuple(created["game_key"].split("|")))
    uid = instance.gm_uid
    for _ in range(5):
        view = profiles.view(instance, uid, True)
        await profiles.act(
            instance,
            uid,
            True,
            {
                "type": "move",
                "move_id": "forage",
                "actor_uid": uid,
                "expected_run_id": instance.run_id,
                "expected_revision": view["revision"],
                "expected_control_revision": 0,
            },
        )
        view = profiles.view(instance, uid, True)
        await profiles.act(
            instance,
            uid,
            True,
            {
                "type": "advance",
                "expected_run_id": instance.run_id,
                "expected_revision": view["revision"],
            },
        )
    final = profiles.view(instance, uid, True)
    assert (
        final["status"] == "won" and not final["actions"] and not final["can_advance"]
    )
    assert final["progression"]["day"] == 5
    restored = GameInstance.from_dict(instance.to_dict())
    assert profiles.view(restored, uid, True)["resources"] == final["resources"]
    before = deepcopy(instance.modules)
    with pytest.raises(ValueError):
        await profiles.act(
            instance,
            uid,
            True,
            {
                "type": "advance",
                "expected_run_id": instance.run_id,
                "expected_revision": final["revision"],
            },
        )
    assert instance.modules == before


@pytest.mark.asyncio
async def test_survival_build_cost_storm_protection_and_medkit_use_share_legal_action_boundary(
    tmp_path,
):
    profiles, registry = service(tmp_path, roll=1)
    rolls = iter([6, 1, 1, 6, 1, 6, 6, 6, 6])
    profiles.deps = ProfileDependencies(
        get=registry.get,
        register=registry.register,
        save=registry.save,
        roll=lambda: next(rolls),
    )
    created = await profiles.create(
        {"profile_id": "core:demo-survival", "names": ["Leader"], "language": "en"}
    )
    instance = registry.get(tuple(created["game_key"].split("|")))
    uid = instance.gm_uid

    async def action(move=None):
        view = profiles.view(instance, uid, True)
        body = {
            "type": "move" if move else "advance",
            "expected_run_id": instance.run_id,
            "expected_revision": view["revision"],
        }
        if move:
            body.update(move_id=move, actor_uid=uid, expected_control_revision=0)
        return await profiles.act(instance, uid, True, body)

    await action("build")
    assert instance.modules["profile_run"]["resources"]["supplies"] == 0
    assert "build" not in [
        move["id"] for move in profiles.view(instance, uid, True)["actions"]
    ]
    await action()
    assert instance.modules["profile_run"]["actors"][uid]["health"] == 4
    await action("gather")
    await action()
    await action("gather")
    await action()
    assert instance.modules["profile_run"]["resources"]["supplies"] == 2
    await action("craft")
    await action()
    before = deepcopy(instance.modules["profile_run"])
    treated = await action("treat")
    assert treated["view"]["actors"][0]["inventory"] == []
    assert treated["view"]["actors"][0]["health"] == min(
        5, before["actors"][uid]["health"] + 3
    )
    assert "treat" not in [move["id"] for move in treated["view"]["actions"]]
    # An independently staged native state checks the level-two protection;
    # costs and item effects above travel through the public action authority.
    runtime = profiles._state(instance)[0].runtime
    sheltered = deepcopy(before)
    sheltered["resources"].update(base=2, food=10, water=10)
    health = sheltered["actors"][uid]["health"]
    result = runtime.advance(sheltered, {"day": 4}, 1)
    assert not result["storm_damage"] and sheltered["actors"][uid]["health"] == health


@pytest.mark.asyncio
async def test_creation_save_failure_registers_no_live_game_and_malformed_binding_cannot_mutate(
    tmp_path,
):
    async def fail_save(_):
        raise RuntimeError("creation storage failed")

    profiles, registry = service(tmp_path, save=fail_save)
    with pytest.raises(RuntimeError):
        await profiles.create({"profile_id": "core:demo-heist", "names": ["Leader"]})
    assert not registry.list_active()
    profiles, registry = service(tmp_path)
    created = await profiles.create(
        {"profile_id": "core:demo-survival", "names": ["Leader"]}
    )
    instance = registry.get(tuple(created["game_key"].split("|")))
    for malformed in (
        {},
        {"schema_version": True, "profile_id": "", "profile_version": 0},
        {"schema_version": 1, "profile_id": "", "profile_version": 0},
    ):
        instance.modules["profile_run"] = malformed
        before = deepcopy(instance.modules)
        with pytest.raises(ValueError):
            profiles.view(instance, instance.gm_uid, True)
        assert instance.modules == before


@pytest.mark.asyncio
async def test_stage_save_failure_restores_upkeep_clock_and_stale_run_rejects_before_rolling(
    tmp_path,
):
    profiles, registry = service(tmp_path)
    created = await profiles.create(
        {"profile_id": "core:demo-survival", "names": ["Leader"], "language": "en"}
    )
    instance = registry.get(tuple(created["game_key"].split("|")))

    async def fail_save(_):
        raise RuntimeError("storage failed")

    profiles.deps = ProfileDependencies(
        get=registry.get, register=registry.register, save=fail_save, roll=lambda: 1
    )
    before = deepcopy(instance.modules)
    with pytest.raises(RuntimeError):
        await profiles.act(
            instance,
            instance.gm_uid,
            True,
            {
                "type": "advance",
                "expected_run_id": instance.run_id,
                "expected_revision": 0,
            },
        )
    assert instance.modules == before
    with pytest.raises(ValueError, match="run changed"):
        await profiles.act(
            instance,
            instance.gm_uid,
            True,
            {"type": "advance", "expected_run_id": "stale", "expected_revision": 0},
        )
    assert instance.modules == before
