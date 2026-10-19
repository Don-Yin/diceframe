from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.engine.game_instance import GameInstance, GameState
from src.engine.module_state import ModuleStateError
from src.engine.modules import storytelling
from src.webui.routes import games
from src.webui.services.storytelling import StorytellingDependencies, StorytellingService


SPEAKER_ID = "s_0123456789abcdef0123"


def _instance(*, mode: str = "prose") -> GameInstance:
    instance = GameInstance(game_key=("web", "story", "bot"), gm_uid="gm")
    storytelling.replace_mode(instance, mode)
    instance.log.append({
        "round": 1,
        "story": {"segments": [{"speaker_id": SPEAKER_ID, "text": "hello"}]},
    })
    return instance


def test_storytelling_slot_defaults_and_validates_mode() -> None:
    instance = GameInstance(game_key=("web", "story-default", "bot"))
    instance.modules.pop("storytelling", None)
    assert storytelling.read_mode(instance) == "prose"
    assert storytelling.portrait_overrides(instance) == {}
    assert "storytelling" not in instance.modules
    assert storytelling.mode(instance) == "prose"
    assert storytelling.portraits(instance) == {}


@pytest.mark.parametrize("bad_mode", [None, "", "legacy", {}, []])
def test_storytelling_invalid_persisted_mode_defaults_to_prose(bad_mode) -> None:
    instance = GameInstance(
        game_key=("web", "story-invalid", "bot"),
        modules={"storytelling": {"schema_version": 1, "mode": bad_mode, "portraits": {}}},
    )
    assert storytelling.read_mode(instance) == "prose"
    with pytest.raises(ValueError):
        storytelling.replace_mode(instance, "invalid")
    assert storytelling.mode(instance) == "prose"


def test_storytelling_unknown_schema_fails_closed_without_mutation() -> None:
    instance = GameInstance(
        game_key=("web", "story-future", "bot"),
        modules={"storytelling": {"schema_version": 99, "mode": "dialogue", "portraits": {}}},
    )
    before = deepcopy(instance.modules)
    with pytest.raises(ModuleStateError):
        storytelling.replace_mode(instance, "prose")
    assert instance.modules == before


def test_clearing_portrait_keeps_explicit_null_override() -> None:
    instance = _instance()
    storytelling.set_portrait(instance, SPEAKER_ID, None)
    assert SPEAKER_ID in storytelling.portrait_overrides(instance)
    assert storytelling.portrait_overrides(instance)[SPEAKER_ID] is None


def test_copy_preferences_keeps_stable_npc_portraits_and_drops_guests() -> None:
    source = GameInstance(
        game_key=("web", "story-source", "bot"),
        run_id="source-run",
    )
    candidate = GameInstance(
        game_key=("web", "story-candidate", "bot"),
        run_id="candidate-run",
    )
    npc_id = "s_0123456789abcdef0123"
    guest_id = "g_0123456789abcdef0123"
    storytelling.replace_mode(source, "dialogue")
    storytelling.set_portrait(source, npc_id, {"kind": "builtin", "id": "npc"})
    storytelling.set_portrait(source, guest_id, {"kind": "builtin", "id": "guest"})

    storytelling.copy_preferences(candidate, source)

    assert storytelling.mode(candidate) == "dialogue"
    assert storytelling.identity_namespace(source) == "source-run"
    assert storytelling.identity_namespace(candidate) == "source-run"
    assert storytelling.portrait_overrides(candidate) == {
        npc_id: {"kind": "builtin", "id": "npc"},
    }


def test_story_speaker_list_projects_all_history_with_newest_dedup_and_overrides() -> None:
    instance = GameInstance(game_key=("web", "story-cast", "bot"), gm_uid="gm")
    first = "s_0123456789abcdef0123"
    second = "s_abcdef01234567890123"
    guest = "g_0123456789abcdef0123"
    discarded = "s_aaaaaaaaaaaaaaaaaaaa"
    instance.log = [
        {
            "story": {
                "version": 1,
                "segments": [
                    {"kind": "dialogue", "speaker_id": first, "speaker_name": "旧名字", "text": "old", "gm_note": "secret"},
                    {"kind": "dialogue", "speaker_id": second, "speaker_name": "第二人", "text": "two"},
                ],
            },
            "swipe_stories": [{"version": 1, "segments": [{"kind": "dialogue", "speaker_id": discarded, "speaker_name": "discarded", "text": "no"}]}],
        },
        {
            "story": {
                "version": 1,
                "segments": [
                    {"kind": "dialogue", "speaker_id": first, "speaker_name": "新名字", "text": "new", "canonical_id": "private"},
                    {"kind": "dialogue", "speaker_id": guest, "speaker_name": "旅人", "text": "guest"},
                ],
            },
        },
    ]
    storytelling.set_portrait(instance, first, {"kind": "builtin", "id": "override"})
    service = StorytellingService(StorytellingDependencies(
        parse_game_key=lambda _key: ("web", "story-cast", "bot"),
        get_instance=lambda _key: instance,
        save_instance=lambda _instance: None,
        validate_portrait=lambda portrait: portrait,
    ))

    result = service.list_speakers("web|story-cast|bot")

    assert result["ok"] is True
    assert result["total"] == 3
    assert result["speakers"] == [
        {"id": first, "name": "新名字", "portrait": {"kind": "builtin", "id": "override"}},
        {"id": guest, "name": "旅人"},
        {"id": second, "name": "第二人"},
    ]


