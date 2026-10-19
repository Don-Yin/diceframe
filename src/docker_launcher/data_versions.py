"""Version-bound game data for updates, including unmodified runtime-1 launchers.

Only the candidate's private copy is migrated. Host credentials/configuration and
TLS remain shared so rollback never resurrects revoked sessions or old passwords.
This module runs before application imports and uses only the standard library.
"""

from __future__ import annotations

import asyncio
from contextlib import closing
import hashlib
import json
import os
import shutil
import sqlite3
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from uuid import uuid4

from .contracts import VERSIONED_DATA_MODE, atomic_json, version_key

DATA_MODE = VERSIONED_DATA_MODE
SHARED_ENTRIES = frozenset({
    "_updater", "config.json", "secrets.json", "access_token.txt",
    "reset_access_password.txt", "sessions.json", "paired_devices.json",
    "server_identity.json", "login_audit.json", "certs", "logs",
})
_MARKER = ".diceframe-data.json"


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"update data record is missing or invalid: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError("update data record must be an object")
    return value


def _payload(runtime: Path, relative: str) -> Path:
    path = (runtime / relative).resolve()
    if not relative or path.parent != (runtime / "docker-versions").resolve():
        raise ValueError("update data payload path is invalid")
    return path


def _binding_path(runtime: Path, payload: Path) -> Path:
    key = hashlib.sha256(payload.relative_to(runtime).as_posix().encode()).hexdigest()
    return runtime / "data-bindings" / f"{key}.json"


def _pending_path(runtime: Path, payload: Path) -> Path:
    return runtime / "data-pending" / _binding_path(runtime, payload).name


def _binding_data(runtime: Path, payload: Path, path: Path) -> Path:
    record = _read(path)
    if record.get("schema") != 1 or record.get("payload") != payload.relative_to(runtime).as_posix():
        raise ValueError("update data binding identity is invalid")
    selected = (runtime / str(record.get("data_dir") or "")).resolve()
    if selected.parent != (runtime / "data-versions").resolve() or not selected.is_dir():
        raise ValueError("update data binding directory is invalid")
    if _read(selected / _MARKER) != {"schema": 1, "payload": record["payload"], "id": record.get("id")}:
        raise ValueError("update data binding marker is invalid")
    return selected


def finalize_binding(runtime: Path, payload: Path, expected_data: Path | None = None) -> None:
    pending = _pending_path(runtime, payload)
    if not pending.exists():
        return
    pointer = _read(runtime / "current.json") if (runtime / "current.json").exists() else {}
    if pointer.get("relative_dir") != payload.relative_to(runtime).as_posix():
        return
    selected = _binding_data(runtime, payload, pending)
    if expected_data is not None:
        if selected != expected_data.resolve():
            return
    elif _binding_path(runtime, payload).exists():
        if _read(pending).get("source_payload") != pointer.get("previous_relative_dir"):
            return
    os.replace(pending, _binding_path(runtime, payload))


def bound_data(runtime: Path, payload: Path, *, allow_pending: bool = False) -> Path:
    if allow_pending and _pending_path(runtime, payload).exists():
        return _binding_data(runtime, payload, _pending_path(runtime, payload))
    finalize_binding(runtime, payload)
    return _binding_data(runtime, payload, _binding_path(runtime, payload))


def data_for_payload(runtime: Path, home: Path, payload: Path) -> Path:
    if _binding_path(runtime, payload).exists() or _pending_path(runtime, payload).exists():
        return bound_data(runtime, payload)
    manifest_path = payload / "manifest.json"
    if not manifest_path.exists() or _read(manifest_path).get("data_mode") == DATA_MODE:
        raise ValueError("committed version has no valid data binding")
    return home


