import json
import sqlite3
from pathlib import Path

import pytest

from src.docker_launcher import data_versions


def installation(tmp_path):
    home = tmp_path / "data"
    runtime = home / "_updater"
    payload = runtime / "docker-versions" / "v3.0.0"
    app = payload / "app"
    app.mkdir(parents=True)
    (payload / "manifest.json").write_text(json.dumps({
        "version": "3.0.0", "data_mode": "versioned-copy-v1",
    }), encoding="utf-8")
    (home / "saves").mkdir()
    (home / "saves" / "game.json").write_text('{"instance_schema_version":43,"round":7}', encoding="utf-8")
    (home / "config.json").write_text('{"model":"configured"}', encoding="utf-8")
    with sqlite3.connect(home / "lorebook.db") as db:
        db.execute("PRAGMA user_version=11")
        db.execute("CREATE TABLE books(name TEXT)")
        db.execute("INSERT INTO books VALUES ('original')")
    (runtime / "current.json").write_text(json.dumps({
        "relative_dir": "docker-versions/v2.6.1", "previous_relative_dir": "",
    }), encoding="utf-8")
    (runtime / "docker-versions/v2.6.1").mkdir()
    (runtime / "docker-versions/v2.6.1/manifest.json").write_text('{"version":"2.6.1"}')
    env = {"TRPG_INSTALL_MODE": "docker-managed", "TRPG_DATA_DIR": str(home),
           "TRPG_DOCKER_RUNTIME_ROOT": str(runtime), "TRPG_ACTIVE_VERSION_DIR": str(payload)}
    return home, runtime, app, env


def test_first_upgrade_migrates_a_copy_and_leaves_old_reader_data_intact(tmp_path):
    home, runtime, app, env = installation(tmp_path)
    selected = data_versions.prepare_version_data(app, env)
    assert selected != home
    assert selected.is_relative_to(runtime / "data-versions")
    assert not (selected / "_updater").exists()
    assert env["TRPG_DATA_DIR"] == str(selected)
    assert env["TRPG_DOCKER_DATA_HOME"] == str(home)
    with sqlite3.connect(selected / "lorebook.db") as db:
        db.execute("PRAGMA user_version=12")
        db.execute("UPDATE books SET name='new'")
    (selected / "saves/game.json").write_text('{"instance_schema_version":44,"round":8}', encoding="utf-8")
    with sqlite3.connect(home / "lorebook.db") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 11
        assert db.execute("SELECT name FROM books").fetchone()[0] == "original"
    assert json.loads((home / "saves/game.json").read_text())["round"] == 7


def test_failed_candidate_retry_starts_from_last_committed_data(tmp_path):
    home, runtime, app, env = installation(tmp_path)
    first = data_versions.prepare_version_data(app, env)
    (first / "saves/game.json").write_text('{"round":999}', encoding="utf-8")
    env["TRPG_DATA_DIR"] = str(home)
    second = data_versions.prepare_version_data(app, env)
    assert second != first
    assert json.loads((second / "saves/game.json").read_text())["round"] == 7


def test_successful_update_restart_and_next_update_keep_latest_progress(tmp_path):
    home, runtime, app, env = installation(tmp_path)
    first = data_versions.prepare_version_data(app, env)
    (first / "saves/game.json").write_text('{"round":8}', encoding="utf-8")
    (runtime / "current.json").write_text(json.dumps({
        "relative_dir": "docker-versions/v3.0.0", "previous_relative_dir": "docker-versions/v2.6.1",
    }), encoding="utf-8")
    assert data_versions.prepare_version_data(app, env) == first
    app2 = runtime / "docker-versions/v3.1.0/app"
    app2.mkdir(parents=True)
    (app2.parent / "manifest.json").write_text('{"version":"3.1.0","data_mode":"versioned-copy-v1"}')
    env["TRPG_ACTIVE_VERSION_DIR"] = str(app2.parent)
    second = data_versions.prepare_version_data(app2, env)
    assert json.loads((second / "saves/game.json").read_text())["round"] == 8
    (second / "saves/game.json").write_text('{"round":9}', encoding="utf-8")
    (runtime / "current.json").write_text(json.dumps({
        "relative_dir": "docker-versions/v3.1.0", "previous_relative_dir": "docker-versions/v3.0.0",
    }), encoding="utf-8")
    env["TRPG_ACTIVE_VERSION_DIR"] = str(app.parent)
    assert data_versions.prepare_version_data(app, env) == first
    assert json.loads((first / "saves/game.json").read_text())["round"] == 8


