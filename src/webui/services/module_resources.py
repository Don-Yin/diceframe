"""Installed module resource inventory and exact-source read snapshots.

Uses a temporary contribution registry to inspect disabled packages without
enabling their runtime, changing the global registry or importing any content.
"""
from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.adventures.bundle import AdventureBundleLoader
from src.plugin_host.content import PluginContentCatalog
from src.plugin_host.registry import ContributionRegistry
from src.rulesets.module_catalogs import load_declared_module_catalog
from src.webui.services import adventures, lorebooks, modules
from src.webui.services.module_validation import parse_requires


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ModuleResourceDependencies:
    modules: modules.ModuleDependencies
    lorebooks: lorebooks.LorebookDependencies


class ModuleResources:
    def __init__(self, deps: ModuleResourceDependencies):
        self.deps = deps

    def runtime(self, module_id: str):
        host = self.deps.modules.plugin_host
        runtime = getattr(host, "plugins", {}).get(str(module_id))
        if runtime is None or runtime.manifest.get("plugin_type") != "content-pack":
            raise ValueError("installed content module not found")
        return runtime

    def catalog(self, module_id: str) -> PluginContentCatalog:
        runtime = self.runtime(module_id)
        registry = ContributionRegistry()
        registry.register_static_plugin(runtime.manifest, runtime.directory)
        return PluginContentCatalog(registry, logging.getLogger("trpg"))

    def adventure_loader(self, module_id: str) -> AdventureBundleLoader | None:
        runtime = self.runtime(module_id)
        if runtime.adventure_packages_root is None:
            return None
        return AdventureBundleLoader(runtime.adventure_packages_root, allowed_directory_ids=runtime.adventure_package_directories)

    def catalogs(self, module_id: str):
        runtime = self.runtime(module_id)
        requirements = parse_requires(runtime.manifest)
        declared_default = self.deps.modules.default_runtime_requirement
        runtime_id = requirements[0]["id"] if requirements else str((declared_default() if declared_default else {}).get("id") or "")
        root = runtime.ruleset_catalogs_root
        if root is not None:
            for directory in runtime.ruleset_catalog_directories:
                loaded = load_declared_module_catalog(runtime_id, root / directory, source_label=f"module:{module_id}")
                records = getattr(loaded, "records", None)
                if not isinstance(records, dict):
                    raise ValueError("runtime catalog does not expose readable records")
                yield directory, records

    def list(self, module_id: str) -> dict[str, Any]:
        catalog = self.catalog(module_id)
        resources = [{"kind": item.kind, "title": item.title or item.key, "description": item.description,
                      "selector": {"origin": "contribution", "kind": item.kind, "key": item.key}}
                     for item in catalog.registry.list()]
        loader = self.adventure_loader(module_id)
        if loader is not None:
            for bundle in loader.list(""):
                graph = bundle.adventure
                tutorial = graph.get("tutorial") or {}
                resources.append({"kind": "adventure", "title": tutorial.get("name") or graph.get("name") or bundle.manifest.adventure_id,
                                  "description": tutorial.get("summary") or graph.get("summary") or "",
                                  "selector": {"origin": "adventure", "key": bundle.root.name}})
        for directory, records in self.catalogs(module_id):
            for (kind, key), record in records.items():
                resources.append({"kind": kind, "title": str(record.get("name") or key), "description": str(record.get("description") or ""),
                                  "selector": {"origin": "catalog", "directory": directory, "kind": kind, "key": key}})
        for book in self.deps.lorebooks.lorebook.list_lorebooks():
            if book.get("source_kind") == "module" and book.get("source_id") == module_id:
                resources.append({"kind": "lorebook", "title": str(book.get("name") or book["id"]), "description": str(book.get("description") or ""),
                                  "selector": {"origin": "book", "key": book["id"]}})
        return {"ok": True, "module_id": module_id, "resources": resources}

    def asset_path(self, module_id: str, selector: dict) -> Path:
        catalog = self.catalog(module_id)
        item = next((item for item in catalog.registry.list() if selector == {"origin": "contribution", "kind": item.kind, "key": item.key}), None)
        if item is None or item.path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("declared image resource not found")
        if item.path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("module image resource is too large")
        return catalog.public_asset_path(module_id, item.relative_path, self.runtime(module_id).directory)

    def package_digest(self, module_id: str) -> str:
        """Fence all declared content dependencies while excluding runtime config/secrets."""
        runtime = self.runtime(module_id)
        rows = []
        for item in self.catalog(module_id).registry.list():
            if item.path.is_symlink() or not item.path.resolve().is_relative_to(runtime.directory.resolve()):
                raise ValueError("unsafe module contribution path")
            if item.path.stat().st_size > 20 * 1024 * 1024:
                raise ValueError("module contribution is too large")
            rows.append([item.kind, item.key, hashlib.sha256(item.path.read_bytes()).hexdigest()])
        loader = self.adventure_loader(module_id)
        if loader is not None:
            rows.extend(["adventure", bundle.root.name, bundle.content_digest] for bundle in loader.list(""))
        for directory, records in self.catalogs(module_id):
            rows.extend([directory, kind, key, digest(record)] for (kind, key), record in records.items())
        for book in self.deps.lorebooks.lorebook.list_lorebooks():
            if book.get("source_kind") == "module" and book.get("source_id") == module_id:
                rows.append(["book", book["id"], digest(lorebooks.export_lorebook(self.deps.lorebooks, book["id"]))])
        return digest({"manifest": dict(runtime.manifest), "content": sorted(rows, key=lambda row: json.dumps(row))})

    def read(self, module_id: str, selector: dict, language: str = "") -> dict[str, Any]:
        if not isinstance(selector, dict) or len(json.dumps(selector).encode()) > 2048:
            raise ValueError("invalid module resource selector")
        metadata = next((row for row in self.list(module_id)["resources"] if row["selector"] == selector), None)
        if metadata is None:
            raise ValueError("module resource not found")
        origin, kind = selector["origin"], metadata["kind"]
        if origin == "contribution":
            if kind in {"portrait_asset", "scene_image_asset", "map_icon", "map_scene"}:
                path = self.asset_path(module_id, selector)
                payload = {"file_name": path.name, "bytes": path.stat().st_size}
                source_digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
                target = "portrait" if kind == "portrait_asset" else "scene_image" if kind == "scene_image_asset" else ""
            else:
                payload = self.catalog(module_id).read_declared_resource(kind, selector["key"], plugin_id=module_id, language=language)
                source_digest = digest(payload)
                target = {"world_template": "world", "world": "world", "lorebook": "lorebook", "character_template": "character_template",
                          "npc": "lorebook", "item": "lorebook", "spell": "lorebook", "class": "lorebook"}.get(kind, "")
        elif origin == "adventure":
            loader = self.adventure_loader(module_id)
            if loader is None:
                raise ValueError("module adventure source unavailable")
            bundle = loader.load(selector["key"], language)
            payload = {"directory_id": bundle.root.name, "files": adventures.adventure_bundle_files(bundle)}
            source_digest, target = bundle.content_digest, "adventure"
        elif origin == "catalog":
            records = next((records for directory, records in self.catalogs(module_id) if directory == selector["directory"]), None)
            if records is None or (kind, selector["key"]) not in records:
                raise ValueError("module catalog resource not found")
            payload = deepcopy(records[(kind, selector["key"])])
            source_digest, target = digest(payload), ""
        else:
            exported = lorebooks.export_lorebook(self.deps.lorebooks, selector["key"])
            if not exported.get("ok"):
                raise ValueError("module book source unavailable")
            payload = exported
            source_digest, target = digest(payload), "lorebook"
        return {"ok": True, "resource": {**metadata, "module_id": module_id, "payload": payload,
                                          "source_digest": source_digest, "fork_target": target, "readonly": True}}
