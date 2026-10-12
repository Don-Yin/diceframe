"""世界模板读取 helper。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.content.worlds import load_world_template as _load_content_world


def world_template_path(worlds_dir: str | Path, world_id: str) -> Path:
    """按 world_id 构造世界模板路径。"""
    return Path(worlds_dir) / f"{world_id}.json"


def load_world_template(worlds_dir: str | Path, world_id: str, locale: str = "") -> dict[str, Any] | None:
    """加载 V2 世界模板，旧 V1 文件由同一入口透明回退。"""
    return _load_content_world(worlds_dir, world_id, locale)
