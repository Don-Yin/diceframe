"""Confirmable Lorebook import plans (PR G2b).

Protected contracts:
- preview returns a ``plan`` whose ``plan_digest`` covers each item's draft
  digest, matched canonical Book and that Book's state token (revision);
- commit recomputes the plan and refuses a stale one with ``PLAN_STALE`` and a
  fresh preview; a match always needs an explicit decision;
- update is a full mirror (metadata, settings, entries incl. deletions) that
  keeps bindings and ``enabled``; duplicate makes a new tracked Book and
  detaches the old one; skip writes nothing; unchanged is detected from the
  recorded source digest and server state;
- a retried commit never writes twice;
- the legacy commit route (no ``plan_digest``) keeps its behaviour.
"""

from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.webui.routes.lorebooks import register_lorebooks

pytest_plugins = ["tests.webapi_harness"]

DEVICE = {"kind": "device", "id": "install-a"}


def _book(name: str, entries: dict[str, str], **book_fields) -> dict:
    return {
        "spec": "lorebook_v3",
        "data": {"lorebook": {"name": name, **book_fields, "entries": [
            {"id": key, "name": key, "content": content, "keys": [key]}
            for key, content in entries.items()
        ]}},
    }


def _push(document: dict, *, external_id: str = "book-1", source: dict | None = None) -> dict:
    return {"payload": document, "source": source or DEVICE, "external_id": external_id}


def _preview(api, body: dict) -> dict:
    result = api.preview_lorebook_import(body)
    assert "plan" in result, result
    return result


def _commit(api, body: dict, *, decision: str | None = None, digest: str | None = None) -> dict:
    plan_digest = digest if digest is not None else _preview(api, body)["plan"]["plan_digest"]
    request = {**body, "plan_digest": plan_digest}
    if decision is not None:
        request["decision"] = decision
    return api.commit_lorebook_plan(request)


def _item(preview: dict) -> dict:
    [item] = preview["plan"]["items"]
    return item


def _entry_contents(lorebook, book_id: str) -> dict[str, str]:
    return {row["name"]: row["content"] for row in lorebook.list_book_entries(book_id)}


def test_first_push_creates_a_tracked_book_with_its_identity(web_api) -> None:
    api, lorebook, *_ = web_api
    body = _push(_book("Atlas", {"town": "Town lore"}))

    preview = _preview(api, body)
    assert _item(preview)["action"] == "create"
    assert _item(preview)["existing"] is None

    result = _commit(api, body)

    assert result["ok"] and result["status"] == "created"
    book = lorebook.get_lorebook(result["book_id"])
    assert (book["source_kind"], book["source_id"], book["external_id"]) == ("device", "install-a", "book-1")
    assert book["import_link"] == "tracked"
    assert book["source_digest"] == _item(preview)["draft_digest"]
    assert result["state_token"] == str(book["revision"])


def test_repush_without_changes_is_unchanged_and_writes_nothing(web_api) -> None:
    api, lorebook, *_ = web_api
    body = _push(_book("Atlas", {"town": "Town lore"}))
    created = _commit(api, body)
    revision = lorebook.get_lorebook(created["book_id"])["revision"]

    item = _item(_preview(api, body))
    assert item["action"] == "unchanged"
    assert item["existing"]["canonical_id"] == created["book_id"]
    assert item["existing"]["server_modified"] is False

    result = _commit(api, body, decision="update")
    assert result["status"] == "unchanged"
    assert lorebook.get_lorebook(created["book_id"])["revision"] == revision


