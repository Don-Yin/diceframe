"""Editable prose review, delegated to content owners with durable per-item receipts.

Each owner commits one independent resource. A mixed batch is explicitly partial
on failure; receipts prevent replaying successful writes after reconnect/retry.
No adapter turns prose into mechanics or overwrites a resource by display name.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePath
from threading import RLock
from typing import Any

from src.content_modules.refs import ContentDraft, build_commit_plan, commit_plan_digest, parse_content_ref
from src.engine.language import normalize_language
from src.engine.world.contracts import canonical_id
from src.webui.services import adventure_script_import, adventures, character_cards, lorebooks, worlds

MAX_TEXT_BYTES = 512 * 1024
TARGETS = {"world", "lorebook", "character_template", "adventure"}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ContentReviewDependencies:
    worlds: worlds.WorldDependencies
    lorebooks: lorebooks.LorebookDependencies
    characters: character_cards.CharacterCardDependencies
    adventures: adventures.AdventureDependencies
    receipts_dir: Path


class ContentTextReview:
    def __init__(self, deps: ContentReviewDependencies):
        self.deps = deps
        self.lock = RLock()

    def preview(self, text: str, filename: str, language: str) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip() or len(text.encode()) > MAX_TEXT_BYTES:
            raise ValueError("text must be nonempty and at most 512 KiB")
        if PurePath(filename).suffix.lower() not in {".md", ".txt"}:
            raise ValueError("content text requires a Markdown or text file")
        sections: list[tuple[str, list[str]]] = []
        fence = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("```", "~~~")):
                fence = "" if fence == stripped[:3] else stripped[:3] if not fence else fence
            heading = re.fullmatch(r"#{1,3}\s+(.+)", stripped) if not fence else None
            if heading:
                sections.append((heading[1], []))
            else:
                if not sections:
                    sections.append((PurePath(filename).stem, []))
                sections[-1][1].append(line)
        items = [{"id": f"part_{index + 1}", "name": name, "text": "\n".join(lines).strip(),
                  "target": "lorebook", "references": []}
                 for index, (name, lines) in enumerate(sections) if "\n".join(lines).strip()]
        return self.review({"source_id": f"text-{_digest(text)[:24]}", "filename": PurePath(filename).name,
                            "language": normalize_language(language), "items": items})

    def clean(self, body: dict[str, Any]) -> dict[str, Any]:
        source = canonical_id(body.get("source_id"), field="text source")
        copy_id = body.get("copy_id", "")
        if not isinstance(copy_id, str) or (copy_id and not re.fullmatch(r"[a-f0-9]{32}", copy_id)):
            raise ValueError("invalid content copy identity")
        rows = body.get("items")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
            raise ValueError("content review requires 1–32 fragments")
        if len(json.dumps(body, ensure_ascii=False).encode()) > MAX_TEXT_BYTES * 4:
            raise ValueError("content draft is too large")
        items, seen = [], set()
        for raw in rows:
            if not isinstance(raw, dict):
                raise ValueError("fragment must be an object")
            key = canonical_id(raw.get("id"), field="fragment id")
            if key in seen:
                raise ValueError("duplicate fragment identity")
            seen.add(key)
            name, text, target = raw.get("name"), raw.get("text"), raw.get("target")
            if not isinstance(name, str) or not name.strip() or len(name) > 200:
                raise ValueError("fragment title is required (up to 200 characters)")
            if not isinstance(text, str) or not text.strip() or len(text.encode()) > MAX_TEXT_BYTES:
                raise ValueError("fragment text is required")
            if target not in TARGETS:
                raise ValueError("unsupported fragment target")
            refs = raw.get("references", [])
            if not isinstance(refs, list) or len(refs) > 256:
                raise ValueError("fragment references must be a bounded array")
            references = [parse_content_ref(ref, default_source=f"device:{source}").to_portable_dict() for ref in refs]
            items.append({"id": key, "name": name.strip(), "text": text.strip(), "target": target, "references": references})
        return {"source_id": source, "copy_id": copy_id, "filename": str(body.get("filename") or "notes.txt")[:200],
                "language": normalize_language(body.get("language")), "items": items}

    def prepare(self, draft: dict, item: dict) -> tuple[dict, list[str]]:
        deps, target = self.deps, item["target"]
        identity = f"review_{_digest([draft['source_id'], item['id'], draft['copy_id']])[:32]}"
        provenance = {"source_id": draft["source_id"], "filename": draft["filename"], "references": item["references"]}
        blockers = []
        if target == "world":
            identity = f"custom_book_{identity}"
            if deps.worlds.lorebook.get_world(identity) or (
                deps.worlds.worlds_dir and (deps.worlds.worlds_dir / f"{identity}.json").exists()
            ):
                blockers.append("world target already exists")
            prepared = {"world_id": identity, "name": item["name"], "description": item["text"], "language": draft["language"], "provenance": provenance}
        elif target == "lorebook":
            prepared = {"book_id": identity, "payload": {"spec": "lorebook_v3", "data": {"lorebook": {
                "name": item["name"], "language": draft["language"], "entries": [{"id": "text", "name": item["name"],
                "content": item["text"], "keys": [], "extensions": {"import_source": provenance}}],
            }}}}
            if deps.lorebooks.lorebook.get_lorebook(identity):
                blockers.append("lorebook target already exists")
            checked = lorebooks.preview_lorebook_import(deps.lorebooks, prepared["payload"])
            if checked["commit_plan"]["unresolved_references"]:
                blockers.append("unresolved lorebook references")
        elif target == "character_template":
            checked = character_cards.preview_character_card_create(deps.characters, {
                "id": identity, "character_name": item["name"], "background": item["text"],
                "source": f"Text: {draft['filename']}", "language": draft["language"],
                "identity": {"import_source": provenance},
            })
            prepared = checked["card"]
            if checked["conflicts"]:
                blockers.append("character target already exists")
        else:
            checked = adventure_script_import.prepare_text_adventure(deps.adventures, f"# {item['name']}\n{item['text']}", identity, draft["language"])
            prepared = checked["draft"]
            prepared["provenance"]["text_fragment"] = provenance
            blockers.extend(checked["blockers"])
        return {"identity": identity, "payload": prepared}, blockers

    def review(self, body: dict[str, Any]) -> dict[str, Any]:
        draft = self.clean(body)
        contents, blockers, signatures, existing = [], [], set(), []
        for item in draft["items"]:
            prepared, problems = self.prepare(draft, item)
            if item["target"] == "character_template":
                signature = character_cards.card_signature(prepared["payload"])
                if signature in signatures:
                    problems.append("duplicate character in this batch")
                signatures.add(signature)
            blockers.extend(f"{item['id']}: {problem}" for problem in problems)
            references = list(item["references"])
            if item["target"] == "adventure":
                references.extend(prepared["payload"].get("references", []))
            contents.append(ContentDraft(kind=item["target"], source_kind="user", source_id=prepared["identity"],
                external_id=prepared["identity"], payload={"fragment": item, "prepared": prepared, "source": draft["source_id"],
                "filename": draft["filename"], "language": draft["language"]},
                references=tuple(dict.fromkeys(parse_content_ref(ref, default_source=f"device:{draft['source_id']}") for ref in references)),
                provenance={"adapter": "text_fragments", "filename": draft["filename"]}))
            if any("already exists" in problem for problem in problems):
                existing.append(contents[-1].ref)
        plan = build_commit_plan(contents, existing=existing)
        if plan.unresolved_references:
            blockers.append("unresolved content references")
        return {"ok": True, "draft": draft, "commit_plan": plan.to_portable_dict(), "plan_digest": commit_plan_digest(plan),
                "blockers": blockers}

    def commit_one(self, item: dict, prepared: dict) -> dict:
        payload, deps = prepared["payload"], self.deps
        if item["target"] == "world":
            return worlds.create_imported_world(deps.worlds, **payload)
        if item["target"] == "lorebook":
            return lorebooks.create_reviewed_lorebook(deps.lorebooks, payload["payload"], payload["book_id"])
        if item["target"] == "character_template":
            return character_cards.create_character_card(deps.characters, payload)
        checked = adventure_script_import.review(deps.adventures, payload)
        return adventure_script_import.commit(deps.adventures, {**payload, "reviewed": True, "plan_digest": checked["plan_digest"]})

    def write_receipt(self, path: Path, receipt: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def commit(self, body: dict[str, Any]) -> dict[str, Any]:
        if body.get("reviewed") is not True:
            raise ValueError("content must be reviewed before saving")
        draft = self.clean(body)
        token = str(body.get("plan_digest") or "")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", token):
            raise ValueError("content review token is stale")
        path = self.deps.receipts_dir / f"{token[7:]}.json"
        with self.lock:
            receipt = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            if receipt is not None:
                if not isinstance(receipt, dict) or receipt.get("schema") != 1 or not isinstance(receipt.get("completed"), dict):
                    raise ValueError("unsupported content import receipt")
                if receipt.get("draft_digest") != _digest(draft):
                    raise ValueError("content review token is stale")
                if receipt.get("ok"):
                    return receipt["response"]
            else:
                checked = self.review(draft)
                if checked["blockers"]:
                    raise ValueError("content draft has blocking issues")
                if checked["plan_digest"] != token:
                    raise ValueError("content review token is stale")
                receipt = {"schema": 1, "draft_digest": _digest(draft), "completed": {}, "ok": False}
                # Prove the receipt directory is writable before any owner write.
                self.write_receipt(path, receipt)
            results = []
            for item in draft["items"]:
                if item["id"] in receipt["completed"]:
                    results.append(receipt["completed"][item["id"]])
                    continue
                try:
                    prepared, blockers = self.prepare(draft, item)
                    if blockers:
                        raise ValueError("; ".join(blockers))
                    result = self.commit_one(item, prepared)
                    if not result.get("ok"):
                        raise ValueError(str(result.get("error") or "content save failed"))
                    row = {"id": item["id"], "target": item["target"], "ok": True, "result": result}
                    results.append(row)
                    receipt["completed"][item["id"]] = row
                    self.write_receipt(path, receipt)
                except (ValueError, OSError) as exc:
                    if results and results[-1]["id"] == item["id"] and results[-1]["ok"]:
                        return {"ok": False, "partial": True, "recovery_required": True, "results": results,
                                "error": "Resource saved but its receipt could not be persisted; inspect the saved library before retrying"}
                    results.append({"id": item["id"], "target": item["target"], "ok": False, "error": str(exc)})
                    return {"ok": False, "partial": bool(receipt["completed"]), "results": results}
            response = {"ok": True, "partial": False, "results": results}
            receipt.update({"ok": True, "response": deepcopy(response)})
            try:
                self.write_receipt(path, receipt)
            except OSError:
                return {"ok": False, "partial": True, "recovery_required": True, "results": results,
                        "error": "Content saved; completion receipt could not be persisted"}
            return response
