from src.compat.saves import normalize_save_payload


def test_legacy_dnd_save_projects_known_names_to_canonical_ids_without_rewriting_display():
    payload = {"players": {"p1": {"character_sheet": {"class": "战士", "equipment": [{"name": "长剑"}]}}}}
    normalized = normalize_save_payload(payload)
    sheet = normalized["players"]["p1"]["character_sheet"]
    assert sheet["class_id"] == "fighter"
    assert sheet["equipment"][0]["item_key"] == "longsword"
    assert sheet["equipment"][0]["name"] == "长剑"


def test_npc_sheets_are_normalized_with_the_same_aliases():
    payload = {"npcs": {"n1": {"character_sheet": {"class": "法师", "equipment": [{"name": "匕首"}]}}}}
    sheet = normalize_save_payload(payload)["npcs"]["n1"]["character_sheet"]
    assert sheet["class_id"] == "wizard"
    assert sheet["equipment"][0]["item_key"] == "dagger"


def test_existing_canonical_ids_are_never_overwritten_by_aliases():
    payload = {"players": {"p1": {"character_sheet": {
        "class": "战士",
        "class_id": "custom_multiclass",
        "equipment": [{"name": "长剑", "item_key": "homebrew_blade"}],
    }}}}
    sheet = normalize_save_payload(payload)["players"]["p1"]["character_sheet"]
    assert sheet["class_id"] == "custom_multiclass"
    assert sheet["equipment"][0]["item_key"] == "homebrew_blade"


def test_unknown_names_stay_untouched_without_invented_ids():
    payload = {"players": {"p1": {"character_sheet": {
        "class": "自定义职业",
        "equipment": [{"name": "祖传菜刀"}],
    }}}}
    sheet = normalize_save_payload(payload)["players"]["p1"]["character_sheet"]
    assert "class_id" not in sheet
    assert "item_key" not in sheet["equipment"][0]
    assert sheet["class"] == "自定义职业"
    assert sheet["equipment"][0]["name"] == "祖传菜刀"


def test_actor_dict_without_character_sheet_wrapper_is_normalized_in_place():
    payload = {"players": {"p1": {"class_name": "游侠", "equipment": [{"name": "长弓"}]}}}
    actor = normalize_save_payload(payload)["players"]["p1"]
    assert actor["class_id"] == "ranger"
    assert actor["equipment"][0]["item_key"] == "longbow"


def test_existing_save_schema_version_is_preserved():
    payload = {"save_schema_version": 7, "players": {}}
    assert normalize_save_payload(payload)["save_schema_version"] == 7
    assert normalize_save_payload({"players": {}})["save_schema_version"] == 1


def test_malformed_payload_is_left_untouched_without_error():
    payload = {"players": None, "npcs": {"broken": "not-a-dict", "no_sheet": []}}
    normalized = normalize_save_payload(payload)
    assert normalized["players"] is None
    assert normalized["npcs"]["broken"] == "not-a-dict"
    assert normalized["npcs"]["no_sheet"] == []


def test_alias_lookup_ignores_whitespace_case_and_locale_of_legacy_name():
    payload = {"players": {
        "p1": {"character_sheet": {"class": "  Barbarian "}},
        "p2": {"character_sheet": {"class": "蛮族"}},
        "p3": {"character_sheet": {"equipment": [{"name": " Iron Sword "}]}},
        "p4": {"character_sheet": {"equipment": [{"name": "鉄の剣"}]}},
    }}
    players = normalize_save_payload(payload)["players"]
    assert players["p1"]["character_sheet"]["class_id"] == "barbarian"
    assert players["p2"]["character_sheet"]["class_id"] == "barbarian"
    assert players["p3"]["character_sheet"]["equipment"][0]["item_key"] == "iron_sword"
    assert players["p4"]["character_sheet"]["equipment"][0]["item_key"] == "iron_sword"
