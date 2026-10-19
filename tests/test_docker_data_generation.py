import json
import subprocess
import sys

import pytest

from scripts import build_docker_update
from src.docker_launcher import contracts
from tests.test_docker_launcher import _package_tree, DockerLauncher


def test_build_guard_runs_without_application_dependencies():
    result = subprocess.run(
        [sys.executable, "-S", "-c", "from scripts.build_docker_update import current_data_schemas; print(current_data_schemas())"],
        cwd=build_docker_update.ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_build_guard_reads_the_actual_migration_owners():
    from src.migrations.instance import CURRENT_INSTANCE_SCHEMA_VERSION
    from src.migrations.lorebook import CURRENT_LOREBOOK_SCHEMA_VERSION

    assert build_docker_update.current_data_schemas() == {
        "instance": CURRENT_INSTANCE_SCHEMA_VERSION,
        "lorebook": CURRENT_LOREBOOK_SCHEMA_VERSION,
    }


def test_new_data_formats_keep_the_existing_base_runtime(tmp_path):
    build_docker_update.write_manifest(tmp_path, "9.0.0", "test")
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["runtime_api"] == 1
    assert manifest["data_mode"] == "versioned-copy-v1"
    assert contracts.validate_manifest(manifest, runtime_api=1)["data_rollback_safe"] is True


@pytest.mark.parametrize("schemas", [None, {"instance": 0, "lorebook": 12}, {"instance": True, "lorebook": 12}])
def test_manifest_requires_valid_data_format_metadata(tmp_path, schemas):
    build_docker_update.write_manifest(tmp_path, "9.0.0", "test")
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifest["data_schemas"] = schemas
    with pytest.raises(ValueError, match="data schema"):
        contracts.validate_manifest(manifest)


def test_unknown_data_format_cannot_be_marked_rollback_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(build_docker_update, "current_data_schemas", lambda: {"instance": -1, "lorebook": 12})
    with pytest.raises(ValueError, match="data schema"):
        build_docker_update.write_manifest(tmp_path, "9.0.0", "test")
    assert not (tmp_path / "manifest.json").exists()


def test_unreviewed_data_format_is_rejected_before_build_tree_cleanup(tmp_path, monkeypatch):
    build_root = tmp_path / "build"
    build_root.mkdir()
    marker = build_root / "keep.txt"
    marker.write_text("existing build", encoding="utf-8")
    monkeypatch.setattr(build_docker_update, "BUILD_ROOT", build_root)
    monkeypatch.setattr(build_docker_update, "current_data_schemas", lambda: {"instance": "invalid", "lorebook": 12})
    with pytest.raises(ValueError, match="data schema"):
        build_docker_update.build_package("9.0.0", tmp_path / "output")
    assert marker.read_text(encoding="utf-8") == "existing build"


def test_incompatible_base_runtime_is_still_rejected(tmp_path):
    launcher = DockerLauncher(tmp_path / "runtime", tmp_path / "seed.zip", tmp_path / "seed.sha256")
    old = _package_tree(launcher.versions_dir, "8.0.0")
    path = old / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["runtime_api"] = 2
    path.write_text(json.dumps(manifest), encoding="utf-8")
    seed = _package_tree(launcher.versions_dir, "9.0.0")
    new_path = seed / "manifest.json"
    new_manifest = json.loads(new_path.read_text(encoding="utf-8"))
    new_manifest["runtime_api"] = 1
    new_path.write_text(json.dumps(new_manifest), encoding="utf-8")
    contracts.atomic_json(launcher.current_file, {
        "relative_dir": launcher._relative(old), "previous_relative_dir": launcher._relative(old),
    })
    assert launcher._choose_startup(seed, new_manifest) == (seed, None)
    with pytest.raises(ValueError, match="different Docker base runtime"):
        launcher._validate_dir(old)
