"""Foundry Adventure JSON document adapter (public document export shape)."""
from __future__ import annotations

import json
import re

from src.adventures.importers.common import NativeDraft, prose


def parse_foundry(payload: bytes, filename: str, runtime: dict, language: str) -> dict:
    try:
        data = json.loads(payload.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Foundry Adventure must be UTF-8 JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("name"), str) or not any(key in data for key in ("journal", "actors", "scenes", "items")):
        raise ValueError("expected a Foundry Adventure document export, not a pack database or arbitrary JSON")
    builder = NativeDraft(payload, filename, data["name"], runtime, language, "foundry-adventure")
    collections = {}
    for kind in ("journal", "actors", "scenes", "items"):
        rows = data.get(kind, [])
        if not isinstance(rows, list) or len(rows) > 128 or not all(isinstance(row, dict) for row in rows):
            raise ValueError(f"Foundry {kind} must be a bounded document array")
        if any(not isinstance(row.get("_id"), str) or not row["_id"] for row in rows) or len({row["_id"] for row in rows}) != len(rows):
            raise ValueError(f"Foundry {kind} requires unique document identities")
        collections[kind] = rows
    actor_refs = {}
    for row in collections["actors"]:
        system = row.get("system") if isinstance(row.get("system"), dict) else {}
        details = system.get("details") if isinstance(system.get("details"), dict) else {}
        bio = details.get("biography") or {}
        actor_refs[row["_id"]] = builder.resource("npc", row["_id"], str(row.get("name") or row["_id"]), prose(bio.get("value") if isinstance(bio, dict) else bio), row)
    for row in collections["items"]:
        system = row.get("system") if isinstance(row.get("system"), dict) else {}
        description = system.get("description") or {}
        builder.resource("item", row["_id"], str(row.get("name") or row["_id"]), prose(description.get("value") if isinstance(description, dict) else description), row)
    for row in collections["journal"]:
        pages = row.get("pages", [])
        if not isinstance(pages, list) or len(pages) > 128 or not all(isinstance(page, dict) for page in pages):
            raise ValueError("Foundry journal pages must be a bounded array")
        content = []
        for page in pages:
            text = page.get("text") or {}
            if page.get("type") == "text" and isinstance(text, dict):
                content.append(str(text.get("content") or ""))
        if not pages and isinstance(row.get("content"), str):
            content.append(row["content"])  # Older journal document exports.
        html = "\n".join(content)
        node = builder.scene("journal:" + row["_id"], str(row.get("name") or row["_id"]), prose(html))
        node["npc_refs"] = list(dict.fromkeys(actor_refs[key] for key in re.findall(r'@UUID\[Actor\.([^\].]+)\]', html) if key in actor_refs))
    for row in collections["scenes"]:
        name = str(row.get("name") or row["_id"])
        builder.resource("map_location", row["_id"], name, name, row)
        builder.scene("scene:" + row["_id"], name, json.dumps(row, ensure_ascii=False, sort_keys=True), reference=True)
    if data.get("macros") or data.get("playlists"):
        builder.draft["warnings"].append("externalImportScriptsOmitted")
    if collections["scenes"] or data.get("img"):
        builder.draft["warnings"].append("externalImportMedia")
    return builder.finish(data["name"])
