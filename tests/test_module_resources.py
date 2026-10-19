import io
import json

import pytest
from PIL import Image

from tests.test_module_install_hardening import (
    _make_api, _module_files, _zip_payload, ADVENTURE_ID, CONTENT_WORLD, MODULE_ID,
)


@pytest.mark.asyncio
async def test_v3_module_world_forks_its_separate_primary_book_and_rolls_back_save_failure(tmp_path, monkeypatch):
    from src.webui.services import worlds
    api, host, store = _make_api(tmp_path / "data")
    try:
        files = _module_files(adventure=False, catalog=False)
        manifest = json.loads(files["plugin.json"])
        manifest["contributes"]["lorebooks"] = ["content/lorebooks/*.json"]
        files["plugin.json"] = json.dumps(manifest).encode()
        files[f"content/worlds/{CONTENT_WORLD}.json"] = json.dumps({
            "world_schema_version": 3, "world_id": CONTENT_WORLD, "world_name": "Book World", "language": "en",
            "primary_lorebook_ref": f"module:{MODULE_ID}:lorebook:castle_lore",
        }).encode()
        files["content/lorebooks/castle_lore.json"] = json.dumps({
            "lorebook_schema_version": 1, "id": "castle_lore", "name": "Separate primary",
            "entries": [{"id": "gate", "name": "Gate", "content": "Separate Book prose", "keywords": ["gate"]}],
        }).encode()
        await api.import_module(_zip_payload(files))
        row = next(row for row in api.module_resources(MODULE_ID)["resources"] if row["kind"] == "world_template")
        checked = api.preview_module_fork(MODULE_ID, row["selector"], "en")
        assert not checked["blockers"]
        original_writer = worlds._write_json_atomic
        def failing_writer(*args):
            raise OSError("disk full")
        monkeypatch.setattr(worlds, "_write_json_atomic", failing_writer)
        body = {**checked["draft"], "reviewed": True, "plan_digest": checked["plan_digest"]}
        with pytest.raises(OSError, match="disk full"):
            api.commit_module_fork(MODULE_ID, body)
        assert not store.list_worlds() and not store.list_lorebooks()
        assert not list(api.module_forks_service.deps.worlds.worlds_dir.glob("custom_book_fork_*.json"))
        monkeypatch.setattr(worlds, "_write_json_atomic", original_writer)
        result = api.commit_module_fork(MODULE_ID, body)["result"]
        assert result["language"] == "en"
        entry = store.list_entries(result["world_id"])[0]
        assert entry["content"] == "Separate Book prose" and entry["keywords"] == ["gate"]
        await api.uninstall_plugin(MODULE_ID)
        assert store.get_world(result["world_id"])
    finally:
        store.close()


def module_with_image():
    files = _module_files(catalog=True)
    manifest = json.loads(files["plugin.json"])
    manifest["contributes"]["scene_images"] = ["assets/scenes/castle.png"]
    output = io.BytesIO()
    Image.new("RGB", (640, 360), "navy").save(output, format="PNG")
    files["assets/scenes/castle.png"] = output.getvalue()
    world_path = f"content/worlds/{CONTENT_WORLD}.json"
    world = json.loads(files[world_path])
    world["scene_image"] = {"kind": "asset", "path": "assets/scenes/castle.png"}
    files[world_path] = json.dumps(world).encode()
    files["plugin.json"] = json.dumps(manifest).encode()
    return files


@pytest.mark.asyncio
async def test_module_portrait_preview_is_pure_and_copied_media_survives_uninstall(tmp_path):
    api, host, store = _make_api(tmp_path / "data")
    try:
        files = module_with_image()
        manifest = json.loads(files["plugin.json"])
        manifest["contributes"]["portraits"] = ["assets/portraits/hero.png"]
        files["assets/portraits/hero.png"] = files["assets/scenes/castle.png"]
        files["plugin.json"] = json.dumps(manifest).encode()
        card = json.loads(files["content/characters/hero.json"])
        card["portrait"] = {"kind": "asset", "path": "assets/portraits/hero.png"}
        files["content/characters/hero.json"] = json.dumps(card).encode()
        await api.import_module(_zip_payload(files))
        rows = api.module_resources(MODULE_ID)["resources"]
        results = {}
        for kind in ("portrait_asset", "scene_image_asset", "character_template"):
            row = next(row for row in rows if row["kind"] == kind)
            checked = api.preview_module_fork(MODULE_ID, row["selector"])
            assert not checked["blockers"]
            if not results:
                assert api.list_user_avatars()["total"] == 0
            results[kind] = api.commit_module_fork(MODULE_ID, {**checked["draft"], "reviewed": True, "plan_digest": checked["plan_digest"]})["result"]
        avatar = results["portrait_asset"]["portrait"]
        assert results["character_template"]["card"]["portrait"] == avatar
        await api.uninstall_plugin(MODULE_ID)
        assert api.avatar_file(avatar["asset_id"]).is_file()
    finally:
        store.close()