def copy_data_tree(source: Path, target: Path) -> None:
    """Copy quiescent business files; snapshot SQLite including committed WAL."""
    for directory, names, files in os.walk(source, followlinks=False):
        parent = Path(directory)
        if parent == source:
            names[:] = [name for name in names if name not in SHARED_ENTRIES]
            files = [name for name in files if name not in SHARED_ENTRIES and name != _MARKER]
        for name in names:
            path = parent / name
            if path.is_symlink():
                raise ValueError("update data contains a symbolic link; snapshot refused")
            (target / path.relative_to(source)).mkdir(parents=True, exist_ok=True)
        for name in sorted(files):
            path = parent / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("update data contains an unsupported filesystem entry")
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if name.endswith(("-wal", "-shm", "-journal")):
                database = path.with_name(name.rsplit("-", 1)[0])
                if database.is_file():
                    with database.open("rb") as stream:
                        if stream.read(16) == b"SQLite format 3\x00":
                            continue
            with path.open("rb") as stream:
                sqlite_file = stream.read(16) == b"SQLite format 3\x00"
            if sqlite_file:
                with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as original:
                    with closing(sqlite3.connect(destination)) as copied:
                        original.backup(copied)
                        if copied.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                            raise ValueError("update data SQLite snapshot integrity check failed")
                shutil.copystat(path, destination)
            else:
                shutil.copy2(path, destination)


def prepare_version_data(app_dir: Path, environ: MutableMapping[str, str]) -> Path:
    existing = Path(environ.get("TRPG_DATA_DIR") or app_dir / "data")
    if environ.get("TRPG_INSTALL_MODE") != "docker-managed":
        return existing
    home = Path(environ.get("TRPG_DOCKER_DATA_HOME") or existing).resolve()
    runtime = Path(environ.get("TRPG_DOCKER_RUNTIME_ROOT") or home / "_updater").resolve()
    if runtime != home / "_updater":
        raise ValueError("update data runtime must belong to the installation data directory")
    payload = app_dir.resolve().parent
    if payload != _payload(runtime, payload.relative_to(runtime).as_posix()):
        raise ValueError("update data entrypoint is outside the selected payload")
    active = environ.get("TRPG_ACTIVE_VERSION_DIR")
    if active and Path(active).resolve() != payload:
        raise ValueError("update data entrypoint does not match the active payload")
    if _read(payload / "manifest.json").get("data_mode") != DATA_MODE:
        return existing
    pointer_path = runtime / "current.json"
    pointer = _read(pointer_path) if pointer_path.exists() else {}
    current = _payload(runtime, str(pointer["relative_dir"])) if pointer.get("relative_dir") else None
    previous = _payload(runtime, str(pointer["previous_relative_dir"])) if pointer.get("previous_relative_dir") else None
    reuse = payload == current
    if payload == previous:
        if not current or not (current / "manifest.json").is_file():
            reuse = True
        else:
            reuse = version_key(_read(payload / "manifest.json")["version"]) < version_key(_read(current / "manifest.json")["version"])
    if reuse:
        selected = bound_data(runtime, payload)
    else:
        source = data_for_payload(runtime, home, current) if current else home
        snapshots = runtime / "data-versions"
        bindings = runtime / "data-bindings"
        (runtime / "data-pending").mkdir(mode=0o700, parents=True, exist_ok=True)
        snapshots.mkdir(mode=0o700, parents=True, exist_ok=True)
        bindings.mkdir(mode=0o700, parents=True, exist_ok=True)
        identity = uuid4().hex
        selected = snapshots / identity
        selected.mkdir(mode=0o700)
        try:
            copy_data_tree(source, selected)
            relative_payload = payload.relative_to(runtime).as_posix()
            marker = {"schema": 1, "payload": relative_payload, "id": identity}
            atomic_json(selected / _MARKER, marker)
            atomic_json(_pending_path(runtime, payload), {
                **marker, "data_dir": selected.relative_to(runtime).as_posix(),
                "source_payload": current.relative_to(runtime).as_posix() if current else "legacy-root",
            })
        except BaseException:
            # This is a newly allocated child of the verified snapshot root.
            if selected.resolve().parent == snapshots.resolve():
                shutil.rmtree(selected, ignore_errors=True)
            raise
    environ["TRPG_DATA_DIR"] = str(selected)
    environ["TRPG_DOCKER_DATA_HOME"] = str(home)
    return selected


