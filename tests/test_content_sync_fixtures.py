"""Published content-sync fixtures and schemas cannot drift from the server.

``docs/content-sync/fixtures`` holds golden portable documents that clients
copy as their own samples; ``docs/content-sync/schemas`` holds the minimal
JSON Schemas. This module checks that:

- every fixture satisfies its schema;
- the server imports every fixture as documented (free-form and CoC create,
  D&D is unsupported, a card's book is a second item, a lorebook creates);
- what the server exports satisfies the same schemas and imports back as
  ``unchanged``.

The schema check is a small subset validator (type, const, required,
properties, items, $ref, minLength, maxItems) so the server does not need a
JSON Schema dependency. Any other validation keyword fails the test: a
published schema must never promise a rule this check (and the server)
silently ignores.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from tests.test_content_sync_api import OWNER, PHONE, _post, sync_app  # noqa: F401 - fixture

pytest_plugins = ["tests.webapi_harness"]

ROOT = Path(__file__).resolve().parents[1] / "docs" / "content-sync"
FIXTURES = ROOT / "fixtures"
SCHEMAS = ROOT / "schemas"

_TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "integer": int, "number": (int, float),
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(ref: str, schema_file: Path) -> tuple[dict, Path]:
    target, _, pointer = ref.partition("#")
    path = (schema_file.parent / target) if target else schema_file
    node: Any = _load(path)
    for part in [p for p in pointer.split("/") if p]:
        node = node[part]
    return node, path


_VALIDATION_KEYWORDS = frozenset({
    "type", "const", "required", "properties", "items", "$ref", "minLength", "maxItems",
})
_ANNOTATION_KEYWORDS = frozenset({"$schema", "$id", "$defs", "title", "description"})


def _validate(value: Any, schema: dict, schema_file: Path, where: str = "$") -> list[str]:
    unknown = set(schema) - _VALIDATION_KEYWORDS - _ANNOTATION_KEYWORDS
    if unknown:
        raise AssertionError(f"{schema_file.name} {where}: unsupported schema keyword(s) {sorted(unknown)}")
    if "$ref" in schema:
        resolved, path = _resolve(schema["$ref"], schema_file)
        return _validate(value, resolved, path, where)
    errors: list[str] = []
    expected = schema.get("type")
    if expected:
        python_type = _TYPES[expected]
        if not isinstance(value, python_type) or (expected in {"integer", "number"} and isinstance(value, bool)):
            return [f"{where}: expected {expected}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{where}: expected {schema['const']!r}")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(f"{where}: too short")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{where}: missing {key}")
        for key, child in schema.get("properties", {}).items():
            if key in value:
                errors.extend(_validate(value[key], child, schema_file, f"{where}.{key}"))
    if isinstance(value, list):
        if len(value) > schema.get("maxItems", len(value)):
            errors.append(f"{where}: too many items")
        if "items" in schema:
            for index, child in enumerate(value):
                errors.extend(_validate(child, schema["items"], schema_file, f"{where}[{index}]"))
    return errors


def _check(document: Any, schema_name: str) -> None:
    schema_file = SCHEMAS / schema_name
    assert _validate(document, _load(schema_file), schema_file) == []


CARD_FIXTURES = sorted(FIXTURES.glob("card-*.chara_card_v3.json"))


def test_the_published_fixture_set_is_complete() -> None:
    names = {path.name for path in FIXTURES.iterdir()}
    assert {
        "card-freeform.chara_card_v3.json", "card-coc.chara_card_v3.json",
        "card-dnd2024.chara_card_v3.json", "card-with-book.chara_card_v3.json",
        "lorebook.lorebook_v3.json",
    } <= names


@pytest.mark.parametrize("path", CARD_FIXTURES, ids=lambda p: p.name)
def test_card_fixtures_satisfy_the_schemas(path: Path) -> None:
    document = _load(path)
    _check(document, "chara-card-v3.schema.json")
    _check(document["data"]["extensions"]["diceframe"], "card-body.schema.json")


def test_lorebook_fixture_satisfies_the_schema() -> None:
    _check(_load(FIXTURES / "lorebook.lorebook_v3.json"), "lorebook-v3.schema.json")


def test_the_validator_rejects_a_broken_document() -> None:
    broken = _load(FIXTURES / "lorebook.lorebook_v3.json")
    del broken["data"]["lorebook"]["entries"][0]["id"]
    schema_file = SCHEMAS / "lorebook-v3.schema.json"
    assert _validate(broken, _load(schema_file), schema_file) == ["$.data.lorebook.entries[0]: missing id"]


def test_the_validator_refuses_keywords_it_does_not_enforce() -> None:
    with pytest.raises(AssertionError, match="maxLength"):
        _validate("text", {"type": "string", "maxLength": 3}, SCHEMAS / "card-body.schema.json")


def _item(client_ref: str, path: Path) -> dict:
    kind = "lorebook" if path.name.startswith("lorebook") else "character_template"
    return {"client_ref": client_ref, "kind": kind, "document": _load(path)}


@pytest.mark.asyncio
async def test_the_server_imports_the_fixtures_as_documented(sync_app) -> None:  # noqa: F811
    app, *_ = sync_app
    items = [
        _item("freeform", FIXTURES / "card-freeform.chara_card_v3.json"),
        _item("coc", FIXTURES / "card-coc.chara_card_v3.json"),
        _item("dnd", FIXTURES / "card-dnd2024.chara_card_v3.json"),
        _item("with-book", FIXTURES / "card-with-book.chara_card_v3.json"),
        _item("atlas", FIXTURES / "lorebook.lorebook_v3.json"),
    ]
    async with TestClient(TestServer(app)) as client:
        status, preview = await _post(client, "/api/content/import/preview", {"source": PHONE, "items": items})

    assert status == 200, preview
    actions = {row["client_ref"]: (row["action"], row["reason"]) for row in preview["items"]}
    assert actions == {
        "freeform": ("create", ""), "coc": ("create", ""),
        "dnd": ("unsupported", "RULESET_CARD_UNSUPPORTED"),
        "with-book": ("create", ""), "with-book.book": ("create", ""),
        "atlas": ("create", ""),
    }
    assert all("warnings" not in row for row in preview["items"])


@pytest.mark.asyncio
async def test_server_exports_satisfy_the_schemas_and_round_trip(sync_app) -> None:  # noqa: F811
    app, *_ = sync_app
    items = [
        _item("freeform", FIXTURES / "card-freeform.chara_card_v3.json"),
        _item("coc", FIXTURES / "card-coc.chara_card_v3.json"),
        _item("with-book", FIXTURES / "card-with-book.chara_card_v3.json"),
        _item("atlas", FIXTURES / "lorebook.lorebook_v3.json"),
    ]
    body = {"source": PHONE, "items": items}
    async with TestClient(TestServer(app)) as client:
        _s, preview = await _post(client, "/api/content/import/preview", body)
        status, committed = await _post(client, "/api/content/import/commit",
                                        {**body, "plan_digest": preview["plan_digest"]})
        assert status == 200, committed
        rows = {row["client_ref"]: row for row in committed["items"]}
        _s, exported = await _post(client, "/api/content/export", {"items": [
            {"kind": "character_template", "canonical_id": rows["freeform"]["canonical_id"]},
            {"kind": "character_template", "canonical_id": rows["coc"]["canonical_id"]},
            {"kind": "character_template", "canonical_id": rows["with-book"]["canonical_id"]},
            {"kind": "lorebook", "canonical_id": rows["atlas"]["canonical_id"]},
        ]})
        back = [
            {"client_ref": ref, "kind": row["kind"], "document": row["document"]}
            for ref, row in zip(("freeform", "coc", "with-book", "atlas"), exported["items"])
        ]
        _s, again = await _post(client, "/api/content/import/preview", {"source": PHONE, "items": back})

    for row in exported["items"]:
        if row["format"] == "chara_card_v3":
            _check(row["document"], "chara-card-v3.schema.json")
            _check(row["document"]["data"]["extensions"]["diceframe"], "card-body.schema.json")
        else:
            _check(row["document"], "lorebook-v3.schema.json")
    assert {row["action"] for row in again["items"]} == {"unchanged"}