def test_missing_committed_data_never_falls_back_to_empty_or_original_data(tmp_path):
    _, runtime, app, env = installation(tmp_path)
    (runtime / "current.json").write_text('{"relative_dir":"docker-versions/v3.0.0"}')
    with pytest.raises(ValueError, match="data"):
        data_versions.prepare_version_data(app, env)


def test_copy_failure_preserves_source_and_never_publishes_incomplete_binding(tmp_path, monkeypatch):
    home, runtime, app, env = installation(tmp_path)
    monkeypatch.setattr(data_versions, "copy_data_tree", lambda *_args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        data_versions.prepare_version_data(app, env)
    assert json.loads((home / "saves/game.json").read_text())["round"] == 7
    assert not list((runtime / "data-bindings").glob("*.json"))


def test_non_managed_source_run_keeps_existing_layout(tmp_path):
    env = {"TRPG_DATA_DIR": str(tmp_path / "data")}
    assert data_versions.prepare_version_data(tmp_path, env) == tmp_path / "data"
    assert "TRPG_DOCKER_DATA_HOME" not in env


def test_upgrading_forward_again_uses_latest_legacy_progress(tmp_path):
    home, runtime, app, env = installation(tmp_path)
    first = data_versions.prepare_version_data(app, env)
    (home / "saves/game.json").write_text('{"instance_schema_version":43,"round":10}')
    (runtime / "current.json").write_text(json.dumps({
        "relative_dir": "docker-versions/v2.6.1", "previous_relative_dir": "docker-versions/v3.0.0",
    }))
    second = data_versions.prepare_version_data(app, env)
    assert second != first
    assert json.loads((second / "saves/game.json").read_text())["round"] == 10


def test_sqlite_snapshot_includes_committed_wal_data(tmp_path):
    home, _, app, env = installation(tmp_path)
    connection = sqlite3.connect(home / "lorebook.db")
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("INSERT INTO books VALUES ('in WAL')")
        connection.commit()
        selected = data_versions.prepare_version_data(app, env)
        with sqlite3.connect(selected / "lorebook.db") as db:
            assert db.execute("SELECT name FROM books ORDER BY rowid").fetchall() == [("original",), ("in WAL",)]
    finally:
        connection.close()


def test_snapshot_binding_cannot_escape_installation(tmp_path):
    _, runtime, app, env = installation(tmp_path)
    data_versions.prepare_version_data(app, env)
    (runtime / "current.json").write_text('{"relative_dir":"docker-versions/v3.0.0"}')
    data_versions.bound_data(runtime, app.parent)
    binding = next((runtime / "data-bindings").glob("*.json"))
    record = json.loads(binding.read_text())
    record["data_dir"] = "../../outside"
    binding.write_text(json.dumps(record))
    (runtime / "current.json").write_text('{"relative_dir":"docker-versions/v3.0.0"}')
    with pytest.raises(ValueError, match="directory"):
        data_versions.prepare_version_data(app, env)


def test_host_configuration_and_session_revocations_remain_shared(tmp_path):
    from src.webui.runtime_config import RuntimePaths

    home, _, app, env = installation(tmp_path)
    selected = data_versions.prepare_version_data(app, env)
    paths = RuntimePaths.from_root(app, env)
    assert paths.data_dir == selected
    assert paths.config_file == home / "config.json"
    assert paths.secrets_file == home / "secrets.json"
    assert not (selected / "config.json").exists()


def test_manual_data_rollback_preserves_schema_and_never_revives_room_credentials(tmp_path):
    from src.compat.program_rollback_access import prepare_rollback_access
    from src.engine.modules.room_access import fresh

    home, _, _, _ = installation(tmp_path)
    slot = fresh()
    slot["seat_credentials"] = {"player": {"hash": "obsolete"}}
    slot["room_tokens"] = [{"hash": "obsolete"}]
    original = {"instance_schema_version": 43, "modules": {"room_access": slot}, "round": 7}
    (home / "saves/game.json").write_text(json.dumps(original))
    prepare_rollback_access(home)
    restored = json.loads((home / "saves/game.json").read_text())
    assert restored["instance_schema_version"] == 43
    assert restored["round"] == 7
    assert restored["modules"]["room_access"]["seat_credentials"] == {}
    assert restored["modules"]["room_access"]["room_tokens"] == []
    assert restored["modules"]["room_access"]["player_access_open"] is False


def test_rollback_sanitation_does_not_rewrite_non_save_metadata(tmp_path):
    from src.compat.program_rollback_access import prepare_rollback_access

    home, _, _, _ = installation(tmp_path)
    metadata = home / "saves/metadata.json"
    metadata.write_text('{"notes":"unchanged"}')
    prepare_rollback_access(home)
    assert json.loads(metadata.read_text()) == {"notes": "unchanged"}


def test_failed_forward_retry_never_replaces_the_previous_committed_snapshot(tmp_path):
    home, runtime, app, env = installation(tmp_path)
    stable = data_versions.prepare_version_data(app, env)
    (stable / "saves/game.json").write_text('{"round":8}')
    (runtime / "current.json").write_text(json.dumps({
        "relative_dir": "docker-versions/v3.0.0", "previous_relative_dir": "docker-versions/v2.6.1",
    }))
    data_versions.prepare_version_data(app, env)
    (runtime / "current.json").write_text(json.dumps({
        "relative_dir": "docker-versions/v2.6.1", "previous_relative_dir": "docker-versions/v3.0.0",
    }))
    candidate = data_versions.prepare_version_data(app, env)
    (candidate / "saves/game.json").write_text('{"round":999}')
    # The retry failed, then the old payload became unreadable. Startup falls
    # back to the previous committed program, not the failed candidate data.
    (runtime / "docker-versions/v2.6.1/manifest.json").unlink()
    assert data_versions.prepare_version_data(app, env) == stable


def test_next_upgrade_can_read_a_committed_snapshot_before_activation_task_promotes_it(tmp_path):
    _, runtime, app, env = installation(tmp_path)
    selected = data_versions.prepare_version_data(app, env)
    (selected / "saves/game.json").write_text('{"round":15}')
    (runtime / "current.json").write_text(json.dumps({
        "relative_dir": "docker-versions/v3.0.0", "previous_relative_dir": "docker-versions/v2.6.1",
    }))
    app2 = runtime / "docker-versions/v3.1.0/app"
    app2.mkdir(parents=True)
    (app2.parent / "manifest.json").write_text('{"version":"3.1.0","data_mode":"versioned-copy-v1"}')
    env["TRPG_ACTIVE_VERSION_DIR"] = str(app2.parent)
    newest = data_versions.prepare_version_data(app2, env)
    assert json.loads((newest / "saves/game.json").read_text())["round"] == 15


def test_successful_commit_prunes_failed_snapshots_but_keeps_legacy_data(tmp_path):
    home, runtime, app, env = installation(tmp_path)
    failed = data_versions.prepare_version_data(app, env)
    current = data_versions.prepare_version_data(app, env)
    (runtime / "current.json").write_text(json.dumps({
        "relative_dir": "docker-versions/v3.0.0", "previous_relative_dir": "docker-versions/v2.6.1",
    }))
    data_versions.bound_data(runtime, app.parent)
    data_versions.prune_retired_data(runtime)
    assert not failed.exists()
    assert current.exists()
    assert (home / "saves/game.json").is_file()


def test_pruning_preserves_files_still_referenced_by_shared_host_settings(tmp_path):
    home, runtime, app, env = installation(tmp_path)
    referenced = data_versions.prepare_version_data(app, env)
    current = data_versions.prepare_version_data(app, env)
    resource = referenced / "reference.wav"
    resource.write_bytes(b"test resource")
    (home / "config.json").write_text(json.dumps({"local_resource": str(resource)}))
    (runtime / "current.json").write_text(json.dumps({
        "relative_dir": "docker-versions/v3.0.0", "previous_relative_dir": "docker-versions/v2.6.1",
    }))
    data_versions.bound_data(runtime, app.parent)
    data_versions.prune_retired_data(runtime)
    assert resource.is_file()
    assert current.exists()
