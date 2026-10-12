from __future__ import annotations

import json
from pathlib import Path

from src.lorebook.bootstrap import seed_builtin_worlds


ROOT = Path(__file__).resolve().parents[1]


def test_freeform_sandbox_is_blank_and_legacy_tavern_is_hidden():
    sandbox = json.loads((ROOT / "templates/worlds/freeform_sandbox.json").read_text(encoding="utf-8"))
    legacy = json.loads((ROOT / "templates/worlds/tavern_generic.json").read_text(encoding="utf-8"))

    assert sandbox["sandbox"] is True
    assert sandbox["world_setting"] == ""
    assert sandbox["starter_scene"] == ""
    assert sandbox["starter_lorebook"] == []
    assert sandbox["default_rule"] == "tavern_free"
    assert legacy["deprecated"] is True


def test_deprecated_world_is_not_seeded(tmp_path: Path):
    (tmp_path / "legacy.json").write_text(json.dumps({
        "world_id": "legacy",
        "deprecated": True,
        "starter_lorebook": [{"id": "entry", "name": "Old"}],
    }), encoding="utf-8")

    class Store:
        def get_world(self, world_id):
            return None

        def create_world(self, *args, **kwargs):
            raise AssertionError("deprecated templates must not be seeded")

    assert seed_builtin_worlds(Store(), tmp_path) == 0