@pytest.mark.asyncio
async def test_installed_disabled_module_resources_are_browsable_without_enabling_or_importing(tmp_path):
    api, host, store = _make_api(tmp_path / "data")
    try:
        await api.import_module(_zip_payload(module_with_image()))
        assert host.plugins[MODULE_ID].status == "disabled"
        result = api.module_resources(MODULE_ID)
        assert result["ok"]
        resources = result["resources"]
        assert {"world_template", "character_template", "npc", "scene_image_asset", "adventure", "monster"} <= {row["kind"] for row in resources}
        for row in resources:
            read = api.module_resource(MODULE_ID, row["selector"])
            assert read["ok"] and read["resource"]["source_digest"].startswith("sha256:")
        adventure = next(row for row in resources if row["kind"] == "adventure")
        assert api.module_resource(MODULE_ID, adventure["selector"])["resource"]["payload"]["files"]["manifest.json"]["adventure_id"] == ADVENTURE_ID
        assert not store.list_worlds() and not store.list_lorebooks() and not api.list_character_cards()["cards"]
        assert host.plugins[MODULE_ID].status == "disabled"
        with pytest.raises(ValueError):
            api.module_resource(MODULE_ID, {"origin": "contribution", "kind": "npc", "key": "../plugin.json"})
    finally:
        store.close()


@pytest.mark.asyncio
async def test_module_fork_rejects_stale_edits_source_and_dependency_before_writes(tmp_path):
    api, host, store = _make_api(tmp_path / "data")
    try:
        await api.import_module(_zip_payload(module_with_image()))
        row = next(row for row in api.module_resources(MODULE_ID)["resources"] if row["kind"] == "world_template")
        checked = api.preview_module_fork(MODULE_ID, row["selector"], "en")
        draft = checked["draft"]
        draft["payload"]["definition"]["world_name"] = "Edited copy"
        with pytest.raises(ValueError, match="stale"):
            api.commit_module_fork(MODULE_ID, {**draft, "reviewed": True, "plan_digest": checked["plan_digest"]})
        reviewed = api.review_module_fork(MODULE_ID, draft)
        assert reviewed["commit_plan"]["drafts"][0]["payload"]["name"] == "Edited copy"
        draft["payload"]["definition"] = "malformed"
        assert api.review_module_fork(MODULE_ID, draft)["blockers"]
        draft = reviewed["draft"]
        image = host.plugins[MODULE_ID].directory / "assets/scenes/castle.png"
        Image.new("RGB", (640, 360), "red").save(image)
        with pytest.raises(ValueError, match="dependencies changed"):
            api.commit_module_fork(MODULE_ID, {**draft, "reviewed": True, "plan_digest": reviewed["plan_digest"]})
        assert not store.list_worlds() and not store.list_lorebooks()
        checked = api.preview_module_fork(MODULE_ID, row["selector"])
        path = host.plugins[MODULE_ID].directory / f"content/worlds/{CONTENT_WORLD}.json"
        source = json.loads(path.read_text())
        source["world_name"] = "Changed source"
        path.write_text(json.dumps(source))
        with pytest.raises(ValueError, match="source changed"):
            api.review_module_fork(MODULE_ID, checked["draft"])
    finally:
        store.close()


@pytest.mark.asyncio
async def test_unsupported_native_adventure_media_is_blocked_in_review(tmp_path):
    api, host, store = _make_api(tmp_path / "data")
    try:
        files = module_with_image()
        files["adventures/castle/assets/map.png"] = files["assets/scenes/castle.png"]
        await api.import_module(_zip_payload(files))
        row = next(row for row in api.module_resources(MODULE_ID)["resources"] if row["kind"] == "adventure")
        checked = api.preview_module_fork(MODULE_ID, row["selector"])
        assert checked["blockers"] and "JSON" in checked["blockers"][0]
        with pytest.raises(ValueError, match="blocking"):
            api.commit_module_fork(MODULE_ID, {**checked["draft"], "reviewed": True, "plan_digest": checked["plan_digest"]})
        assert not list(api.module_forks_service.deps.adventures.adventure_loader.adventures_dir.glob("fork_*"))
    finally:
        store.close()


@pytest.mark.asyncio
async def test_native_module_forks_are_reviewed_user_content_and_survive_source_uninstall(tmp_path):
    api, host, store = _make_api(tmp_path / "data")
    try:
        await api.import_module(_zip_payload(module_with_image()))
        resources = api.module_resources(MODULE_ID)["resources"]
        results = {}
        for kind in ("world_template", "character_template", "npc", "adventure"):
            row = next(row for row in resources if row["kind"] == kind)
            checked = api.preview_module_fork(MODULE_ID, row["selector"])
            assert checked["ok"] and not checked["blockers"]
            draft = checked["draft"]
            if kind == "character_template":
                draft["payload"]["background"] = "Edited blueprint background"
            checked = api.review_module_fork(MODULE_ID, draft)
            assert not checked["blockers"]
            results[kind] = api.commit_module_fork(MODULE_ID, {**draft, "reviewed": True, "plan_digest": checked["plan_digest"]})
            assert results[kind]["ok"]
        card = results["character_template"]["result"]["card"]
        assert card["background"] == "Edited blueprint background" and not card.get("source_plugin")
        world_id = results["world_template"]["result"]["world_id"]
        assert store.list_entries(world_id)[0]["content"] == "石门。"
        native_file = api.module_forks_service.deps.worlds.worlds_dir / f"{world_id}.json"
        image = json.loads(native_file.read_text(encoding="utf-8"))["scene_image"]
        assert image["kind"] == "upload"
        assert host.plugins[MODULE_ID].status == "disabled"
        await api.uninstall_plugin(MODULE_ID)
        assert store.get_world(world_id)
        assert any(item["id"] == card["id"] for item in api.list_character_cards()["cards"])
        assert api.adventure_detail(results["adventure"]["result"]["adventure_id"])["ok"]
    finally:
        store.close()