@pytest.mark.asyncio
async def test_story_speaker_route_is_gm_only_and_empty_cast_is_valid() -> None:
    instance = GameInstance(game_key=("web", "story-empty", "bot"), gm_uid="gm")

    class API:
        def get_game_instance(self, _key):
            return instance

        def list_story_speakers(self, _game_key):
            return {"ok": True, "speakers": [], "total": 0}

    class Request:
        app = {"api": API()}
        match_info = {"game_key": "web|story-empty|bot"}

        def __init__(self, uid):
            self.uid = uid

        def get(self, key, default=None):
            return {"user_id": self.uid, "owner_authenticated": False}.get(key, default)

    denied = await games.api_story_speakers(Request("player"))
    assert denied.status == 403
    allowed = await games.api_story_speakers(Request("gm"))
    assert allowed.status == 200


@pytest.mark.asyncio
async def test_story_mode_save_failure_rolls_back_only_storytelling_slot() -> None:
    instance = _instance()
    instance.modules["unrelated"] = {"keep": [1]}

    async def save(_instance):
        raise OSError("disk full")

    service = StorytellingService(StorytellingDependencies(
        parse_game_key=lambda _key: ("web", "story", "bot"),
        get_instance=lambda _key: instance,
        save_instance=save,
        validate_portrait=lambda portrait: portrait,
    ))
    before = deepcopy(instance.modules)
    result = await service.set_mode("web|story|bot", "dialogue")
    assert result["ok"] is False
    assert result["error_code"] == "SAVE_FAILED"
    assert instance.modules == before


@pytest.mark.asyncio
async def test_story_mode_save_failure_preserves_absent_slot() -> None:
    instance = _instance()
    instance.modules.pop("storytelling", None)

    async def save(_instance):
        raise OSError("disk full")

    service = StorytellingService(StorytellingDependencies(
        parse_game_key=lambda _key: ("web", "story", "bot"),
        get_instance=lambda _key: instance,
        save_instance=save,
        validate_portrait=lambda portrait: portrait,
    ))
    result = await service.set_mode("web|story|bot", "dialogue")
    assert result["error_code"] == "SAVE_FAILED"
    assert "storytelling" not in instance.modules


@pytest.mark.asyncio
async def test_portrait_can_edit_speaker_from_older_selected_story() -> None:
    instance = _instance()
    older_id = "g_0123456789abcdef0123"
    instance.log.insert(0, {
        "round": 0,
        "story": {"segments": [{"speaker_id": older_id, "text": "old"}]},
        "swipe_stories": [{"segments": [{"speaker_id": "s_aaaaaaaaaaaaaaaaaaaa"}]}],
    })
    saved = False

    async def save(_instance):
        nonlocal saved
        saved = True

    service = StorytellingService(StorytellingDependencies(
        parse_game_key=lambda _key: ("web", "story", "bot"),
        get_instance=lambda _key: instance,
        save_instance=save,
        validate_portrait=lambda portrait: portrait,
    ))
    result = await service.set_portrait("web|story|bot", older_id, {"kind": "builtin", "id": "x"})
    assert result["ok"] is True
    assert saved is True
    assert storytelling.portrait_overrides(instance)[older_id] == {"kind": "builtin", "id": "x"}
    discarded = await service.set_portrait(
        "web|story|bot", "s_aaaaaaaaaaaaaaaaaaaa", {"kind": "builtin", "id": "x"},
    )
    assert discarded["error_code"] == "UNKNOWN_SPEAKER"


