from __future__ import annotations

import hashlib
import json
from html.parser import HTMLParser
from typing import Any

from src.adventures.graph_v2 import MAX_NODES
from src.adventures.script_import import parse_script
from src.engine.language import normalize_language


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if not self.hidden and tag in {"p", "div", "br", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in {"p", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def prose(value: Any) -> str:
    parser = _Text()
    parser.feed(str(value or ""))
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())


def local_id(kind: str, external_id: str) -> str:
    return kind + "_" + hashlib.sha256(str(external_id).encode()).hexdigest()[:16]


class NativeDraft:
    def __init__(self, payload: bytes, filename: str, name: str, runtime: dict, language: str, format_name: str):
        digest = hashlib.sha256(payload).hexdigest()
        identity = f"import_{digest[:16]}"
        self.draft = parse_script(f"# {name}\n### Opening\n".encode(), "import.md", runtime, normalize_language(language))
        self.files = self.draft["files"]
        self.graph = self.files["adventure.json"]
        self.graph.update({"id": identity, "name": name, "source_ref": f"user:{identity}", "nodes": [], "start_node_ids": []})
        self.files["manifest.json"]["adventure_id"] = f"user:{identity}"
        self.files["manifest.json"]["reference_policy"] = "adventure-local"
        for value in self.files.values():
            if isinstance(value.get("target"), dict):
                value["target"]["id"] = identity
        self.draft.update({"directory_id": identity, "provenance": {"format": format_name, "filename": filename,
                           "source_digest": f"sha256:{digest}"}, "warnings": ["scriptDefaultGm", "scriptMechanicsReference", "externalImportReference"]})

    def scene(self, external_id: str, name: str, text: str, *, reference: bool = False) -> dict:
        if len(self.graph["nodes"]) >= MAX_NODES:
            raise ValueError("import contains too many scenes")
        identity = local_id("n", external_id)
        if any(node["id"] == identity for node in self.graph["nodes"]):
            raise ValueError("duplicate external scene identity")
        node = {"id": identity, "type": "reference" if reference else "scene", "name": name,
                "description": text, "chapter_id": self.graph["chapters"][0]["id"], "visibility": "gm",
                "optional": reference, "transitions": []}
        self.graph["nodes"].append(node)
        return node

    def resource(self, kind: str, external_id: str, name: str, text: str, original: Any) -> str:
        identity = local_id(kind, external_id)
        path = f"content/{kind}/{identity}.json"
        if path in self.files:
            raise ValueError("duplicate external resource identity")
        self.files[path] = {"schema_version": 1, "kind": kind, "id": identity, "name": name,
                            "source_ref": self.graph["source_ref"], "automation_level": "reference", "visibility": "gm",
                            "description": text, "source_record": json.dumps(original, ensure_ascii=False, sort_keys=True)}
        return f"{kind}:{identity}"

    def finish(self, name: str) -> dict:
        ordinary = [node for node in self.graph["nodes"] if not node["optional"]]
        if not ordinary:
            ordinary = [self.scene("opening", name, "")]
        self.graph["start_node_ids"] = [ordinary[0]["id"]]
        # Source documents do not define a DiceFrame causal graph. Keep other
        # sections optional references; the reviewer authors transitions.
        for node in ordinary[1:]:
            node["optional"] = True
        return self.draft
