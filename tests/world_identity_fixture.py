"""Shared legacy-world fixture for identity migration tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.engine.game_instance import GameInstance
from src.lorebook.store import SCHEMA
from src.migrations.lorebook import migrate


OLD_WORLD_ID = "ai_旧版世界：测试"
WORLD_NAME = "旧版世界：测试"


def _make_fixture(root: Path) -> None:
    (root / "templates" / "worlds").mkdir(parents=True)
    (root / "saves" / f"web#{OLD_WORLD_ID}_1#web_bot").mkdir(parents=True)
    (root / "saves" / f"web#{OLD_WORLD_ID}_2#web_bot").mkdir(parents=True)

    entries = [
        {"id": f"entry-{index}", "name": f"条目 {index}", "content": f"内容 {index}"}
        for index in range(20)
    ]
    template = {
        "world_id": OLD_WORLD_ID,
        "world_name": WORLD_NAME,
        "description": "display text stays unchanged",
        "starter_lorebook": entries,
    }
    (root / "templates" / "worlds" / f"{OLD_WORLD_ID}.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    conn = sqlite3.connect(root / "lorebook.db")
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO worlds(id, name) VALUES (?, ?)", (OLD_WORLD_ID, WORLD_NAME))
    for entry in entries:
        conn.execute(
            "INSERT INTO lorebook_entries(id, world_id, name, content) VALUES (?, ?, ?, ?)",
            (entry["id"], OLD_WORLD_ID, entry["name"], entry["content"]),
        )
    conn.commit()
    migrate(conn, upto=4)
    conn.commit()
    conn.close()

    for index, folder in enumerate(sorted((root / "saves").iterdir()), start=1):
        instance = GameInstance(
            game_key=tuple(folder.name.split('#')),
            world_id=OLD_WORLD_ID,
            world_name=WORLD_NAME,
        )
        instance.put_player('alice', {'user_id': 'alice', 'character_name': 'Alice',
                            'character_sheet': {'hp': 10, 'max_hp': 10, 'sanity': 40, 'max_sanity': 99}})
        state = instance.to_dict()
        state["world_id"] = OLD_WORLD_ID
        state["world_name"] = WORLD_NAME
        state["chatlog_marker"] = {"keep": "chat and character data"}
        state["modules"] = {
            "content_binding": {
                "schema_version": 1,
                "world_ref": {
                    "source_kind": "world", "source_id": OLD_WORLD_ID,
                    "kind": "world", "id": OLD_WORLD_ID, "digest": "",
                },
                "book_ref": {
                    "source_kind": "world", "source_id": OLD_WORLD_ID,
                    "kind": "lorebook", "id": f"world:{OLD_WORLD_ID}", "digest": "",
                },
                "book_refs": [{
                    "source_kind": "world", "source_id": OLD_WORLD_ID,
                    "kind": "lorebook", "id": f"world:{OLD_WORLD_ID}", "digest": "",
                }],
            }
        }
        (folder / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        (folder / "state.backup.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
