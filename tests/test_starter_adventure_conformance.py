"""The shipped creator example must survive the same validator as installation."""
from pathlib import Path
import shutil
import json

import pytest

from scripts.validate_content_module import validate_module
from scripts.package_plugin import make_zip
from src.plugin_host.host import PluginHost
from tests.test_golden_e2e_54pr import golden, _dnd_characters  # noqa: F401

SOURCE = Path(__file__).resolve().parents[1] / "plugins/examples/starter-adventure"


def test_original_starter_validates_before_and_after_packaging(tmp_path):
    assert validate_module(SOURCE)["ok"]
    artifact = make_zip(SOURCE, tmp_path / "starter.dfplugin", overwrite=False)
    import zipfile
    with zipfile.ZipFile(artifact) as archive:
        archive.extractall(tmp_path / "unpacked")
    report = validate_module(tmp_path / "unpacked/starter-adventure")
    assert report["ok"], report
    assert len(report["adventures"]) == 1


@pytest.mark.parametrize("invalid", ["entrypoint", "runtime", "path", "secret-locale", "relation-kind"])
def test_starter_blockers_are_actionable_and_do_not_modify_source(tmp_path, invalid):
    directory = tmp_path / "starter-adventure"
    shutil.copytree(SOURCE, directory)
    manifest = directory / "plugin.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if invalid == "entrypoint":
        payload["entrypoint"] = ["python", "forbidden.py"]
    elif invalid == "path":
        payload["adventure_packages"] = ["../outside"]
    elif invalid == "runtime":
        adventure = directory / "adventures/lantern-harbor/manifest.json"
        data = json.loads(adventure.read_text(encoding="utf-8"))
        data["required_runtime"] = {"id": "missing:runtime", "minimum_version": 999}
        adventure.write_text(json.dumps(data), encoding="utf-8")
    elif invalid == "relation-kind":
        graph = directory / "adventures/lantern-harbor/adventure.json"
        data = json.loads(graph.read_text(encoding="utf-8"))
        data["world_seed"]["relations"][0]["kind"] = "unknown-relation"
        graph.write_text(json.dumps(data), encoding="utf-8")
    else:
        locale = directory / "adventures/lantern-harbor/locales/zh-CN/adventure.json"
        data = json.loads(locale.read_text(encoding="utf-8"))
        data["fields"]["nodes"] = [{"id": "secret", "visibility": "public"}]
        locale.write_text(json.dumps(data), encoding="utf-8")
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    before = manifest.read_bytes()
    report = validate_module(directory)
    assert report["ok"] is False and report["errors"], report
    assert manifest.read_bytes() == before


@pytest.mark.asyncio
async def test_starter_install_start_private_projection_save_reload_and_reexport(golden, tmp_path):
    from src.engine import persistence
    from src.webui.services import modules

    artifact = make_zip(SOURCE, tmp_path / "starter.dfplugin", overwrite=False)
    installed = await golden.api.import_module(artifact.read_bytes())
    assert installed["ok"], installed
    await golden.api.update_plugin_config("starter-adventure", {"enabled": True})
    resources = golden.host.list_content_resources()
    assert any(row["name"] == "Harbor Keeper Notes" for row in resources["lorebook"])
    created = await golden.api.create_game(
        "lantern_harbor", game_name="Starter acceptance", rule_id="dnd2024_srd",
        players=_dnd_characters(1), language="en", adventure_id="plugin:lantern-harbor",
        adventure_source_kind="plugin", adventure_source_id="starter-adventure",
    )
    assert created["ok"], created
    key = created["game_key"]
    instance = golden.instance(key)
    gm = golden.api.game_adventure_projection(key, viewer_is_gm=True)
    public = golden.api.game_adventure_projection(key, viewer_is_gm=False)
    assert "PRIVATE_STARTER_CLUE" in json.dumps(gm)
    assert "PRIVATE_STARTER_CLUE" not in json.dumps(public)
    assert gm["adventure"]["binding"]["source_id"] == "starter-adventure"
    await persistence.save(golden.api._reg, instance)
    reborn, host = golden._make_api()
    try:
        assert await reborn._reg.recover_all()
        loaded = reborn.get_game_instance(key)
        assert loaded.adventure_binding == instance.adventure_binding
        assert reborn.game_adventure_projection(key, viewer_is_gm=True)["adventure"]["available"]
        with pytest.raises(modules.ModuleInUse):
            await reborn.import_module(artifact.read_bytes(), overwrite=True)
        exported = reborn.export_content_pack(
            "starter-roundtrip", "Starter roundtrip", "1.0.0", "Conformance fixture",
            adventure_refs=[{"source_kind": "plugin", "source_id": "starter-adventure", "adventure_id": "plugin:lantern-harbor"}],
            language="en",
        )
        assert exported["ok"], exported
        other = PluginHost(tmp_path / "other-plugins", tmp_path / "other-data")
        await other.install_from_zip(exported["payload"])
        assert other.plugins["starter-roundtrip"].adventure_package_directories == ("lantern-harbor",)
    finally:
        host.plugins.clear()