def test_update_is_a_full_mirror_that_keeps_bindings_and_enabled(web_api) -> None:
    api, lorebook, *_ = web_api
    created = _commit(api, _push(_book("Atlas", {"town": "Town", "keep": "Keep", "ruin": "Ruin"})))
    book_id = created["book_id"]
    lorebook.bind_lorebook({"id": "bind:global", "book_id": book_id, "scope_kind": "global", "scope_id": ""})
    lorebook.update_lorebook(book_id, {"enabled": False})

    edited = _push(_book(
        "Atlas Revised", {"town": "Town v2", "keep": "Keep", "glacier": "Glacier"},
        description="Second edition", scan_depth=7,
    ))
    item = _item(_preview(api, edited))
    assert item["action"] == "update"
    assert (item["existing"]["entries_add"], item["existing"]["entries_remove"]) == (1, 1)
    assert item["existing"]["server_modified"] is False

    result = _commit(api, edited, decision="update")

    assert result["status"] == "updated" and result["book_id"] == book_id
    assert result["entries_removed"] == 1
    book = lorebook.get_lorebook(book_id)
    assert (book["name"], book["description"], book["scan_depth"]) == ("Atlas Revised", "Second edition", 7)
    assert _entry_contents(lorebook, book_id) == {"town": "Town v2", "keep": "Keep", "glacier": "Glacier"}
    assert [b["id"] for b in lorebook.list_bindings() if b["book_id"] == book_id] == ["bind:global"]
    assert not book["enabled"]
    assert len(lorebook.list_lorebooks()) == 1


def test_server_edits_are_flagged_as_server_modified(web_api) -> None:
    api, lorebook, *_ = web_api
    body = _push(_book("Atlas", {"town": "Town"}))
    created = _commit(api, body)
    [entry] = lorebook.list_book_entries(created["book_id"])
    lorebook.update_book_entry(created["book_id"], entry["id"], {"content": "Edited on the server"})

    item = _item(_preview(api, body))

    assert item["existing"]["server_modified"] is True
    assert item["action"] == "update"


def test_skip_returns_the_existing_book_and_writes_nothing(web_api) -> None:
    api, lorebook, *_ = web_api
    created = _commit(api, _push(_book("Atlas", {"town": "Town"})))
    revision = lorebook.get_lorebook(created["book_id"])["revision"]

    result = _commit(api, _push(_book("Atlas", {"town": "Changed"})), decision="skip")

    assert result["status"] == "skipped" and result["book_id"] == created["book_id"]
    assert _entry_contents(lorebook, created["book_id"]) == {"town": "Town"}
    assert lorebook.get_lorebook(created["book_id"])["revision"] == revision


def test_duplicate_keeps_both_and_detaches_the_old_copy(web_api) -> None:
    api, lorebook, *_ = web_api
    created = _commit(api, _push(_book("Atlas", {"town": "Town"})))
    edited = _push(_book("Atlas", {"town": "Changed"}))

    result = _commit(api, edited, decision="duplicate")

    assert result["status"] == "duplicated"
    assert result["detached_book_id"] == created["book_id"]
    new_id = result["book_id"]
    assert new_id != created["book_id"]
    old, new = lorebook.get_lorebook(created["book_id"]), lorebook.get_lorebook(new_id)
    assert old["import_link"] == "detached" and new["import_link"] == "tracked"
    # The detached copy keeps its provenance and its content.
    assert (old["source_id"], old["external_id"]) == ("install-a", "book-1")
    assert _entry_contents(lorebook, created["book_id"]) == {"town": "Town"}
    assert _entry_contents(lorebook, new_id) == {"town": "Changed"}
    # Later pushes follow the new copy.
    assert _item(_preview(api, edited))["existing"]["canonical_id"] == new_id


def test_a_stale_plan_is_refused_with_a_fresh_preview(web_api) -> None:
    api, lorebook, *_ = web_api
    body = _push(_book("Atlas", {"town": "Town"}))
    created = _commit(api, body)
    edited = _push(_book("Atlas", {"town": "Changed"}))
    seen = _preview(api, edited)["plan"]["plan_digest"]
    # The server copy moves after the user reviewed the plan.
    [entry] = lorebook.list_book_entries(created["book_id"])
    lorebook.update_book_entry(created["book_id"], entry["id"], {"content": "Edited meanwhile"})

    stale = _commit(api, edited, decision="update", digest=seen)

    assert stale["ok"] is False and stale["error_code"] == "PLAN_STALE"
    fresh = stale["preview"]["plan"]
    assert fresh["plan_digest"] != seen
    assert fresh["items"][0]["existing"]["server_modified"] is True
    assert _entry_contents(lorebook, created["book_id"]) == {"town": "Edited meanwhile"}

    applied = _commit(api, edited, decision="update", digest=fresh["plan_digest"])
    assert applied["status"] == "updated"


