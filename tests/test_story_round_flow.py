"""Character dialogue survives the real generation, log and branch boundaries."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from src.commands.round_llm import call_llm_with_tag_retry
from src.engine.game_instance import GameInstance
from src.engine.modules import storytelling
from src.engine.story import parse_story, story_text
from src.llm.client import LLMResponse
from src.webui.services import logs


def game():
    instance = GameInstance(game_key=("web", "story-flow", "bot"))
    storytelling.replace_mode(instance, "dialogue")
    return instance


def wire(text="晚上好。", speaker="new:traveler"):
    return json.dumps({"kind": "dialogue", "speaker": speaker, "name": "旅人", "text": text}, ensure_ascii=False) + "\n---\nNONE"


class Model:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def call(self, **kwargs):
        return self.response()

    def response(self):
        content = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return LLMResponse(content=content, narration=content.split("---")[0], total_tokens=10,
                           state_update=None, memory_delta=None, info_asymmetry=None,
                           plot_update=None, is_narration_only=False, provider_used="story-test")

    async def call_stream(self, on_delta=None, **kwargs):
        response = self.response()
        for offset in range(0, len(response.content), 9):
            await on_delta(response.content[offset:offset + 9])
        return response


class Sink:
    def __init__(self):
        self.text = ""
        self.stories = []
        self.resets = 0

    async def __call__(self, text):
        self.text += text

    async def story_update(self, story):
        self.stories.append(deepcopy(story))

    async def reset(self):
        self.text = ""
        self.stories = []
        self.resets += 1


@pytest.mark.asyncio
async def test_real_llm_flow_returns_plain_text_and_structured_story_without_extra_call():
    instance, sink = game(), Sink()
    model = Model([wire()])
    response, _ = await call_llm_with_tag_retry(model, instance, "GM", "context", "narrative", "", 1024, on_delta=sink, on_reset=sink.reset)
    assert response.narration == "旅人：晚上好。"
    assert response.story["segments"][0]["kind"] == "dialogue"
    assert sink.text == response.narration
    assert sink.stories[-1] == response.story
    assert model.calls == 1
    assert "new:" not in sink.text
    assert "NONE" not in sink.text


@pytest.mark.asyncio
async def test_bad_story_format_retries_then_degrades_to_public_narration():
    instance, sink = game(), Sink()
    model = Model(["普通正文。\n---\nNONE", wire()])
    response, _ = await call_llm_with_tag_retry(model, instance, "GM", "context", "narrative", "", 1024, on_delta=sink, on_reset=sink.reset)
    assert response.story["segments"][0]["kind"] == "dialogue"
    assert model.calls == 2 and sink.resets >= 1
    assert sink.text == response.narration
    fallback = Model(["普通正文。\n---\nNONE"])
    response, _ = await call_llm_with_tag_retry(fallback, instance, "GM", "context", "narrative", "", 1024)
    assert response.story["segments"][0]["kind"] == "narration"
    assert response.narration == "普通正文。"
    assert fallback.calls == 2


@pytest.mark.asyncio
async def test_long_story_is_bounded_without_flattening_speakers():
    instance = game()
    model = Model([wire("很长的台词。" * 200)])
    response, data = await call_llm_with_tag_retry(model, instance, "GM", "context", "narrative", "", 1024)
    assert response.story["segments"][0]["kind"] == "dialogue"
    assert len(response.narration) <= 400
    assert response.narration == story_text(response.story)
    assert data["quick_actions"] == []


@pytest.mark.asyncio
async def test_round_save_reload_and_swipe_keep_matching_story():
    instance = game()
    first = parse_story(instance, wire().split("---")[0])
    second = parse_story(instance, wire("请进。").split("---")[0], revision=1)
    await instance.finish_judgment(story_text(first), story=first)
    round_number = instance.log[-1]["round"]
    await instance.finish_judgment_with_swipe(story_text(second), round_number, story=second)
    assert instance.log[-1]["story"] == second
    assert instance.log[-1]["swipe_stories"] == [first, second]
    restored = GameInstance.from_dict(instance.to_dict())
    assert restored.log[-1]["story"] == second
    assert await restored.switch_swipe(round_number, 0)
    assert restored.log[-1]["story"] == first
    assert restored.log[-1]["gm_response"] == story_text(first)
    await restored.finish_judgment_with_swipe("旧格式分支", round_number)
    assert "story" not in restored.log[-1]
    assert await restored.switch_swipe(round_number, 1)
    assert restored.log[-1]["story"] == second


def test_player_log_projects_safe_story_and_avatar_overrides():
    instance = game()
    story = parse_story(instance, wire().split("---")[0])
    ref = story["segments"][0]["speaker_id"]
    storytelling.set_portrait(instance, ref, {"kind": "builtin", "id": "freeform_fantasy:1"})
    story["segments"][0]["source_ref"] = "secret_traitor_001"
    instance.log.append({"round": 1, "gm_response": story_text(story), "story": story, "swipe_stories": [story]})
    before = deepcopy(instance.to_dict())
    dependencies = logs.LogDependencies(registry={instance.game_key: instance}, parse_game_key=lambda _: instance.game_key)
    result = logs.get_log(dependencies, "story")
    segment = result["log"][0]["story"]["segments"][0]
    assert segment["portrait"]["id"] == "freeform_fantasy:1"
    assert "source_ref" not in segment
    assert "swipe_stories" not in result["log"][0]
    assert "secret_traitor" not in json.dumps(result)
    assert instance.to_dict() == before
