import pytest

from src.webui.services.assistant_content import AgentContentDependencies, AgentContentTools


@pytest.mark.asyncio
async def test_non_text_draft_generates_one_reviewable_fragment():
    calls = []

    async def generate(prompt, system_hint, language):
        calls.append((prompt, system_hint, language))
        return {"ok": True, "text": "# Harbor\n\nA fogbound port open to every traveler."}

    def review_content(body):
        return {"ok": True, "draft": body, "plan_digest": "sha256:" + "a" * 64, "blockers": []}

    tools = AgentContentTools(AgentContentDependencies(generate, review_content, lambda body: body))
    result = await tools.draft("world", "A fogbound port with a cursed bell", "en")

    assert result["kind"] == "world"
    assert result["draft"]["filename"] == "agent.md"
    assert result["draft"]["language"] == "en"
    assert result["draft"]["source_id"].startswith("agent-")
    assert len(result["draft"]["items"]) == 1
    item = result["draft"]["items"][0]
    assert item["target"] == "world"
    assert item["references"] == []
    assert item["text"].startswith("# Harbor")
    assert calls and "language `en`" in calls[0][1]
    assert "public-only" in calls[0][1]
    assert "GM-only hidden material is supported only for adventures" in calls[0][1]
    assert "GM guidance" not in calls[0][1]


@pytest.mark.parametrize("text", [
    "# Harbor\nGM: The bell is cursed.",
    "# Harbor\n## GM-only\nThe bell is cursed.",
    "# Harbor\n## 秘密\nThe bell is cursed.",
    "# Harbor\nThe secret is the bell.",
])
@pytest.mark.asyncio
async def test_public_content_rejects_hidden_markers_before_review(text):
    review_calls = []

    async def generate(prompt, system_hint, language):
        return {"ok": True, "text": text}

    def review_content(body):
        review_calls.append(body)
        return {"ok": True}

    tools = AgentContentTools(AgentContentDependencies(generate, review_content, lambda body: body))
    result = await tools.draft("world", "A public harbor", "en")

    assert result["ok"] is False
    assert "private or hidden" in result["error"]
    assert review_calls == []


@pytest.mark.asyncio
async def test_adventure_outer_title_is_removed_before_script_review():
    from src.adventures.script_import import parse_script

    reviewed = []

    async def generate(prompt, system_hint, language):
        return {"ok": True, "text": "# Harbor Bell\n## Arrival\n### Dock {#dock}\nA fogbound dock.\nGM: The bell is cursed."}

    def review_content(body):
        reviewed.append(body)
        return {"ok": True, "draft": body, "plan_digest": "sha256:" + "c" * 64, "blockers": []}

    tools = AgentContentTools(AgentContentDependencies(generate, review_content, lambda body: body))
    result = await tools.draft("adventure", "A short harbor adventure", "en")

    body = reviewed[0]
    item = body["items"][0]
    assert item["name"] == "Harbor Bell"
    assert item["text"].startswith("## Arrival")
    parsed = parse_script(
        f"# {item['name']}\n{item['text']}".encode(),
        "agent.md",
        {},
        "en",
    )
    assert len(parsed["files"]["adventure.json"]["chapters"]) == 1
    assert parsed["files"]["adventure.json"]["chapters"][0]["name"] == "Arrival"
    assert result["kind"] == "adventure"


@pytest.mark.asyncio
async def test_text_draft_does_not_enter_review_or_commit():
    review_calls = []
    commit_calls = []

    async def generate(prompt, system_hint, language):
        return {"ok": True, "text": "A concise answer."}

    def review_content(body):
        review_calls.append(body)
        return {"ok": True}

    def commit_content(body):
        commit_calls.append(body)
        return {"ok": True}

    tools = AgentContentTools(AgentContentDependencies(generate, review_content, commit_content))
    result = await tools.draft("text", "Explain the harbor", "en")

    assert result == {"ok": True, "kind": "text", "text": "A concise answer."}
    assert review_calls == []
    assert commit_calls == []


@pytest.mark.asyncio
async def test_generation_failure_does_not_review_or_commit():
    review_calls = []

    async def generate(prompt, system_hint, language):
        return {"ok": False, "error": "provider unavailable"}

    def review_content(body):
        review_calls.append(body)
        return {"ok": True}

    tools = AgentContentTools(AgentContentDependencies(generate, review_content, lambda body: body))
    result = await tools.draft("adventure", "A short quest", "en")

    assert result == {"ok": False, "kind": "adventure", "error": "provider unavailable"}
    assert review_calls == []


def test_review_delegates_only_the_reviewable_draft_and_commit_requires_clear_review():
    review_calls = []
    commit_calls = []

    def review_content(body):
        review_calls.append(body)
        return {"ok": True, "draft": body, "plan_digest": "sha256:" + "b" * 64, "blockers": []}

    def commit_content(body):
        commit_calls.append(body)
        return {"ok": True, "saved": True}

    tools = AgentContentTools(AgentContentDependencies(lambda *_: None, review_content, commit_content))
    draft = {"source_id": "agent-123", "filename": "agent.md", "language": "en", "items": []}
    checked = tools.review({"kind": "lorebook", "draft": draft})
    assert checked["kind"] == "lorebook"
    assert review_calls == [draft]

    assert tools.commit(checked) == {"ok": True, "saved": True}
    assert commit_calls == [{**draft, "reviewed": True, "plan_digest": "sha256:" + "b" * 64}]

    checked["blockers"] = ["blocked"]
    with pytest.raises(ValueError, match="blocking"):
        tools.commit(checked)
    assert len(commit_calls) == 1


def test_edited_adventure_targeted_to_public_content_rejects_private_markers_before_review_or_commit():
    review_calls = []
    commit_calls = []
    body = {
        "source_id": "agent-adventure",
        "filename": "agent.md",
        "language": "en",
        "items": [{
            "id": "scene",
            "name": "Harbor",
            "text": "Public setup\nGM: hidden betrayal",
            "target": "world",
            "references": [],
        }],
    }

    def review_content(value):
        review_calls.append(value)
        return {"ok": True, "draft": value, "plan_digest": "sha256:" + "d" * 64, "blockers": []}

    def commit_content(value):
        commit_calls.append(value)
        return {"ok": True}

    tools = AgentContentTools(AgentContentDependencies(lambda *_: None, review_content, commit_content))
    with pytest.raises(ValueError, match="private or hidden"):
        tools.review({"kind": "adventure", "draft": body})
    with pytest.raises(ValueError, match="private or hidden"):
        tools.commit({"kind": "adventure", "draft": body, "plan_digest": "sha256:" + "d" * 64, "blockers": []})
    assert review_calls == []
    assert commit_calls == []


@pytest.mark.parametrize("kind", ["", "unknown", 1, None])
@pytest.mark.asyncio
async def test_draft_rejects_invalid_kind(kind):
    async def generate(prompt, system_hint, language):
        raise AssertionError("generation should not run")

    tools = AgentContentTools(AgentContentDependencies(generate, lambda body: body, lambda body: body))
    with pytest.raises((TypeError, ValueError)):
        await tools.draft(kind, "prompt", "en")


@pytest.mark.asyncio
async def test_draft_rejects_invalid_language_and_oversized_prompt():
    async def generate(prompt, system_hint, language):
        raise AssertionError("generation should not run")

    tools = AgentContentTools(AgentContentDependencies(generate, lambda body: body, lambda body: body))
    with pytest.raises((TypeError, ValueError)):
        await tools.draft("text", "prompt", "fr")
    with pytest.raises((TypeError, ValueError)):
        await tools.draft("text", "x" * 8193, "en")
