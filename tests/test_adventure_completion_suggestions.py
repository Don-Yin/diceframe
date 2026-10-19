from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.commands.round_effects import apply_plot_update
from src.commands.tag_parser import parse_tag_state
from src.engine import module_hooks
from src.engine.game_instance import GameInstance
from src.engine.modules import adventure_runtime_state
from src.rulesets.registry import RulesetRuntimeRegistry
from src.webui.services import adventure_commands, adventure_runtime, adventures
from tests.test_adventure_choices import installed_choice


def _suggestion(node_id: str = "gate") -> dict:
    return {
        "format_version": 1,
        "node_id": node_id,
        "reason": "The party found the key and opened the gate.",
        "evidence_rounds": [1],
    }


def _record_suggestion(instance: GameInstance, node_id: str = "gate") -> None:
    instance.log.append({"round": 1, "gm_response": "The party found the key."})
    candidate = _suggestion(node_id)
    assert adventure_runtime_state.record_completion_suggestion(instance, candidate)


def _projection_dependencies(tmp_path, instance):
    from src.adventures import AdventureResolver

    resolver = AdventureResolver.single_directory(
        tmp_path / "adventures", source_kind="user",
    )
    return adventures.AdventureDependencies(
        adventure_loader=resolver,
        adventure_resolver=resolver,
        list_instances=lambda: [instance],
        load_rule_by_id=lambda *_: None,
        ruleset_registry=RulesetRuntimeRegistry(),
        default_runtime_requirement=lambda: {},
    )


def test_adventure_completion_tag_is_parsed_as_advisory_data():
    expected = _suggestion()

    parsed = parse_tag_state(
        f"The party opened the gate.\n---\nADVENTURE_COMPLETE:{json.dumps(expected)}",
    )

    assert parsed["plot_update"]["adventure_completion"] == expected


def test_suggestion_requires_committed_positive_evidence_and_closed_shape(tmp_path):
    _, instance = installed_choice(tmp_path)
    candidate = _suggestion()

    assert not adventure_runtime_state.record_completion_suggestion(instance, candidate)
    instance.log.append({"round": 0, "gm_response": " "})
    assert not adventure_runtime_state.record_completion_suggestion(
        instance, {**candidate, "evidence_rounds": [0]},
    )
    assert not adventure_runtime_state.record_completion_suggestion(
        instance, {**candidate, "evidence_rounds": [2]},
    )
    assert not adventure_runtime_state.record_completion_suggestion(
        instance, {**candidate, "unexpected": True},
    )
    assert not adventure_runtime_state.record_completion_suggestion(
        instance, {**candidate, "format_version": True},
    )
    instance.log.append({"round": 1, "gm_response": "The party found the key."})
    assert adventure_runtime_state.record_completion_suggestion(instance, candidate)
    assert not adventure_runtime_state.record_completion_suggestion(instance, candidate)


@pytest.mark.asyncio
async def test_round_commit_records_suggestion_with_log_and_rewind_removes_it(tmp_path):
    _, instance = installed_choice(tmp_path)
    instance.capture_round_entity_snapshot()

    await instance.finish_judgment(
        "The party found the key.",
        adventure_completion_candidate={**_suggestion(), "evidence_rounds": [0]},
    )

    assert instance.log[-1]["round"] == 0
    assert len(adventure_runtime_state.progress_snapshot(instance)["completion_suggestions"]) == 1
    assert await instance.rollback_last_round() is not None
    assert adventure_runtime_state.progress_snapshot(instance).get("completion_suggestions", []) == []


@pytest.mark.asyncio
async def test_swipe_replaces_suggestion_evidence_and_switch_clears_it(tmp_path):
    _, instance = installed_choice(tmp_path)
    instance.capture_round_entity_snapshot()
    await instance.finish_judgment(
        "The party found the key.",
        adventure_completion_candidate={**_suggestion(), "evidence_rounds": [0]},
    )

    await instance.finish_judgment_with_swipe(
        "The alternate narration changes the gate result.", 0,
        adventure_completion_candidate={
            **_suggestion(),
            "reason": "The alternate narration establishes the gate opened.",
            "evidence_rounds": [0],
        },
    )
    progress = adventure_runtime_state.progress_snapshot(instance)
    assert progress["completion_suggestions"][0]["reason"].startswith("The alternate")

    assert await instance.switch_swipe(0, 0)
    assert adventure_runtime_state.progress_snapshot(instance)["completion_suggestions"] == []


def test_model_suggestion_is_stored_only_for_active_nodes_and_never_completes_them(tmp_path):
    _, instance = installed_choice(tmp_path)

    _record_suggestion(instance)
    progress = adventure_runtime_state.progress_snapshot(instance)

    assert progress["active_nodes"] == ["gate"]
    assert progress["completed_nodes"] == []
    assert len(progress["completion_suggestions"]) == 1
    assert progress["completion_suggestions"][0]["node_id"] == "gate"
    assert progress["completion_suggestions"][0]["evidence_rounds"] == [1]

    # A model cannot create a suggestion for a declared but unopened branch.
    apply_plot_update(
        instance,
        SimpleNamespace(plot_update={"adventure_completion": _suggestion("bridge")}),
    )
    assert len(adventure_runtime_state.progress_snapshot(instance)["completion_suggestions"]) == 1


