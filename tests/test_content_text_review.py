from copy import deepcopy

import pytest

from tests.test_module_install_hardening import _make_api


def test_text_fragments_can_be_edited_and_distributed_to_real_content_owners(tmp_path):
    api, _host, store = _make_api(tmp_path / "data")
    try:
        preview = api.preview_content_text("# Harbor\nFog.\n# Keeper\nFriendly.\n# Rumor\nLost bell.\n# Quest\nFind it.", "notes.md", "en")
        assert len(preview["draft"]["items"]) == 4
        draft = preview["draft"]
        for item, target in zip(draft["items"], ["world", "character_template", "lorebook", "adventure"], strict=True):
            item["target"] = target
        draft["items"][1]["text"] = "Reviewed keeper background"
        checked = api.review_content_text(draft)
        assert not checked["blockers"]
        assert len(checked["commit_plan"]["operations"]) == 4
        assert not store.list_worlds() and not store.list_lorebooks()
        result = api.commit_content_text({**draft, "reviewed": True, "plan_digest": checked["plan_digest"]})
        assert result["ok"] and len(result["results"]) == 4
        outputs = {row["target"]: row["result"] for row in result["results"]}
        assert store.get_world(outputs["world"]["world_id"])["description"] == "Fog."
        assert outputs["character_template"]["card"]["background"] == "Reviewed keeper background"
        assert outputs["character_template"]["card"]["attributes"] == {}
        assert store.list_book_entries(outputs["lorebook"]["book_id"])[0]["content"] == "Lost bell."
        assert store.get_lorebook(outputs["lorebook"]["book_id"])["language"] == "en"
        assert api.adventure_detail(outputs["adventure"]["adventure_id"])["adventure"]["custom"]
        assert api.commit_content_text({**draft, "reviewed": True, "plan_digest": checked["plan_digest"]}) == result
    finally:
        store.close()