@pytest.mark.asyncio
async def test_portrait_membership_is_rechecked_after_authority_gate() -> None:
    instance = _instance()
    speaker = SPEAKER_ID

    @asynccontextmanager
    async def gate():
        instance.log.clear()
        yield True

    instance.authoritative_write = gate
    service = StorytellingService(StorytellingDependencies(
        parse_game_key=lambda _key: ("web", "story", "bot"),
        get_instance=lambda _key: instance,
        save_instance=lambda _instance: pytest.fail("must not save"),
        validate_portrait=lambda portrait: portrait,
    ))
    result = await service.set_portrait("web|story|bot", speaker, {"kind": "builtin", "id": "x"})
    assert result["error_code"] == "UNKNOWN_SPEAKER"
    assert storytelling.portrait_overrides(instance) == {}


@pytest.mark.asyncio
async def test_storytelling_write_rolls_back_and_reraises_cancellation() -> None:
    instance = _instance()
    before = deepcopy(instance.modules)

    async def save(_instance):
        raise asyncio.CancelledError()

    service = StorytellingService(StorytellingDependencies(
        parse_game_key=lambda _key: ("web", "story", "bot"),
        get_instance=lambda _key: instance,
        save_instance=save,
        validate_portrait=lambda portrait: portrait,
    ))
    with pytest.raises(asyncio.CancelledError):
        await service.set_mode("web|story|bot", "dialogue")
    assert instance.modules == before


@pytest.mark.asyncio
async def test_story_mode_rejects_during_active_judgment_and_inflight_generation() -> None:
    instance = _instance()
    service = StorytellingService(StorytellingDependencies(
        parse_game_key=lambda _key: ("web", "story", "bot"),
        get_instance=lambda _key: instance,
        save_instance=lambda _instance: pytest.fail("must not save"),
        validate_portrait=lambda portrait: portrait,
    ))
    instance.state = GameState.ACTIVE_JUDGMENT
    result = await service.set_mode("web|story|bot", "dialogue")
    assert result["error_code"] == "STORY_MODE_LOCKED"
    instance.state = GameState.CREATED
    instance.round_processing_in_flight = lambda: True
    result = await service.set_mode("web|story|bot", "dialogue")
    assert result["error_code"] == "STORY_MODE_LOCKED"


@pytest.mark.asyncio
async def test_portrait_rejects_unknown_speaker_and_invalid_portrait() -> None:
    instance = _instance()
    service = StorytellingService(StorytellingDependencies(
        parse_game_key=lambda _key: ("web", "story", "bot"),
        get_instance=lambda _key: instance,
        save_instance=lambda _instance: None,
        validate_portrait=lambda _portrait: (_ for _ in ()).throw(ValueError("invalid portrait")),
    ))
    unknown = await service.set_portrait("web|story|bot", "s_aaaaaaaaaaaaaaaaaaaa", {"kind": "builtin", "id": "x"})
    assert unknown["error_code"] == "UNKNOWN_SPEAKER"
    invalid = await service.set_portrait("web|story|bot", SPEAKER_ID, {"kind": "bad"})
    assert invalid["error_code"] == "INVALID_PORTRAIT"
    assert storytelling.portraits(instance) == {}


@pytest.mark.asyncio
async def test_story_mode_route_is_gm_only() -> None:
    instance = _instance()
    calls: list[tuple] = []

    class API:
        def get_game_instance(self, _key):
            return instance

        async def set_story_mode(self, game_key, mode):
            calls.append((game_key, mode))
            return {"ok": True, "story_mode": mode}

    class Request:
        app = {"api": API()}
        match_info = {"game_key": "web|story|bot"}
        headers = {}

        def __init__(self, uid):
            self.uid = uid

        def get(self, key, default=None):
            return {"user_id": self.uid, "owner_authenticated": False}.get(key, default)

        async def json(self):
            return {"mode": "dialogue"}

    response = await games.api_set_story_mode(Request("player"))
    assert response.status == 403
    assert calls == []


@pytest.mark.asyncio
async def test_story_mode_route_broadcasts_generic_refresh_event() -> None:
    instance = _instance()
    calls: list[tuple] = []

    class Pool:
        async def broadcast(self, game_key, payload):
            calls.append((game_key, payload))

    class API:
        def get_game_instance(self, _key):
            return instance

        async def set_story_mode(self, game_key, mode):
            return {"ok": True, "story_mode": mode}

    class Request:
        app = {"api": API(), "connection_pool": Pool()}
        match_info = {"game_key": "web|story|bot"}

        def get(self, key, default=None):
            return {"user_id": "gm", "owner_authenticated": False}.get(key, default)

        async def json(self):
            return {"mode": "dialogue"}

    response = await games.api_set_story_mode(Request())
    assert response.status == 200
    assert calls == [("web|story|bot", {"type": "story_settings_changed"})]
