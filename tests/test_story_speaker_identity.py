"""Explicit GM identity repair must never merge actors just by display name."""
from copy import deepcopy
import asyncio

import pytest

from src.engine.game_instance import GameInstance, GameState
from src.engine.modules import storytelling
from src.engine.story import public_story, speaker_catalog
from src.webui.services.storytelling import StorytellingDependencies, StorytellingService

GUEST = "g_0123456789abcdef0123"
KNOWN = "s_abcdef01234567890123"


def fixture(save=None):
    instance = GameInstance(game_key=("web", "cast", "bot"), gm_uid="gm")
    instance.log = [{"round": round_, "story": {"version": 1, "segments": [{
        "id": "beat_0", "kind": "dialogue", "speaker_id": ref,
        "speaker_name": "报童", "text": "晚报。",
    }]}} for round_, ref in [(3, GUEST), (4, GUEST), (5, KNOWN)]]

    async def saved(_instance):
        if save:
            await save(_instance)

    service = StorytellingService(StorytellingDependencies(
        parse_game_key=lambda _key: instance.game_key,
        get_instance=lambda _key: instance, save_instance=saved,
        validate_portrait=lambda value: value,
    ))
    return instance, service


@pytest.mark.asyncio
async def test_explicit_guest_promotion_repairs_cast_and_projection_without_rewriting_history():
    instance, service = fixture()
    before = deepcopy(instance.log)
    storytelling.set_portrait(instance, GUEST, {"kind": "builtin", "id": "guest-avatar"})
    assert service.list_speakers("cast")["total"] == 2

    result = await service.merge_speakers("cast", GUEST, KNOWN)

    assert result["ok"], result
    assert instance.log == before
    assert service.list_speakers("cast")["total"] == 1
    assert set(speaker_catalog(instance)) == {KNOWN}
    restored = GameInstance.from_dict(instance.to_dict())
    for row in restored.log:
        segment = public_story(restored, row["story"])["segments"][0]
        assert segment["speaker_id"] == KNOWN
        assert segment["portrait"] == {"kind": "builtin", "id": "guest-avatar"}


def test_same_named_distinct_actors_remain_separate_without_explicit_identity_repair():
    instance, service = fixture()
    before = deepcopy(instance.to_dict())
    assert service.list_speakers("cast")["total"] == 2
    assert len(speaker_catalog(instance)) == 2
    assert instance.to_dict() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["different-persona", "missing", "canonical-source", "busy", "future"])
async def test_unsafe_identity_repairs_fail_without_mutation(invalid):
    instance, service = fixture()
    source, target = GUEST, KNOWN
    if invalid == "different-persona":
        instance.log[-1]["story"]["segments"][0]["speaker_name"] = "蒙面人"
    elif invalid == "missing":
        source = "g_aaaaaaaaaaaaaaaaaaaa"
    elif invalid == "canonical-source":
        source, target = KNOWN, GUEST
    elif invalid == "busy":
        instance.state = GameState.ACTIVE_JUDGMENT
    else:
        instance.modules["storytelling"] = {"schema_version": 99, "opaque": [1]}
    before = deepcopy(instance.to_dict())
    result = await service.merge_speakers("cast", source, target)
    assert result["ok"] is False
    assert instance.to_dict() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_identity_repair_rolls_back_if_durable_save_fails(cancelled):
    async def fail(_instance):
        raise asyncio.CancelledError() if cancelled else OSError("disk full")
    instance, service = fixture(fail)
    before = deepcopy(instance.to_dict())
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await service.merge_speakers("cast", GUEST, KNOWN)
    else:
        assert (await service.merge_speakers("cast", GUEST, KNOWN))["error_code"] == "SAVE_FAILED"
    assert instance.to_dict() == before


@pytest.mark.asyncio
async def test_identity_repair_does_not_cross_run_boundaries():
    instance, service = fixture()
    assert (await service.merge_speakers("cast", GUEST, KNOWN))["ok"]
    candidate = GameInstance(game_key=instance.game_key, gm_uid="gm")
    storytelling.copy_preferences(candidate, instance)
    assert storytelling.speaker_aliases(candidate) == {}
    storytelling.restore_preferences(instance, storytelling.preference_snapshot(instance))
    assert storytelling.speaker_aliases(instance) == {}


@pytest.mark.asyncio
async def test_only_gm_can_confirm_identity_repair():
    from src.webui.routes import games
    instance, service = fixture()

    class API:
        def get_game_instance(self, _key):
            return instance

        async def merge_story_speakers(self, key, source, target):
            return await service.merge_speakers(key, source, target)

    class Request:
        app = {"api": API()}
        match_info = {"game_key": "cast"}

        def __init__(self, uid):
            self.uid = uid

        def get(self, key, default=None):
            return {"user_id": self.uid, "owner_authenticated": False}.get(key, default)

        async def json(self):
            return {"source_id": GUEST, "target_id": KNOWN}

    before = deepcopy(instance.to_dict())
    assert (await games.api_merge_story_speakers(Request("player"))).status == 403
    assert instance.to_dict() == before
    assert (await games.api_merge_story_speakers(Request("gm"))).status == 200
