"""AI authored content adapter.

This module only turns generated prose into the existing content-text review
contract.  Content owners remain responsible for validation and persistence;
the adapter never calls a direct world/adventure creation API.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from src.engine.language import SUPPORTED_LANGUAGES


_KINDS = frozenset({"world", "lorebook", "character_template", "adventure", "text"})
_MAX_PROMPT_CHARS = 8192
_MAX_LANGUAGE_CHARS = 16
_MAX_GENERATED_BYTES = 512 * 1024
_HEADING = re.compile(r"^#{1,3}\s+(.+?)\s*$")
_LEVEL_ONE_HEADING = re.compile(r"^#\s+.+$", re.IGNORECASE)
_EXPLICIT_ID = re.compile(r"\s*\{#[a-z0-9][a-z0-9_.-]*\}\s*$")
# Public prose may legitimately mention a secret, a host, or a hidden rumor.
# Treat only explicit section/line labels as visibility markers; a lexical
# occurrence inside an ordinary sentence is not enough to reject the draft.
_PRIVATE_HEADING_MARKER = re.compile(
    r"(?i)^(?:"
    r"gm(?:\s*[- ]\s*only)?(?:\s+(?:notes?|guidance|information|section))?|"
    r"secret(?:s)?(?:\s+(?:notes?|information|section))?|"
    r"private(?:\s+(?:notes?|information|section))?|"
    r"hidden(?:\s+(?:notes?|information|section))?|"
    r"秘密(?:信息|笔记|内容|段落|提示)?|"
    r"机密(?:信息|笔记|内容|段落|提示)?|"
    r"主持人(?:备注|笔记|信息|内容|段落|提示)?"
    r")\s*[:：]?\s*$"
)
_PRIVATE_TEXT_MARKER = re.compile(
    r"(?i)^(?:"
    r"gm\s*:\s*|"
    r"gm\s*[- ]\s*only(?=\s|[:：]|$)|"
    r"gm\s+(?:notes?|guidance|information|section)\s*[:：]\s*|"
    r"(?:secret(?:s)?|private|hidden)(?:\s+(?:notes?|information|section))?\s*[:：]\s*|"
    r"(?:秘密|机密|主持人(?:备注|笔记|信息|内容|段落|提示)?)\s*[:：]\s*"
    r")"
)


@dataclass(frozen=True)
class AgentContentDependencies:
    """Callbacks supplied by the application composition root."""

    generate_text: Callable[[str, str, str], Awaitable[dict[str, Any]]]
    review_content: Callable[[dict[str, Any]], dict[str, Any]]
    commit_content: Callable[[dict[str, Any]], dict[str, Any]]


def _validate_kind(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("content kind must be a string")
    if value not in _KINDS:
        raise ValueError("unsupported content kind")
    return value


def _validate_prompt(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("content prompt must be a string")
    if not value.strip():
        raise ValueError("content prompt must be nonempty")
    if len(value) > _MAX_PROMPT_CHARS:
        raise ValueError("content prompt is too long")
    return value.strip()


def _validate_language(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("content language must be a string")
    if not value or len(value) > _MAX_LANGUAGE_CHARS or value not in SUPPORTED_LANGUAGES:
        raise ValueError("unsupported content language")
    return value


def _generated_failure(kind: str, error: object) -> dict[str, Any]:
    message = str(error or "text generation failed")
    return {"ok": False, "kind": kind, "error": message}


def _has_private_markers(text: str) -> bool:
    """Reject explicit private markers before text reaches a public owner."""

    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"(?i)^gm\s*:", stripped):
            return True
        heading = _HEADING.fullmatch(stripped)
        if heading and _PRIVATE_HEADING_MARKER.search(heading.group(1)):
            return True
        if _PRIVATE_TEXT_MARKER.search(stripped):
            return True
    return False


def _title(text: str, kind: str) -> str:
    for line in text.splitlines():
        match = _HEADING.fullmatch(line.strip())
        if match:
            value = _EXPLICIT_ID.sub("", match.group(1)).strip()
            if value:
                return value[:200]
    return {
        "world": "AI World",
        "lorebook": "AI Lorebook",
        "character_template": "AI Character Template",
        "adventure": "AI Adventure",
    }[kind]


def _system_hint(kind: str, language: str) -> str:
    if kind in {"world", "lorebook", "character_template"}:
        audience = (
            "This target currently accepts a player-safe public-only draft. Do not include GM notes, hidden "
            "information, secrets, or private sections; GM-only hidden material is supported only for adventures."
        )
    elif kind == "adventure":
        audience = (
            "Adventure scripts may include public material and GM-only notes. Put a GM-only note on a line "
            "beginning exactly with `GM:`; this private marker is supported only by the adventure parser."
        )
    else:
        audience = "Answer as ordinary text; this result is informational and is not a content commit candidate."
    common = (
        f"You author DiceFrame content in language `{language}`. Return complete, usable Markdown prose only; "
        "do not return JSON, metadata, commentary, or a surrounding code fence. Make the content sufficiently "
        f"detailed to use immediately. {audience} Do not invent unsupported protocol markers or hidden mechanics."
    )
    if kind == "world":
        return common + (
            " Create one coherent world setting with its identity, places, factions, conflicts, tone, and useful "
            "starting context. Keep all setting descriptions player-safe and public."
        )
    if kind == "lorebook":
        return common + (
            " Create one coherent lorebook as a single complete document. Include a title and organized Markdown "
            "sections when useful; keep related knowledge together instead of producing separate books."
        )
    if kind == "character_template":
        return common + (
            " Create one complete reusable character template with identity, appearance, personality, background, "
            "motivations, relationships, and public guidance. Do not assert rules statistics as authoritative mechanics."
        )
    if kind == "adventure":
        return common + (
            " Create one playable adventure script. Use only the markers supported by DiceFrame's script parser: "
            "level 1-3 Markdown headings (`#`, `##`, `###`) for title/chapter/scene, optional `{#scene-id}` on "
            "scene headings, `GM:` lines for GM notes, `@npc value`, `@location value`, `@encounter value`, and "
            "`@choice label -> scene-id` for choices. Put each marker on its own line, keep scene ids lowercase "
            "ASCII, and do not make up other control syntax."
        )
    return common + " Answer the user's request directly as ordinary prose."


def _body(kind: str, text: str, language: str) -> dict[str, Any]:
    content_text = text
    if kind == "adventure":
        # ContentTextReview.prepare adds the canonical outer ``# title``.
        # Dropping only a duplicate generated level-one title preserves all
        # subsequent parser headings, chapters, scenes, and GM notes.
        lines = text.splitlines()
        if lines and _LEVEL_ONE_HEADING.fullmatch(lines[0].strip()):
            content_text = "\n".join(lines[1:]).strip()
    return {
        "source_id": f"agent-{uuid.uuid4()}",
        "filename": "agent.md",
        "language": language,
        # Keep a lorebook as one complete book fragment. The existing review
        # service can split user-authored text, but doing so here would turn
        # one generated work into many independent resources.
        "items": [{
            "id": f"{kind}_content",
            "name": _title(text, kind),
            "text": content_text,
            "target": kind,
            "references": [],
        }],
    }


def _reject_private_public_items(body: dict[str, Any]) -> None:
    """Enforce visibility from the edited item's actual target, not outer kind."""

    items = body.get("items")
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        target = item.get("target")
        text = item.get("text")
        if target in {"world", "lorebook", "character_template"} and isinstance(text, str):
            if _has_private_markers(text):
                raise ValueError("private or hidden markers cannot be saved to public content")


