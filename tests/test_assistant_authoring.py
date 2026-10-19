import pytest
from src.knowledge.visibility import entry_visible_to_viewer
from src.lorebook.store import LorebookStore
from src.webui.services.lorebooks import LorebookDependencies, save_lorebook_entry

from src.webui.services.assistant_authoring import AuthoringDependencies, authoring_tools


def tools(entries, save):
    return {tool.name: tool for tool in authoring_tools(AuthoringDependencies(
        list_worlds=lambda: {"worlds": []}, update_world=lambda *a: {},
        list_book_entries=lambda book: {"ok": True, "entries": entries}, save_book_entry=save,
        list_cards=lambda: {"cards": []}, update_card=lambda *a: {},
        adventure_detail=lambda *a: {}, get_rule=lambda *a: {},
    ))}


@pytest.mark.asyncio
async def test_book_entry_writes_cannot_guess_existing_ids_or_publish_private_markers():
    writes = []
    def save(book, row):
        writes.append((book, row))
        return {"ok": True}
    writer = tools([{"id": "known", "name": "Old"}], save)["write_lorebook_entries"]
    with pytest.raises(ValueError, match="exist"):
        await writer.handler({"book_id": "book", "entries": [{"id": "guessed", "name": "Name", "content": "Text"}]}, "owner")
    with pytest.raises(ValueError, match="private"):
        await writer.handler({"book_id": "book", "entries": [{"name": "Note", "content": "GM: A hidden trap", "visibility": "public"}]}, "owner")
    assert writes == []
    assert writer.mutation
    result = await writer.handler({"book_id": "book", "entries": [
        {"name": "Public", "content": "Harbor", "visibility": "public"},
        {"name": "Hidden", "content": "GM: A hidden trap"}]}, "owner")
    assert result["ok"]
    assert writes[0][1]["visible_to"] == ["*"]
    assert writes[1][1]["visible_to"] == []


@pytest.mark.asyncio
async def test_book_batch_reports_partial_results_and_does_not_hide_owner_failure():
    count = [0]
    def save(book, row):
        count[0] += 1
        return {"ok": count[0] == 1, "error": "cannot save"}
    writer = tools([], save)["write_lorebook_entries"]
    result = await writer.handler({"book_id": "b", "entries": [
        {"name": "One", "content": "First"}, {"name": "Two", "content": "Second"}]}, "owner")
    assert not result["ok"] and result["partial"] and len(result["results"]) == 2


@pytest.mark.asyncio
async def test_existing_public_entry_cannot_receive_gm_text_without_visibility_change():
    writes = []
    writer = tools([{"id": "public", "visible_to": ["*"]}], lambda *args: writes.append(args))["write_lorebook_entries"]
    with pytest.raises(ValueError, match="private"):
        await writer.handler({"book_id": "b", "entries": [{"id": "public", "name": "Note", "content": "GM: Hidden trap"}]}, "owner")
    assert not writes


@pytest.mark.asyncio
async def test_visibility_only_updates_preserve_full_entry_and_support_canonical_characters():
    writes = []
    original = {"id": "e1", "name": "Secret", "content": "A clue", "type": "npc",
                "keywords": ["clue"], "visible_to": [], "extensions": {"x": 1}}
    deps = AuthoringDependencies(
        list_worlds=lambda: {"worlds": []}, update_world=lambda *a: {},
        list_book_entries=lambda book: {"ok": True, "entries": [original]},
        save_book_entry=lambda book, row: writes.append(row) or {"ok": True},
        list_cards=lambda: {"cards": [{"id": "char-a"}, {"id": "char-b"}]},
        update_card=lambda *a: {}, adventure_detail=lambda *a: {}, get_rule=lambda *a: {},
        game_players=lambda game, owner: {"players": {"uid-b": {"character_name": "B"}}},
    )
    tool = {item.name: item for item in authoring_tools(deps)}["set_lorebook_entry_visibility"]
    result = await tool.handler({"book_id": "book", "entry_ids": ["e1"], "game_key": "game",
                                 "audience": "characters", "character_ids": ["uid-b"]}, "owner")
    assert result["ok"]
    assert writes[0]["visible_to"] == ["uid-b"]
    assert writes[0]["content"] == original["content"]
    assert writes[0]["extensions"] == original["extensions"]


@pytest.mark.asyncio
async def test_visibility_only_preflights_all_ids_and_rejects_unknown_characters_or_private_disclosure():
    writes = []
    entries = [{"id": "e1", "name": "A", "content": "Public clue", "visible_to": []},
               {"id": "e2", "name": "B", "content": "GM: hidden clue", "visible_to": []}]
    deps = AuthoringDependencies(
        list_worlds=lambda: {"worlds": []}, update_world=lambda *a: {},
        list_book_entries=lambda book: {"ok": True, "entries": entries},
        save_book_entry=lambda book, row: writes.append(row) or {"ok": True},
        list_cards=lambda: {"cards": [{"id": "char-a"}]},
        update_card=lambda *a: {}, adventure_detail=lambda *a: {}, get_rule=lambda *a: {},
        game_players=lambda game, owner: {"players": {"uid-a": {"character_name": "A"}}},
    )
    tool = {item.name: item for item in authoring_tools(deps)}["set_lorebook_entry_visibility"]
    with pytest.raises(ValueError, match="Unknown"):
        await tool.handler({"book_id": "book", "entry_ids": ["e1"],
                            "game_key": "game", "audience": "characters", "character_ids": ["missing"]}, "owner")
    with pytest.raises(ValueError, match="private"):
        await tool.handler({"book_id": "book", "entry_ids": ["e2"],
                            "audience": "public"}, "owner")
    with pytest.raises(ValueError, match="exist"):
        await tool.handler({"book_id": "book", "entry_ids": ["e1", "missing"],
                            "audience": "gm"}, "owner")
    assert writes == []


@pytest.mark.asyncio
async def test_visibility_only_uses_live_player_uid_and_projection_contract(tmp_path):
    store = LorebookStore(tmp_path / "lorebook.db")
    store.open()
    try:
        store.create_lorebook({"id": "book", "name": "Book", "source_kind": "user"})
        store.add_book_entry("book", {"id": "e1", "name": "Clue", "content": "Clue", "visible_to": []})
        lore_deps = LorebookDependencies(store, lambda _: None, lambda: None)
        deps = AuthoringDependencies(
            list_worlds=lambda: {"worlds": []}, update_world=lambda *a: {},
            list_book_entries=lambda book: {"ok": True, "entries": store.list_book_entries(book)},
            save_book_entry=lambda book, row: save_lorebook_entry(lore_deps, book, row),
            list_cards=lambda: {"cards": []}, update_card=lambda *a: {},
            adventure_detail=lambda *a: {}, get_rule=lambda *a: {},
            game_players=lambda game, owner: {"players": {"uid-live": {"character_name": "Shown Name"}}},
        )
        tool = {item.name: item for item in authoring_tools(deps)}["set_lorebook_entry_visibility"]
        result = await tool.handler({"book_id": "book", "entry_ids": ["e1"], "game_key": "game",
                                     "audience": "characters", "character_ids": ["uid-live"]}, "owner")
        assert result["ok"]
        saved = store.get_book_entry("book", "e1")
        assert entry_visible_to_viewer(saved, "character", uid="uid-live")
        assert not entry_visible_to_viewer(saved, "character", uid="other")
        assert not entry_visible_to_viewer(saved, "character", uid="", name="Shown Name")
    finally:
        store.close()