def test_unknown_receipt_schema_fails_closed_and_character_conflicts_do_not_upsert(tmp_path):
    import json
    api, _host, store = _make_api(tmp_path / "data")
    try:
        checked = api.preview_content_text("# Keeper\nSame background", "notes.md", "en")
        draft = checked["draft"]
        draft["items"][0]["target"] = "character_template"
        checked = api.review_content_text(draft)
        body = {**draft, "reviewed": True, "plan_digest": checked["plan_digest"]}
        result = api.commit_content_text(body)
        assert result["ok"]
        assert api.review_content_text(draft)["blockers"]
        receipt = api.content_text_review.deps.receipts_dir / f"{checked['plan_digest'][7:]}.json"
        stored = json.loads(receipt.read_text(encoding="utf-8"))
        stored["schema"] = 99
        receipt.write_text(json.dumps(stored), encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported"):
            api.commit_content_text(body)
        assert len(api.list_character_cards()["cards"]) == 1
    finally:
        store.close()


def test_explicit_fork_creates_an_independent_book_and_keeps_original(tmp_path):
    api, _host, store = _make_api(tmp_path / "data")
    try:
        checked = api.preview_content_text("# Note\nOriginal", "notes.md", "en")
        body = {**checked["draft"], "reviewed": True, "plan_digest": checked["plan_digest"]}
        first = api.commit_content_text(body)
        checked = api.review_content_text(checked["draft"])
        assert checked["blockers"] and checked["commit_plan"]["operations"][0]["existing_ref"]
        draft = checked["draft"]
        draft["copy_id"] = "a" * 32
        draft["items"][0]["text"] = "Forked content"
        checked = api.review_content_text(draft)
        assert not checked["blockers"]
        forked = api.commit_content_text({**draft, "reviewed": True, "plan_digest": checked["plan_digest"]})
        assert forked["ok"] and len(store.list_lorebooks()) == 2
        assert store.list_book_entries(first["results"][0]["result"]["book_id"])[0]["content"] == "Original"
    finally:
        store.close()


def test_receipt_failure_reports_saved_resource_once_and_replay_cannot_overwrite(tmp_path, monkeypatch):
    api, _host, store = _make_api(tmp_path / "data")
    try:
        checked = api.preview_content_text("# Note\nOriginal", "notes.md", "en")
        body = {**checked["draft"], "reviewed": True, "plan_digest": checked["plan_digest"]}
        writer = api.content_text_review.write_receipt
        calls = 0

        def failing(path, receipt):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("receipt disk full")
            writer(path, receipt)

        monkeypatch.setattr(api.content_text_review, "write_receipt", failing)
        result = api.commit_content_text(body)
        assert result["recovery_required"] and len(result["results"]) == 1 and result["results"][0]["ok"]
        assert len(store.list_lorebooks()) == 1
        retry = api.commit_content_text(body)
        assert not retry["ok"] and len(store.list_lorebooks()) == 1
    finally:
        store.close()


def test_character_review_preserves_an_unreadable_existing_library(tmp_path):
    api, _host, store = _make_api(tmp_path / "data")
    try:
        checked = api.preview_content_text("# Keeper\nBackground", "notes.md", "en")
        checked["draft"]["items"][0]["target"] = "character_template"
        path = api.content_text_review.deps.characters.cards_path
        path.write_text("{corrupt library", encoding="utf-8")
        with pytest.raises(ValueError, match="character library"):
            api.review_content_text(checked["draft"])
        assert path.read_text(encoding="utf-8") == "{corrupt library"
    finally:
        store.close()


def test_stale_review_and_unknown_reference_never_write(tmp_path):
    api, _host, store = _make_api(tmp_path / "data")
    try:
        checked = api.preview_content_text("# Notes\nReviewed", "notes.md", "en")
        draft = deepcopy(checked["draft"])
        draft["items"][0]["text"] = "Changed"
        with pytest.raises(ValueError, match="stale"):
            api.commit_content_text({**draft, "reviewed": True, "plan_digest": checked["plan_digest"]})
        draft["items"][0]["references"] = [{"source_kind": "module", "source_id": "missing", "kind": "npc", "id": "keeper"}]
        checked = api.review_content_text(draft)
        assert checked["commit_plan"]["unresolved_references"] and checked["blockers"]
        with pytest.raises(ValueError, match="blocking"):
            api.commit_content_text({**draft, "reviewed": True, "plan_digest": checked["plan_digest"]})
        assert not store.list_lorebooks()
    finally:
        store.close()


def test_adventure_marker_references_are_visible_in_the_shared_plan(tmp_path):
    api, _host, store = _make_api(tmp_path / "data")
    try:
        checked = api.preview_content_text("# Quest\n@npc missing_guard", "notes.md", "en")
        checked["draft"]["items"][0]["target"] = "adventure"
        reviewed = api.review_content_text(checked["draft"])
        assert reviewed["blockers"]
        assert reviewed["commit_plan"]["unresolved_references"][0]["id"] == "missing_guard"
    finally:
        store.close()


def test_partial_save_is_reported_and_retry_does_not_repeat_success(tmp_path, monkeypatch):
    api, _host, store = _make_api(tmp_path / "data")
    try:
        checked = api.preview_content_text("# One\nFirst\n# Two\nSecond", "notes.md", "en")
        body = {**checked["draft"], "reviewed": True, "plan_digest": checked["plan_digest"]}
        service = api.content_text_review
        commit_one = service.commit_one
        calls = []

        def failing(item, prepared):
            calls.append(item["id"])
            if len(calls) == 2:
                raise OSError("disk full")
            return commit_one(item, prepared)

        monkeypatch.setattr(service, "commit_one", failing)
        first = api.commit_content_text(body)
        assert not first["ok"] and first["results"][0]["ok"] and not first["results"][1]["ok"]
        assert len(store.list_lorebooks()) == 1
        monkeypatch.setattr(service, "commit_one", commit_one)
        retry = api.commit_content_text(body)
        assert retry["ok"] and len(store.list_lorebooks()) == 2
        changed = deepcopy(body)
        changed["items"][0]["text"] = "Injected after receipt"
        with pytest.raises(ValueError, match="stale"):
            api.commit_content_text(changed)
    finally:
        store.close()
