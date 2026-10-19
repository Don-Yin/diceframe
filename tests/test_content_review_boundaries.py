from src.lorebook.store import LorebookStore
from src.webui.services.lorebooks import LorebookDependencies, commit_lorebook_import, preview_lorebook_import


def test_unresolved_lore_references_block_commit_even_without_a_preview_token(tmp_path):
    store = LorebookStore(tmp_path / "books.db")
    store.open()
    try:
        deps = LorebookDependencies(store, lambda _key: None, lambda: None)
        payload = {"name": "Notes", "entries": [{"uid": 1, "content": "keeper"}],
                   "references": [{"source_kind": "module", "source_id": "castle", "kind": "npc", "id": "keeper"}]}
        preview = preview_lorebook_import(deps, payload)
        assert preview["commit_plan"]["unresolved_references"]
        result = commit_lorebook_import(deps, payload)
        assert result["ok"] is False and result["code"] == "IMPORT_UNRESOLVED_REFERENCES"
        assert not store.list_lorebooks()
    finally:
        store.close()


def test_review_token_covers_entry_text_not_just_entry_names(tmp_path):
    store = LorebookStore(tmp_path / "books.db")
    store.open()
    try:
        deps = LorebookDependencies(store, lambda _key: None, lambda: None)
        payload = {"name": "Notes", "entries": [{"uid": 1, "content": "Reviewed text"}]}
        token = preview_lorebook_import(deps, payload)["plan_digest"]
        assert token == preview_lorebook_import(deps, {**payload, "duplicate_policy": "update"})["plan_digest"]
        payload["entries"][0]["content"] = "Unreviewed replacement"
        result = commit_lorebook_import(deps, payload, plan_digest=token)
        assert result["ok"] is False and result["code"] == "IMPORT_PLAN_STALE"
        assert not store.list_lorebooks()
    finally:
        store.close()


def test_duplicate_choices_match_real_books_and_preserve_existing_content(tmp_path):
    store = LorebookStore(tmp_path / "books.db")
    store.open()
    try:
        deps = LorebookDependencies(store, lambda _key: None, lambda: None)
        payload = {"name": "Notes", "entries": [{"uid": 1, "content": "First"}]}
        original = commit_lorebook_import(deps, payload)["book_id"]
        payload["entries"][0]["content"] = "Second"
        checked = preview_lorebook_import(deps, payload)
        assert checked["commit_plan"]["operations"][0]["existing_ref"]
        skipped = commit_lorebook_import(deps, payload, plan_digest=checked["plan_digest"], duplicate_policy="skip")
        assert skipped["ok"] and skipped["skipped"]
        assert store.list_book_entries(original)[0]["content"] == "First"
        copied = commit_lorebook_import(deps, payload, plan_digest=checked["plan_digest"], duplicate_policy="duplicate")
        assert copied["ok"] and copied["book_id"] != original and len(store.list_lorebooks()) == 2
        assert store.list_book_entries(original)[0]["content"] == "First"
    finally:
        store.close()


def test_domain_import_preserves_declared_source_kind(tmp_path):
    from src.lorebook.importer import commit_lorebook_import as commit_draft, draft_lorebook_import
    store = LorebookStore(tmp_path / "books.db")
    store.open()
    try:
        draft = draft_lorebook_import({"name": "Keepers", "entries": [{"uid": 1, "content": "Guard"}]})
        draft.source = {"kind": "external_adapter", "source_kind": "module", "source_id": "castle", "external_id": "keepers"}
        identity = commit_draft(store, draft)
        assert store.get_lorebook(identity)["source_kind"] == "module"
    finally:
        store.close()
