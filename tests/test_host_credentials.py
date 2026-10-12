"""Host credential startup behavior and migration contracts."""

from __future__ import annotations

from src.webui.access_password import verify_access_password
from src.webui.host_credentials import HostCredentials


def _credentials(tmp_path, state, environ=None):
    saves = []
    credentials = HostCredentials(
        state=state,
        data_dir=tmp_path,
        access_token_file=tmp_path / "access_token.txt",
        environ=dict(environ or {}),
        save_config=lambda: saves.append(dict(state)),
    )
    return credentials, saves


def test_plaintext_access_password_is_hashed_without_changing_password(tmp_path):
    state = {"access_token": "legacy-password"}
    credentials, saves = _credentials(tmp_path, state)

    credentials.initialize_access_password()

    assert verify_access_password("legacy-password", state["access_token"])
    assert saves


def test_reset_file_replaces_password_and_is_consumed(tmp_path):
    state = {"access_token": "old-password"}
    reset_file = tmp_path / "reset_access_password.txt"
    reset_file.write_text("new-password", encoding="utf-8")
    credentials, saves = _credentials(tmp_path, state)

    credentials.initialize_access_password()

    assert verify_access_password("new-password", state["access_token"])
    assert not reset_file.exists()
    assert saves


def test_existing_bot_token_is_not_regenerated_or_saved(tmp_path):
    state = {"bot_token": "existing-token"}
    credentials, saves = _credentials(tmp_path, state)

    token = credentials.ensure_bot_token()

    assert token == "existing-token"
    assert saves == []
