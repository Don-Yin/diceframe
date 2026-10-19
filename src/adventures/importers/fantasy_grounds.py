"""FG XML / .mod data archive; no scripts, entities or external file reads."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from src.adventures.importers.common import NativeDraft

MAX_EXPANDED_BYTES = 10 * 1024 * 1024


def xml_root(payload: bytes):
    try:
        text = payload.decode("utf-8-sig")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise ValueError("Fantasy Grounds XML declarations/entities are not accepted")
        root = ET.fromstring(text)
    except (UnicodeDecodeError, ET.ParseError) as exc:
        raise ValueError("Fantasy Grounds data must be valid UTF-8 XML") from exc
    if root.tag != "root":
        raise ValueError("Fantasy Grounds XML must have a root element")
    pending = [(root, 0)]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if depth > 32 or count > 16000:
            raise ValueError("Fantasy Grounds XML tree is too large or deep")
        pending.extend((child, depth + 1) for child in node)
    return root


def _text(element):
    return "\n".join(text.strip() for text in element.itertext() if text.strip()) if element is not None else ""


def _records(root, prefix=""):
    for node in root:
        path = f"{prefix}.{node.tag}" if prefix else node.tag
        if node.find("name") is not None:
            yield path, node
        else:
            yield from _records(node, path)


def parse_fantasy_grounds(payload: bytes, filename: str, runtime: dict, language: str) -> dict:
    name = PurePosixPath(filename).stem
    sources = {"db.xml": payload}
    media = False
    if filename.lower().endswith(".mod"):
        try:
            archive = zipfile.ZipFile(io.BytesIO(payload))
        except zipfile.BadZipFile as exc:
            raise ValueError("Fantasy Grounds .mod must be an unencrypted ZIP") from exc
        sources = {}
        total = 0
        with archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) > 256:
                raise ValueError("Fantasy Grounds module has too many files")
            seen = set()
            for member in members:
                path = PurePosixPath(member.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts or ":" in str(path) or str(path) in seen or member.flag_bits & 1:
                    raise ValueError("unsafe or encrypted Fantasy Grounds archive entry")
                seen.add(str(path)); total += member.file_size
                if total > MAX_EXPANDED_BYTES:
                    raise ValueError("Fantasy Grounds module expands beyond the size limit")
                if path.as_posix() in {"definition.xml", "db.xml", "client.xml"}:
                    sources[path.as_posix()] = archive.read(member)
                elif path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    media = True
            if "definition.xml" not in sources or not any(key in sources for key in ("db.xml", "client.xml")):
                raise ValueError("Fantasy Grounds .mod requires definition.xml and db.xml/client.xml")
            definition = xml_root(sources.pop("definition.xml"))
            name = _text(definition.find("displayname")) or _text(definition.find("name")) or name
    builder = NativeDraft(payload, filename, name, runtime, language, "fantasy-grounds")
    imported = 0
    for source_name, raw in sources.items():
        root = xml_root(raw)
        datasets = [(root.find(path), kind) for path, kind in (
            ("encounter", "story"), ("reference/encounters", "story"), ("npc", "npc"), ("reference/npcs", "npc"),
            ("item", "item"), ("reference/items", "item"), ("image", "map_location"), ("reference/images", "map_location"),
            ("battle", "encounter_reference"), ("reference/battles", "encounter_reference"),
        )]
        for container, kind in datasets:
            if container is None:
                continue
            for path, record in _records(container):
                imported += 1
                if imported > 128:
                    raise ValueError("Fantasy Grounds contains too many records")
                record_name = _text(record.find("name"))
                text = _text(record.find("text")) or _text(record.find("description"))
                external_id = f"{source_name}:{kind}:{path}"
                original = ET.tostring(record, encoding="unicode")
                if kind == "story":
                    builder.scene(external_id, record_name, text)
                elif kind == "encounter_reference":
                    builder.scene(external_id, record_name, original, reference=True)
                else:
                    builder.resource(kind, external_id, record_name, text, original)
    if not imported:
        raise ValueError("Fantasy Grounds contains no supported story/resource records")
    if media:
        builder.draft["warnings"].append("externalImportMedia")
    builder.draft["provenance"]["source_files"] = sorted(sources)
    # The original XML is a string in source_record, never an executable model.
    json.dumps(builder.draft)
    return builder.finish(name)
