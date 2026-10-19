"""Review/edit/fork declared module resources into user content owners."""
from __future__ import annotations

import base64
import json
import re
import uuid
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from src.content.contracts import ResourceRef
from src.content_modules.refs import ContentDraft, build_commit_plan, collect_content_refs, commit_plan_digest
from src.engine.language import localized_text, normalize_language
from src.lorebook.adapters.module_resource import module_book_review_payload
from src.webui.services import adventures, character_cards, lorebooks, worlds
from src.webui.services.module_resources import ModuleResources


def copy_name(target: str, payload: dict, fallback: str) -> str:
    nested = payload
    key = "name"
    if target == "world":
        nested, key = payload.get("definition"), "world_name"
    elif target == "character_template":
        key = "character_name"
    elif target == "lorebook":
        data = payload.get("data")
        nested = data.get("lorebook") if isinstance(data, dict) else None
    elif target == "adventure":
        files = payload.get("files")
        nested = files.get("adventure.json") if isinstance(files, dict) else None
        if isinstance(nested, dict) and isinstance(nested.get("tutorial"), dict):
            nested = nested["tutorial"]
    return str(nested.get(key) or fallback) if isinstance(nested, dict) else fallback


@dataclass(frozen=True)
class ModuleForkDependencies:
    resources: ModuleResources
    worlds: worlds.WorldDependencies
    lorebooks: lorebooks.LorebookDependencies
    characters: character_cards.CharacterCardDependencies
    adventures: adventures.AdventureDependencies
    save_portrait: Callable[[str, str], dict[str, Any]]
    save_scene_image: Callable[[str, str], dict[str, Any]]
    preview_portrait: Callable[[str, str], dict[str, Any]]
    preview_scene_image: Callable[[str, str], dict[str, Any]]