def runtime_for_data(data_dir: Path, environ: Mapping[str, str]) -> Path | None:
    if environ.get("TRPG_INSTALL_MODE") != "docker-managed" or not environ.get("TRPG_DOCKER_DATA_HOME"):
        return None
    home = Path(environ["TRPG_DOCKER_DATA_HOME"]).resolve()
    runtime = Path(environ.get("TRPG_DOCKER_RUNTIME_ROOT") or "").resolve()
    if runtime != home / "_updater":
        raise ValueError("update data runtime directory is invalid")
    active = _payload(runtime, Path(environ.get("TRPG_ACTIVE_VERSION_DIR") or "").resolve().relative_to(runtime).as_posix())
    if bound_data(runtime, active, allow_pending=activation_pending(environ)) != data_dir.resolve():
        raise ValueError("update data directory does not match the active payload")
    return runtime


def activation_pending(environ: Mapping[str, str]) -> bool:
    if not environ.get("TRPG_DOCKER_DATA_HOME"):
        return False
    runtime = Path(environ["TRPG_DOCKER_RUNTIME_ROOT"]).resolve()
    pointer = _read(runtime / "current.json") if (runtime / "current.json").exists() else {}
    relative = pointer.get("relative_dir")
    return not relative or _payload(runtime, str(relative)) != Path(environ["TRPG_ACTIVE_VERSION_DIR"]).resolve()


async def wait_for_activation(environ: Mapping[str, str]) -> None:
    while activation_pending(environ):
        await asyncio.sleep(0.25)
    if environ.get("TRPG_DOCKER_DATA_HOME"):
        runtime = Path(environ["TRPG_DOCKER_RUNTIME_ROOT"]).resolve()
        payload = Path(environ["TRPG_ACTIVE_VERSION_DIR"]).resolve()
        finalize_binding(runtime, payload, Path(environ["TRPG_DATA_DIR"]))


def prune_retired_data(runtime: Path) -> None:
    """Retain current/previous pairs; never delete legacy installation data."""
    pointer = _read(runtime / "current.json")
    keep = set()
    for key in ("relative_dir", "previous_relative_dir"):
        relative = pointer.get(key)
        if not relative:
            continue
        payload = _payload(runtime, str(relative))
        if _binding_path(runtime, payload).exists() or _pending_path(runtime, payload).exists():
            keep.add(bound_data(runtime, payload))
    snapshots = runtime / "data-versions"

    def retain_local_references(value) -> None:
        if isinstance(value, dict):
            for item in value.values():
                retain_local_references(item)
        elif isinstance(value, list):
            for item in value:
                retain_local_references(item)
        elif isinstance(value, str) and Path(value).is_absolute():
            referenced = Path(value).resolve()
            if referenced.is_relative_to(snapshots.resolve()):
                relative = referenced.relative_to(snapshots.resolve())
                if relative.parts:
                    keep.add(snapshots / relative.parts[0])

    for name in ("config.json", "secrets.json"):
        source = runtime.parent / name
        if source.exists():
            retain_local_references(_read(source))
    retired_files = []
    retired_dirs = set()
    for directory in (runtime / "data-bindings", runtime / "data-pending"):
        for file in directory.glob("*.json"):
            record = _read(file)
            payload = _payload(runtime, str(record.get("payload") or ""))
            if file.name != _binding_path(runtime, payload).name:
                raise ValueError("retired update data binding identity is invalid")
            selected = _binding_data(runtime, payload, file)
            if selected not in keep:
                retired_dirs.add(selected)
                retired_files.append(file)
    for selected in snapshots.iterdir() if snapshots.is_dir() else ():
        if selected.resolve() in keep or not (selected / _MARKER).is_file():
            continue
        marker = _read(selected / _MARKER)
        if selected.resolve().parent != snapshots.resolve() or marker.get("schema") != 1 or marker.get("id") != selected.name:
            raise ValueError("orphan update data snapshot identity is invalid")
        _payload(runtime, str(marker.get("payload") or ""))
        retired_dirs.add(selected.resolve())
    # All paths and identities are verified before deleting any snapshot.
    for selected in retired_dirs:
        shutil.rmtree(selected)
    for file in retired_files:
        file.unlink()