class AgentContentTools:
    """Draft, review, and commit AI-authored content through existing owners."""

    def __init__(self, deps: AgentContentDependencies):
        self.deps = deps

    async def draft(self, kind: str, prompt: str, language: str) -> dict[str, Any]:
        kind = _validate_kind(kind)
        prompt = _validate_prompt(prompt)
        language = _validate_language(language)
        generated = await self.deps.generate_text(prompt, _system_hint(kind, language), language)
        if not isinstance(generated, dict) or generated.get("ok") is not True:
            error = generated.get("error") if isinstance(generated, dict) else "invalid text generation response"
            return _generated_failure(kind, error)
        text = generated.get("text")
        if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > _MAX_GENERATED_BYTES:
            return _generated_failure(kind, "generated content is empty or too large")
        text = text.strip()
        if kind == "text":
            return {"ok": True, "kind": "text", "text": text}
        if kind in {"world", "lorebook", "character_template"} and _has_private_markers(text):
            return _generated_failure(kind, "generated content contains private or hidden markers")
        checked = self.deps.review_content(_body(kind, text, language))
        if not isinstance(checked, dict):
            raise TypeError("content review must return an object")
        return {**checked, "kind": kind}

    def review(self, draft: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(draft, dict):
            raise TypeError("content draft must be an object")
        kind = _validate_kind(draft.get("kind"))
        if kind == "text":
            raise ValueError("text drafts are not commit candidates")
        body = draft.get("draft")
        if not isinstance(body, dict):
            raise ValueError("reviewable content draft is required")
        _reject_private_public_items(body)
        checked = self.deps.review_content(body)
        if not isinstance(checked, dict):
            raise TypeError("content review must return an object")
        return {**checked, "kind": kind}

    def commit(self, checked: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(checked, dict):
            raise TypeError("review result must be an object")
        kind = _validate_kind(checked.get("kind"))
        if kind == "text":
            raise ValueError("text drafts cannot be committed")
        blockers = checked.get("blockers", [])
        if not isinstance(blockers, list):
            raise ValueError("content review blockers must be a list")
        if blockers:
            raise ValueError("content review has blocking issues")
        body = checked.get("draft")
        if not isinstance(body, dict):
            raise ValueError("review result does not contain a draft")
        _reject_private_public_items(body)
        token = checked.get("plan_digest")
        if not isinstance(token, str) or not token:
            raise ValueError("content review token is required")
        return self.deps.commit_content({**body, "reviewed": True, "plan_digest": token})
