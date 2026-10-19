"""Real old-launcher process tests: a new data format must never touch old data."""

import json
import shutil
import socket
import sqlite3
from pathlib import Path

import pytest

from scripts.build_docker_update import write_manifest
from tests.fixtures.docker_runtime_v1 import contracts as old_contract
from tests.fixtures.docker_runtime_v1.launcher import DockerLauncher as OldLauncher
from tests.test_docker_version_data import installation


def payload(root: Path, version: str, *, versioned: bool, crash: bool = False) -> Path:
    directory = root / "docker-versions" / f"v{version}"
    app = directory / "app"
    (app / "src").mkdir(parents=True, exist_ok=True)
    (app / "static-v2").mkdir(exist_ok=True)
    (directory / "runtime/site-packages").mkdir(parents=True, exist_ok=True)
    (directory / "runtime/site-packages/placeholder").touch()
    (app / "src/version.py").write_text(f'__version__ = "{version}"')
    (app / "static-v2/index.html").write_text("test")
    if versioned:
        source = Path(__file__).parents[1] / "src/docker_launcher"
        shutil.copytree(source, app / "src/docker_launcher", ignore=shutil.ignore_patterns("__pycache__"))
        write_manifest(directory, version, "test")
    else:
        manifest = {
            "schema": 1, "version": version, "platform": "linux-amd64", "python_abi": "cp311",
            "launcher_schema_min": 1, "runtime_api": 1, "data_rollback_safe": True,
            "entrypoint": "app/web_server.py", "site_packages": "runtime/site-packages",
            "health_path": "/api/system/update/health", "probation_seconds": 0,
        }
        (directory / "manifest.json").write_text(json.dumps(manifest))
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["probation_seconds"] = 0
    (directory / "manifest.json").write_text(json.dumps(manifest))
    script = '''import json, os, sqlite3
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
'''
    if versioned:
        script += '''from src.docker_launcher.data_versions import prepare_version_data
prepare_version_data(Path(__file__).parent, os.environ)
'''
    script += '''data=Path(os.environ['TRPG_DATA_DIR'])
with sqlite3.connect(data/'lorebook.db') as db:
'''
    if versioned:
        script += "    db.execute('PRAGMA user_version=12')\n    db.execute(\"UPDATE books SET name='new'\")\n"
        script += "(data/'saves/game.json').write_text('{\"instance_schema_version\":44,\"round\":8}')\n"
        if crash:
            script += "os._exit(17)\n"
    else:
        script += "    assert db.execute('PRAGMA user_version').fetchone()[0] == 11\n"
        script += "assert json.loads((data/'saves/game.json').read_text())['instance_schema_version'] == 43\n"
    script += f'''class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body=json.dumps({{"ok":True,"version":"{version}","data_dir":str(data)}}).encode()
        self.send_response(200)
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self,*args): pass
HTTPServer(('127.0.0.1',int(os.environ['TRPG_WEB_PORT'])),Handler).serve_forever()
'''
    (app / "web_server.py").write_text(script, encoding="utf-8")
    return directory


@pytest.fixture
def old_install(tmp_path, monkeypatch):
    home, runtime, _, env = installation(tmp_path)
    monkeypatch.setenv("TRPG_DATA_DIR", str(home))
    monkeypatch.delenv("TRPG_DOCKER_DATA_HOME", raising=False)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    monkeypatch.setenv("TRPG_WEB_PORT", str(port))
    old = payload(runtime, "2.6.1", versioned=False)
    launcher = OldLauncher(runtime, tmp_path / "seed.zip", tmp_path / "seed.sha256",
                           port=port, startup_timeout=2, poll_interval=0.02, data_dir=home)
    launcher._commit(old, None)
    yield home, runtime, old, launcher
    launcher._stop_child(timeout=2)


def test_actual_runtime_1_accepts_new_versioned_data_manifest(tmp_path):
    write_manifest(tmp_path, "3.0.0", "test")
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert old_contract.validate_manifest(manifest)["runtime_api"] == 1


def test_old_launcher_successfully_upgrades_and_can_restore_old_program_and_data(old_install):
    home, runtime, old, launcher = old_install
    new = payload(runtime, "3.0.0", versioned=True)
    assert launcher._launch_candidate(new, old) is True
    pointer = json.loads(launcher.current_file.read_text())
    assert pointer["version"] == "3.0.0"
    with sqlite3.connect(home / "lorebook.db") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 11
    assert launcher._launch_candidate(old, new) is True
    assert json.loads(launcher.current_file.read_text())["version"] == "2.6.1"
    assert json.loads((home / "saves/game.json").read_text())["round"] == 7
    assert launcher._launch_candidate(new, old) is True


def test_unclean_failure_after_migration_automatically_restarts_old_readable_data(old_install):
    home, runtime, old, launcher = old_install
    new = payload(runtime, "3.0.0", versioned=True, crash=True)
    assert launcher._launch_candidate(new, old) is False
    assert launcher.child is not None and launcher.child.poll() is None
    assert json.loads(launcher.state_file.read_text())["state"] == "rolled-back"
    assert json.loads(launcher.current_file.read_text())["version"] == "2.6.1"
    with sqlite3.connect(home / "lorebook.db") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 11
        assert db.execute("SELECT name FROM books").fetchone()[0] == "original"


@pytest.mark.asyncio
async def test_new_updater_uses_shared_control_and_old_launcher_restores_the_pair(old_install, monkeypatch):
    from types import SimpleNamespace
    from src.docker_launcher.data_versions import bound_data
    from src.webui.services.updater import UpdaterDependencies, UpdaterService

    home, runtime, old, launcher = old_install
    new = payload(runtime, "3.0.0", versioned=True)
    assert launcher._launch_candidate(new, old) is True
    data = bound_data(runtime, new)
    monkeypatch.setenv("TRPG_INSTALL_MODE", "docker-managed")
    monkeypatch.setenv("TRPG_DOCKER_DATA_HOME", str(home))
    monkeypatch.setenv("TRPG_DOCKER_RUNTIME_ROOT", str(runtime))
    monkeypatch.setenv("TRPG_ACTIVE_VERSION_DIR", str(new))

    async def check():
        return {"ok": False}

    service = UpdaterService(UpdaterDependencies(data, new / "app", SimpleNamespace(), check))
    assert service._dir == runtime
    assert service.get_rollback_status()["restores_data"] is True
    result = await service.rollback_update()
    assert result["ok"] is True
    launcher._handle_restart_signal()
    assert json.loads(launcher.current_file.read_text())["version"] == "2.6.1"
    assert json.loads((home / "saves/game.json").read_text())["instance_schema_version"] == 43