def test_a_retried_commit_never_writes_twice(web_api) -> None:
    api, lorebook, *_ = web_api
    body = _push(_book("Atlas", {"town": "Town"}))
    digest = _preview(api, body)["plan"]["plan_digest"]

    first = _commit(api, body, digest=digest)
    retry = _commit(api, body, digest=digest)

    assert first["status"] == "created"
    assert retry["error_code"] == "PLAN_STALE"
    assert retry["preview"]["plan"]["items"][0]["action"] == "unchanged"
    assert len(lorebook.list_lorebooks()) == 1


def test_a_match_needs_an_explicit_decision(web_api) -> None:
    api, _lorebook, *_ = web_api
    body = _push(_book("Atlas", {"town": "Town"}))
    _commit(api, body)

    missing = _commit(api, _push(_book("Atlas", {"town": "Changed"})))
    bogus = _commit(api, _push(_book("Atlas", {"town": "Changed"})), decision="merge")

    assert missing["error_code"] == "DECISION_REQUIRED"
    assert bogus["error_code"] == "DECISION_NOT_ALLOWED"


def test_two_installs_pushing_the_same_local_id_get_two_books(web_api) -> None:
    api, lorebook, *_ = web_api
    first = _commit(api, _push(_book("Atlas", {"town": "Town"})))
    second = _commit(api, _push(_book("Atlas", {"town": "Town"}), source={"kind": "device", "id": "install-b"}))

    assert second["status"] == "created"
    assert first["book_id"] != second["book_id"]
    assert len(lorebook.list_lorebooks()) == 2


@pytest.mark.parametrize("source, external_id", [
    ({"kind": "plugin", "id": "some-plugin"}, "book-1"),
    ({"kind": "device", "id": "has space"}, "book-1"),
    ({"kind": "device", "id": "install-a"}, None),
    ("device:install-a", "book-1"),
])
def test_only_a_canonical_device_identity_can_be_declared(web_api, source, external_id) -> None:
    api, lorebook, *_ = web_api
    body = {"payload": _book("Atlas", {"town": "Town"}), "source": source, "external_id": external_id}

    preview = api.preview_lorebook_import(body)
    commit = api.commit_lorebook_plan({**body, "plan_digest": "sha256:x"})

    assert preview["error_code"] == "IMPORT_SOURCE_INVALID"
    assert commit["error_code"] == "IMPORT_SOURCE_INVALID"
    assert lorebook.list_lorebooks() == []


def test_legacy_commit_without_a_plan_keeps_its_behaviour(web_api) -> None:
    api, lorebook, *_ = web_api
    document = _book("Atlas", {"town": "Town", "keep": "Keep"})
    first = api.commit_lorebook_import(document)
    book_id = first["book_id"]

    # Same source again with a dropped entry: the legacy path upserts only.
    again = api.commit_lorebook_import(_book("Atlas", {"town": "Town", "keep": "Keep"}), book_id=book_id)
    smaller = api.commit_lorebook_import(_book("Atlas", {"town": "Town v2"}), book_id=book_id)

    assert again["ok"] and smaller["ok"]
    assert _entry_contents(lorebook, book_id) == {"town": "Town v2", "keep": "Keep"}
    book = lorebook.get_lorebook(book_id)
    assert book["import_link"] == "" and book["source_digest"] == ""
    # The legacy preview keeps its single-policy commit plan.
    legacy = api.preview_lorebook_import({**document, "duplicate_policy": "skip"})
    assert [op["action"] for op in legacy["commit_plan"]["operations"]] == ["skip"]


# ---- Route mapping ------------------------------------------------------------


class _PlanApi:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.legacy_calls = 0

    def commit_lorebook_plan(self, body):
        return self.result

    def commit_lorebook_import(self, payload, binding=None, book_id=None):
        self.legacy_calls += 1
        return {"ok": True, "book_id": "legacy"}


