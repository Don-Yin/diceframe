"""Stable boundary for legacy save directory naming."""

from __future__ import annotations

from pathlib import Path

def save_path(registry: object, game_key: tuple) -> Path:
    """Resolve the canonical safe path shared by current and legacy loaders."""
    parts = [str(item) for item in game_key]
    if any(not part or "/" in part or "\\" in part or part in {".", ".."} for part in parts):
        raise ValueError(f"非法 game_key 存档路径: {game_key}")
    separator = str(getattr(registry, "_KEY_SEPARATOR", "__"))
    path = registry.save_dir / separator.join(parts) / "state.json"  # type: ignore[attr-defined]
    base = registry.save_dir.resolve()  # type: ignore[attr-defined]
    parent = path.parent.resolve()
    if base != parent and base not in parent.parents:
        raise ValueError(f"非法 game_key 存档路径: {game_key}")
    return path


def legacy_save_paths(registry: object, game_key: tuple) -> tuple[Path, ...]:
    parts = [str(item) for item in game_key]
    return tuple(registry.save_dir / separator.join(parts) / "state.json" for separator in (",", "|"))  # type: ignore[attr-defined]
