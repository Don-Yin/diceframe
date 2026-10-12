"""Preview -> commit -> preview: the plan must recognise the committed Book."""

from __future__ import annotations

import pytest

pytest_plugins = ["tests.webapi_harness"]


def _book(name: str, entries: list[str]) -> dict:
    return {
        "spec": "lorebook_v3",
        "data": {"lorebook": {"name": name, "entries": [
            {"name": title, "content": f"{title} lore", "keys": [title]} for title in entries
        ]}},
    }


@pytest.mark.parametrize("policy, action", [("update", "update"), ("skip", "skip"), ("duplicate", "create")])
def test_reimporting_a_committed_book_is_detected(web_api, policy, action) -> None:
    api, _lorebook, _registry, _llm, _worlds_dir = web_api
    payload = _book("Ashen Atlas", ["Town", "Keep"])

    first = api.preview_lorebook_import(payload)
    assert [op["action"] for op in first["commit_plan"]["operations"]] == ["create"]
    assert api.commit_lorebook_import(payload)["ok"] is True

    again = api.preview_lorebook_import({**payload, "duplicate_policy": policy})
    operations = again["commit_plan"]["operations"]
    assert [op["action"] for op in operations] == [action]
    assert operations[0]["existing_ref"]["id"] == operations[0]["draft_ref"]["id"]


def test_a_different_book_is_not_mistaken_for_the_committed_one(web_api) -> None:
    api, _lorebook, _registry, _llm, _worlds_dir = web_api
    assert api.commit_lorebook_import(_book("Ashen Atlas", ["Town"]))["ok"] is True

    other = api.preview_lorebook_import(_book("Frost Saga", ["Glacier"]))
    assert [op["action"] for op in other["commit_plan"]["operations"]] == ["create"]
    assert other["commit_plan"]["operations"][0]["existing_ref"] is None
