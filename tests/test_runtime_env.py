from pathlib import Path

from src.runtime_env import load_project_env


def test_load_project_env_reads_values_without_overriding_process_environment(tmp_path, monkeypatch):
    env_file = Path(tmp_path) / ".env"
    env_file.write_text(
        "# comment\n"
        "TRPG_WEB_CORS_ORIGINS=https://diceframe.pages.dev\n"
        "export TRPG_WEB_PORT='10022'\n"
        "EMPTY_VALUE=\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TRPG_WEB_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("TRPG_WEB_PORT", raising=False)
    monkeypatch.delenv("EMPTY_VALUE", raising=False)

    load_project_env(env_file)

    assert __import__("os").environ["TRPG_WEB_CORS_ORIGINS"] == "https://diceframe.pages.dev"
    assert __import__("os").environ["TRPG_WEB_PORT"] == "10022"
    assert __import__("os").environ["EMPTY_VALUE"] == ""


def test_load_project_env_keeps_explicit_environment_value(tmp_path, monkeypatch):
    env_file = Path(tmp_path) / ".env"
    env_file.write_text("TRPG_WEB_CORS_ORIGINS=https://from-file.example\n", encoding="utf-8")
    monkeypatch.setenv("TRPG_WEB_CORS_ORIGINS", "https://from-process.example")

    load_project_env(env_file)

    assert __import__("os").environ["TRPG_WEB_CORS_ORIGINS"] == "https://from-process.example"
