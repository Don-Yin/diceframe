"""Persistent runtime catalogue for bundled and user adventure packages."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path


logger = logging.getLogger("trpg")
BUILTIN_MARKER = ".diceframe-builtin"


def is_builtin_adventure_directory(path: Path) -> bool:
    return (path / BUILTIN_MARKER).is_file()


def _package_snapshot(path: Path) -> list[tuple[str, bytes]]:
    return [
        (item.relative_to(path).as_posix(), item.read_bytes())
        for item in sorted(path.rglob("*"))
        if item.is_file() and item.name != BUILTIN_MARKER
    ]


def sync_adventure_catalog(
    bundled_dir: Path, runtime_dir: Path,
) -> dict[str, int]:
    """Refresh complete bundled packages while preserving user directories."""

    stats = {"copied": 0, "updated": 0, "preserved": 0, "failed": 0}
    runtime_dir.mkdir(parents=True, exist_ok=True)
    if not bundled_dir.is_dir():
        logger.warning("内置冒险包目录不存在: %s", bundled_dir)
        return stats
    for source in sorted(bundled_dir.iterdir()):
        if not source.is_dir() or not (source / "manifest.json").is_file():
            continue
        target = runtime_dir / source.name
        if target.exists() and not is_builtin_adventure_directory(target):
            stats["preserved"] += 1
            logger.warning("用户冒险包与内置目录同名，保留用户版本: %s", target)
            continue
        try:
            if target.exists() and _package_snapshot(source) == _package_snapshot(target):
                continue
            with tempfile.TemporaryDirectory(
                prefix="diceframe-adventure-sync-", dir=runtime_dir.parent,
            ) as temporary:
                staged = Path(temporary) / source.name
                shutil.copytree(source, staged)
                (staged / BUILTIN_MARKER).write_text(
                    json.dumps({"source": source.name}), encoding="utf-8",
                )
                existed = target.exists()
                backup = runtime_dir / f".{source.name}.sync-backup"
                if existed:
                    if backup.exists():
                        shutil.rmtree(backup)
                    target.replace(backup)
                try:
                    shutil.move(str(staged), str(target))
                except Exception:
                    if backup.exists():
                        backup.replace(target)
                    raise
                if backup.exists():
                    shutil.rmtree(backup)
                stats["updated" if existed else "copied"] += 1
        except OSError:
            stats["failed"] += 1
            logger.exception("冒险包同步失败: %s -> %s", source, target)
    return stats
