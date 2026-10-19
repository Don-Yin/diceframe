"""Architecture contracts for play modes and their bot surface declaration.

轨道 P0（ADR-0007 §2 / §6）守卫：

- 玩法模式的 transport 能力是模式模块里的一份数据声明（``MODE_BOT_SURFACES``），
  绑定准入（``bot_access.verify_bind_game``）是唯一执行点；bot bridge 与平台
  插件不得引用具体玩法、``play_mode`` 或模式注册表。
- 具体玩法字面量（``gal``）只允许出现在模式模块与创建校验里，generic path
  不得出现具体玩法分支。
- 每个已知模式必须声明合法 bot surface；未知模式 fail closed 为 ``none``。
"""

from __future__ import annotations

import re
from pathlib import Path

from src.engine.modules import adventure_runtime_state

ROOT = Path(__file__).resolve().parents[2]
_GAL_TOKEN = re.compile(r"\bgal\b")


def _py_sources(*roots: Path):
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            yield path


def test_every_play_mode_declares_a_valid_bot_surface() -> None:
    assert set(adventure_runtime_state.MODE_BOT_SURFACES) == set(adventure_runtime_state.PLAY_MODES)
    assert set(adventure_runtime_state.MODE_BOT_SURFACES.values()) <= set(
        adventure_runtime_state.BOT_SURFACES
    )
    assert adventure_runtime_state.bot_surface("gal") == adventure_runtime_state.BOT_SURFACE_READ_ONLY
    assert adventure_runtime_state.bot_surface("") == adventure_runtime_state.BOT_SURFACE_NONE
    assert adventure_runtime_state.bot_surface("werewolf") == adventure_runtime_state.BOT_SURFACE_NONE


def test_transports_do_not_reference_play_modes() -> None:
    offenders: list[Path] = []
    for path in _py_sources(ROOT / "src" / "bots", ROOT / "plugins"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "play_mode" in text or "adventure_runtime_state" in text or _GAL_TOKEN.search(text):
            offenders.append(path.relative_to(ROOT))
    assert not offenders


def test_specific_mode_literals_stay_in_the_mode_module_and_creation() -> None:
    allowed = {
        (ROOT / "src" / "engine" / "modules" / "adventure_runtime_state.py").resolve(),
        (ROOT / "src" / "webui" / "services" / "game_lifecycle.py").resolve(),
    }
    offenders: list[Path] = []
    for path in _py_sources(ROOT / "src"):
        if path.resolve() in allowed:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _GAL_TOKEN.search(text):
            offenders.append(path.relative_to(ROOT))
    assert not offenders