def test_completion_suggestions_are_idempotent_and_projected_to_gm_only(tmp_path):
    _, instance = installed_choice(tmp_path)
    _record_suggestion(instance)
    candidate = adventure_runtime_state.progress_snapshot(instance)["completion_suggestions"][0]
    apply_plot_update(
        instance,
        SimpleNamespace(plot_update={"adventure_completion": _suggestion()}),
    )

    deps = _projection_dependencies(tmp_path, instance)
    gm = adventures.game_adventure_projection(deps, instance, viewer_is_gm=True)
    player = adventures.game_adventure_projection(
        deps, instance, viewer_is_gm=False, viewer_uid="alice",
    )

    gm_suggestions = gm["adventure"]["projection"]["progress"]["completion_suggestions"]
    assert gm_suggestions == [candidate]
    assert "completion_suggestions" not in player["adventure"]["projection"]["progress"]
    assert candidate["reason"] not in json.dumps(player)


def test_completing_node_clears_its_suggestion(tmp_path):
    runtime_deps, instance = installed_choice(tmp_path)
    _record_suggestion(instance)
    proposal_id = adventure_runtime_state.progress_snapshot(instance)["completion_suggestions"][0]["proposal_id"]
    assert adventure_runtime_state.dismiss_completion_suggestion(instance, proposal_id) == "gate"
    assert adventure_runtime_state.progress_snapshot(instance)["ignored_completion_nodes"] == ["gate"]

    adventure_runtime.complete_adventure_node(
        runtime_deps, instance, "gate", choice_id="bridge_route",
    )

    progress = adventure_runtime_state.progress_snapshot(instance)
    assert progress["completed_nodes"] == ["gate"]
    assert progress["completion_suggestions"] == []
    assert not progress.get("ignored_completion_nodes")


@pytest.mark.asyncio
async def test_only_gm_can_ignore_suggestion_and_save_failure_restores_it(tmp_path):
    _, instance = installed_choice(tmp_path)
    _record_suggestion(instance)
    proposal_id = adventure_runtime_state.progress_snapshot(instance)["completion_suggestions"][0]["proposal_id"]
    before = adventure_runtime_state.progress_snapshot(instance)

    async def binding():
        return None

    async def save(_instance):
        return None

    deps = adventure_commands.AdventureCommandDependencies(
        save=save,
        complete=None,
        request_choice=None,
        admission=lambda: None,
        binding=binding,
    )
    command = {"type": "adventure.completion_suggestion.dismiss", "proposal_id": proposal_id}

    denied = await adventure_commands.execute(deps, instance, command, "alice", is_gm=False)
    assert denied["code"] == "GM_ONLY"
    assert adventure_runtime_state.progress_snapshot(instance) == before

    unknown = await adventure_commands.execute(
        deps, instance,
        {"type": "adventure.completion_suggestion.dismiss", "proposal_id": "stale"},
        "gm", is_gm=True,
    )
    assert unknown["code"] == "SUGGESTION_NOT_FOUND"
    assert adventure_runtime_state.progress_snapshot(instance) == before

    result = await adventure_commands.execute(deps, instance, command, "gm", is_gm=True)
    assert result["ok"] is True
    assert adventure_runtime_state.progress_snapshot(instance)["completion_suggestions"] == []

    instance.log.append({"round": 2, "gm_response": "The party found the key again."})
    assert not adventure_runtime_state.record_completion_suggestion(instance, _suggestion())
    assert adventure_runtime_state.progress_snapshot(instance)["completion_suggestions"] == []

    async def failed_save(_instance):
        raise RuntimeError("storage failure")

    rollback_deps = adventure_commands.AdventureCommandDependencies(
        save=failed_save,
        complete=None,
        request_choice=None,
        admission=lambda: None,
        binding=binding,
    )
    # Re-open the same suggestion so the failed write has something to restore.
    progress = adventure_runtime_state.progress(instance)
    progress["ignored_completion_nodes"] = []
    _record_suggestion(instance)
    before_failure = adventure_runtime_state.progress_snapshot(instance)
    new_proposal_id = before_failure["completion_suggestions"][0]["proposal_id"]

    failed = await adventure_commands.execute(
        rollback_deps, instance,
        {"type": "adventure.completion_suggestion.dismiss", "proposal_id": new_proposal_id},
        "gm", is_gm=True,
    )
    assert failed["code"] == "ADVENTURE_NODE_FAILED"
    assert adventure_runtime_state.progress_snapshot(instance) == before_failure