def _route_app(api: _PlanApi) -> web.Application:
    app = web.Application()
    app["api"] = api
    register_lorebooks(app)
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("code, status", [
    ("PLAN_STALE", 409), ("LOREBOOK_IDENTITY_CONFLICT", 409), ("DECISION_REQUIRED", 400),
])
async def test_plan_commit_route_maps_error_codes(code, status) -> None:
    api = _PlanApi({"ok": False, "error_code": code, "error": code})
    async with TestClient(TestServer(_route_app(api))) as client:
        response = await client.post(
            "/api/lorebooks/import", json={"payload": {}, "plan_digest": "sha256:x"},
        )
    assert response.status == status
    assert api.legacy_calls == 0


@pytest.mark.asyncio
async def test_plan_fields_without_a_plan_digest_are_refused() -> None:
    api = _PlanApi({"ok": True})
    async with TestClient(TestServer(_route_app(api))) as client:
        response = await client.post(
            "/api/lorebooks/import",
            json={"payload": {}, "source": DEVICE, "external_id": "book-1"},
        )
        body = await response.json()
    assert response.status == 400 and body["error_code"] == "PLAN_DIGEST_REQUIRED"
    assert api.legacy_calls == 0


# ---- Schema v11 -----------------------------------------------------------------


def test_v11_moves_uniqueness_to_tracked_books_and_is_idempotent() -> None:
    import sqlite3

    from src.lorebook.store import SCHEMA
    from src.migrations import lorebook as migrations

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    assert migrations.migrate(conn, upto=10) == 10
    conn.execute(
        "INSERT INTO lorebooks (id, name, source_kind, source_id, external_id) "
        "VALUES ('a', 'A', 'device', 'install-a', 'book-1')"
    )
    conn.commit()

    assert migrations.migrate(conn) == 11
    assert migrations.migrate(conn) == 11
    migrations._v11(conn)

    row = conn.execute("SELECT external_id, import_link, import_state_digest FROM lorebooks").fetchone()
    assert row == ("book-1", "", "")
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "idx_lorebooks_external_identity" not in names
    assert "idx_lorebooks_tracked_identity" in names
    insert = (
        "INSERT INTO lorebooks (id, name, source_kind, source_id, external_id, import_link) "
        "VALUES (?, ?, 'device', 'install-a', 'book-1', ?)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert, ("b", "B", "tracked"))
    conn.execute("UPDATE lorebooks SET import_link = 'detached' WHERE id = 'a'")
    conn.execute(insert, ("b", "B", "tracked"))
    conn.execute(insert, ("c", "C", "detached"))


# ---- #487 review follow-ups ----------------------------------------------------


@pytest.mark.parametrize("decision", ["skip", "update"])
def test_a_binding_is_never_silently_dropped_by_an_answer_that_writes_nothing(web_api, decision) -> None:
    api, lorebook, *_ = web_api
    body = _push(_book("Atlas", {"town": "Town"}))
    created = _commit(api, body)
    binding = {"id": "bind:new", "scope_kind": "global", "scope_id": ""}

    preview = _preview(api, body)
    assert _item(preview)["action"] == "unchanged"
    result = api.commit_lorebook_plan({
        **body, "plan_digest": preview["plan"]["plan_digest"],
        "decision": decision, "binding": binding,
    })

    assert result["ok"] is False and result["error_code"] == "BINDING_REQUIRES_WRITE"
    assert [b for b in lorebook.list_bindings() if b["book_id"] == created["book_id"]] == []


def test_several_legacy_books_sharing_a_source_resolve_deterministically(web_api) -> None:
    api, lorebook, *_ = web_api
    document = _book("Atlas", {"town": "Town"})
    first = api.commit_lorebook_import(document)["book_id"]
    source = lorebook.get_lorebook(first)
    # A second legacy Book with the same source (e.g. an older explicit book_id import).
    lorebook.create_lorebook({
        "id": "aaa-older-id", "name": "Atlas copy",
        "source_kind": source["source_kind"], "source_id": source["source_id"],
    })

    items = [_item(_preview(api, document)) for _ in range(3)]

    assert len({item["existing"]["canonical_id"] for item in items}) == 1
    target = items[0]["existing"]["canonical_id"]
    others = items[0]["existing"]["other_matches"]
    assert sorted([target, *others]) == sorted([first, "aaa-older-id"])