class ModuleForks:
    def __init__(self, deps: ModuleForkDependencies):
        self.deps = deps

    def preview(self, module_id: str, selector: dict, language: str = "") -> dict[str, Any]:
        resource = self.deps.resources.read(module_id, selector, language)["resource"]
        target = resource["fork_target"]
        if not target:
            raise ValueError("this resource has no user content owner for cloning")
        payload = deepcopy(resource["payload"])
        name = str(payload.get("world_name") or payload.get("character_name") or payload.get("name") or resource["title"])
        suffix = localized_text(normalize_language(language), {"zh-CN": "（副本）", "en": " (Copy)", "ja": "（コピー）", "de": " (Kopie)", "ru": " (Копия)"})
        if target == "world":
            payload.setdefault("language", normalize_language(payload.get("default_locale") or language))
            if int(payload.get("world_schema_version", 1)) == 3:
                ref = str(payload.get("primary_lorebook_ref") or "")
                if ref.startswith("lorebook:") and ref.count(":") == 1:
                    book_id = ref[len("lorebook:"):]
                else:
                    parsed = ResourceRef.parse(ref)
                    if parsed.owner not in {f"plugin:{module_id}", f"module:{module_id}"} or parsed.kind != "lorebook":
                        raise ValueError("world primary Book must be declared in this module")
                    book_id = parsed.local_id
                book = self.deps.resources.catalog(module_id).read_declared_resource("lorebook", book_id, plugin_id=module_id, language=language)
            else:
                book = {"name": f"{name}{suffix}", "entries": deepcopy(payload.get("starter_lorebook", []))}
            book = module_book_review_payload(book, payload["language"])
            payload["world_name"] = name + suffix
            payload = {"definition": payload, "book": book}
        elif target == "character_template":
            payload["character_name"] = name + suffix
            payload.setdefault("background", str(payload.get("description") or ""))
        elif target == "lorebook":
            if resource["kind"] in {"npc", "item", "spell", "class"}:
                payload = {"spec": "lorebook_v3", "data": {"lorebook": {"name": name + suffix, "language": normalize_language(language),
                    "entries": [{"id": "resource", "name": name, "content": str(payload.get("description") or payload.get("summary") or ""),
                    "keys": [name], "extensions": {"imported_resource": payload, "diceframe": {"type": resource["kind"]}}}]}}}
            else:
                payload = module_book_review_payload(payload, language)
                book = payload.get("data", {}).get("lorebook")
                if not isinstance(book, dict):
                    raise ValueError("native Book payload is invalid")
                book["name"] = str(book.get("name") or name) + suffix
        elif target == "adventure":
            graph = payload["files"]["adventure.json"]
            if isinstance(graph.get("tutorial"), dict):
                graph["tutorial"]["name"] = str(graph["tutorial"].get("name") or name) + suffix
            else:
                graph["name"] = str(graph.get("name") or name) + suffix
        return self.review(module_id, {"selector": selector, "source_digest": resource["source_digest"],
                                       "package_digest": self.deps.resources.package_digest(module_id), "copy_id": uuid.uuid4().hex,
                                       "language": normalize_language(language), "payload": payload})

    def clean(self, body: dict) -> dict:
        if len(json.dumps(body, ensure_ascii=False).encode()) > 5 * 1024 * 1024:
            raise ValueError("module fork draft is too large")
        identity = body.get("copy_id")
        if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{32}", identity):
            raise ValueError("invalid module copy identity")
        if not isinstance(body.get("payload"), dict):
            raise ValueError("module fork payload must be an object")
        return {"selector": deepcopy(body.get("selector")), "source_digest": str(body.get("source_digest") or ""),
                "package_digest": str(body.get("package_digest") or ""),
                "copy_id": identity, "language": normalize_language(body.get("language")), "payload": deepcopy(body["payload"])}

    def source(self, module_id: str, draft: dict) -> dict:
        resource = self.deps.resources.read(module_id, draft["selector"], draft["language"])["resource"]
        if resource["source_digest"] != draft["source_digest"]:
            raise ValueError("module source changed; review a fresh copy")
        if self.deps.resources.package_digest(module_id) != draft["package_digest"]:
            raise ValueError("module dependencies changed; review a fresh copy")
        if not resource["fork_target"]:
            raise ValueError("module resource cannot be cloned")
        return resource

    def prepared_asset(self, module_id: str, selector: dict, target: str) -> dict:
        import hashlib
        path = self.deps.resources.asset_path(module_id, selector)
        raw = path.read_bytes()
        data = base64.b64encode(raw).decode()
        preview = self.deps.preview_portrait if target == "portrait" else self.deps.preview_scene_image
        result = preview(data, path.name)
        if not result.get("ok"):
            raise ValueError(str(result.get("error") or "invalid module image"))
        return {"selector": selector, "target": target, "source_digest": "sha256:" + hashlib.sha256(raw).hexdigest(), "result": result}

    def image_reference(self, module_id: str, reference: Any, target: str) -> dict | None:
        if not isinstance(reference, dict) or reference.get("kind") not in {"asset", "plugin"}:
            return None
        if reference.get("kind") == "plugin" and reference.get("plugin_id") != module_id:
            raise ValueError("copy requires an image declared in its source module")
        relative = str(reference.get("path") or "")
        expected = "portrait_asset" if target == "portrait" else "scene_image_asset"
        item = next((row for row in self.deps.resources.catalog(module_id).registry.list(expected) if row.relative_path == relative), None)
        if item is None:
            raise ValueError("referenced module image is not declared")
        return self.prepared_asset(module_id, {"origin": "contribution", "kind": item.kind, "key": item.key}, target)

    def reviewed_payload(self, module_id: str, draft: dict, resource: dict) -> tuple[dict, list[str]]:
        payload, target = deepcopy(draft["payload"]), resource["fork_target"]
        identity = f"fork_{draft['copy_id']}"
        provenance = {"module_id": module_id, "selector": draft["selector"], "source_digest": draft["source_digest"]}
        blockers, assets = [], []
        if target == "world":
            identity = f"custom_book_{identity}"
            if not isinstance(payload.get("definition"), dict):
                raise ValueError("world definition must be an object")
            payload["definition"]["import_source"] = provenance
            asset = self.image_reference(module_id, payload["definition"].get("scene_image"), "scene_image")
            if asset:
                assets.append(asset)
                payload["definition"]["scene_image"] = asset["result"]["scene_image"]
            worlds.review_world_fork(self.deps.worlds, payload, identity)
        elif target == "character_template":
            for key in ("id", "card_id", "source_plugin", "plugin_content_id", "plugin_id", "plugin_name", "readonly", "ref"):
                payload.pop(key, None)
            payload.update({"id": identity, "source": f"Module copy: {module_id}"})
            metadata = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
            payload["identity"] = {**metadata, "import_source": provenance}
            asset = self.image_reference(module_id, payload.get("portrait"), "portrait")
            if asset:
                assets.append(asset)
                payload["portrait"] = asset["result"]["portrait"]
            checked = character_cards.preview_character_card_create(self.deps.characters, payload)
            payload = checked["card"]
            if checked["conflicts"]:
                blockers.append("character target already exists; edit the blueprint name or background")
        elif target == "lorebook":
            data = payload.get("data")
            book = data.get("lorebook") if isinstance(data, dict) else None
            if not isinstance(book, dict):
                raise ValueError("native Book payload is invalid")
            extensions = book.get("extensions")
            if extensions is not None and not isinstance(extensions, dict):
                raise ValueError("Book extensions must be an object")
            book["extensions"] = {**(extensions or {}), "import_source": provenance}
            checked = lorebooks.preview_lorebook_import(self.deps.lorebooks, payload)
            if checked["commit_plan"]["unresolved_references"]:
                blockers.append("unresolved Book references")
            if self.deps.lorebooks.lorebook.get_lorebook(identity):
                blockers.append("Book target already exists")
        elif target == "adventure":
            if not isinstance(payload.get("files"), dict) or not isinstance(payload["files"].get("manifest.json"), dict):
                raise ValueError("native adventure files are required")
            payload["files"]["manifest.json"]["import_source"] = provenance
            source = self.deps.resources.adventure_loader(module_id).load(draft["selector"]["key"], draft["language"])
            payload = adventures.review_native_adventure_fork(self.deps.adventures, payload, identity, source)
        else:
            assets.append(self.prepared_asset(module_id, draft["selector"], target))
        return {"identity": identity, "payload": payload, "assets": assets}, blockers

    def review(self, module_id: str, body: dict) -> dict:
        draft = self.clean(body)
        resource = self.source(module_id, draft)
        try:
            prepared, blockers = self.reviewed_payload(module_id, draft, resource)
        except (ValueError, TypeError, KeyError) as exc:
            prepared, blockers = {"identity": f"fork_{draft['copy_id']}", "payload": draft["payload"]}, [str(exc)]
        target = resource["fork_target"]
        kind = {"portrait": "portrait_asset", "scene_image": "scene_image_asset"}.get(target, target)
        payload = prepared["payload"]
        name = copy_name(target, payload, resource["title"])
        content = ContentDraft(kind=kind, source_kind="user", source_id=prepared["identity"], external_id=prepared["identity"],
            payload={"name": name, "draft": draft, "prepared": prepared},
            references=collect_content_refs(prepared["payload"], default_source=f"module:{module_id}"),
            provenance={"module_id": module_id, "source_digest": resource["source_digest"]})
        plan = build_commit_plan([content])
        if plan.unresolved_references:
            blockers.append("unresolved content references")
        return {"ok": True, "draft": draft, "commit_plan": plan.to_portable_dict(), "plan_digest": commit_plan_digest(plan),
                "target": target, "blockers": blockers}

    def commit(self, module_id: str, body: dict) -> dict:
        if body.get("reviewed") is not True:
            raise ValueError("module copy must be reviewed")
        checked = self.review(module_id, body)
        if checked["blockers"]:
            raise ValueError("module copy has blocking issues")
        if checked["plan_digest"] != str(body.get("plan_digest") or ""):
            raise ValueError("module copy review is stale")
        draft = checked["draft"]
        resource = self.source(module_id, draft)
        prepared, blockers = self.reviewed_payload(module_id, draft, resource)
        if blockers:
            raise ValueError("module copy has blocking issues")
        target, payload, identity = checked["target"], prepared["payload"], prepared["identity"]
        asset_result = None
        for asset in prepared["assets"]:
            path = self.deps.resources.asset_path(module_id, asset["selector"])
            writer = self.deps.save_portrait if asset["target"] == "portrait" else self.deps.save_scene_image
            asset_result = writer(base64.b64encode(path.read_bytes()).decode(), path.name)
            if asset_result != asset["result"]:
                raise ValueError("module image changed during copy")
        if target == "world":
            result = worlds.create_world_fork(self.deps.worlds, payload, identity)
        elif target == "character_template":
            result = character_cards.create_character_card(self.deps.characters, payload)
        elif target == "lorebook":
            result = lorebooks.create_reviewed_lorebook(self.deps.lorebooks, payload, identity)
        elif target == "adventure":
            source = self.deps.resources.adventure_loader(module_id).load(draft["selector"]["key"], draft["language"])
            result = adventures.create_native_adventure_fork(self.deps.adventures, payload, identity, source)
        else:
            result = asset_result
        if not result.get("ok"):
            raise ValueError(str(result.get("error") or "module copy save failed"))
        return {"ok": True, "target": target, "result": result}
