from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.webui.game_lifecycle_context import (
    CreationPhase,
    CreationTransaction,
)


class _Registry:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self.removed = []
        self.saved = []

    def save_package_state_path(self, _game_key):
        return self.state_path

    def remove(self, game_key):
        self.removed.append(game_key)

    async def save(self, instance):
        self.saved.append(instance)


def _transaction(tmp_path: Path):
    state_path = tmp_path / "save" / "state.json"
    state_path.parent.mkdir()
    state_path.write_text("{}", encoding="utf-8")
    registry = _Registry(state_path)
    cleaned = []
    dependencies = SimpleNamespace(
        registry=registry,
        cleanup_orphan_game_templates=lambda world_id: cleaned.append(world_id),
    )
    return (
        CreationTransaction(dependencies, ("web", "room", "bot"), "world"),
        registry,
        cleaned,
    )


def test_creation_rollback_is_idempotent_and_removes_partial_state(tmp_path):
    transaction, registry, cleaned = _transaction(tmp_path)
    transaction.advance(CreationPhase.INSTANCE_REGISTERED)

    transaction.rollback()
    transaction.rollback()

    assert transaction.phase is CreationPhase.ROLLED_BACK
    assert registry.removed == [("web", "room", "bot")]
    assert cleaned == ["world"]
    assert not (tmp_path / "save").exists()


@pytest.mark.asyncio
async def test_creation_commit_requires_opening_and_disables_compensation(tmp_path):
    transaction, registry, cleaned = _transaction(tmp_path)
    with pytest.raises(RuntimeError, match="cannot commit"):
        await transaction.commit(object())

    transaction.advance(CreationPhase.INSTANCE_REGISTERED)
    transaction.advance(CreationPhase.INSTANCE_CONFIGURED)
    transaction.advance(CreationPhase.PLAYERS_CREATED)
    transaction.advance(CreationPhase.OPENING_STARTED)
    instance = object()
    await transaction.commit(instance)
    transaction.rollback()

    assert transaction.phase is CreationPhase.COMMITTED
    assert registry.saved == [instance]
    assert registry.removed == []
    assert cleaned == []
    assert (tmp_path / "save" / "state.json").exists()
