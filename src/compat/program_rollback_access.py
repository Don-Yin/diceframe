"""Prevent data rollback from reviving previously revoked room credentials."""

from __future__ import annotations

import json
from pathlib import Path

from src.docker_launcher.contracts import atomic_json
from src.engine.modules.room_access import scrub_access_credentials


def prepare_rollback_access(data_dir: Path) -> None:
    saves = data_dir / "saves"
    if not saves.exists():
        return
    if saves.resolve() != data_dir.resolve() / "saves":
        raise ValueError("rollback save directory is outside its data snapshot")
    plan = []
    for path in saves.rglob("*.json"):
        if path.is_symlink() or not path.resolve().is_relative_to(saves.resolve()):
            raise ValueError("rollback save path is outside its data snapshot")
        payload = json.loads(path.read_bytes())
        if not isinstance(payload, dict):
            raise ValueError("rollback save payload must be an object")
        if "instance_schema_version" not in payload and "game_key" not in payload:
            continue
        scrub_access_credentials(payload, close_entrance=True)
        plan.append((path, payload))
    for path, payload in plan:
        atomic_json(path, payload)
