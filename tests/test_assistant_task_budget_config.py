import json

import pytest

from src.assistant_agent_limits import DEFAULT_TASK_MAX_TOKENS, MIN_TASK_MAX_TOKENS, MAX_TASK_MAX_TOKENS
from src.webui.config_update import prepare_config_update
from src.webui.runtime_config import ConfigStore, RuntimePaths
from src.webui.services.assistant_agent import validate_arguments
from src.webui.services.assistant_settings_tools import SettingsToolCallbacks, build_settings_tools


def _store(tmp_path):
    env = {}
    paths = RuntimePaths.from_root(tmp_path, env)
    return ConfigStore(paths, env), paths


def test_task_budget_defaults_without_rewriting_reply_budget(tmp_path):
    store, paths = _store(tmp_path)
    runtime = store.load()
    assert runtime.state["assistant_agent_task_max_tokens"] == DEFAULT_TASK_MAX_TOKENS
    assert runtime.state["assistant_agent_max_tokens"] == 4096
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.config_file.write_text(json.dumps({
        "assistant_agent_max_tokens": 8192,
        "assistant_agent_task_max_tokens": 64000,
    }), encoding="utf-8")
    restored = store.load()
    assert restored.state["assistant_agent_max_tokens"] == 8192
    assert restored.state["assistant_agent_task_max_tokens"] == 64000


@pytest.mark.parametrize("value", [True, 1.5, MIN_TASK_MAX_TOKENS - 1, MAX_TASK_MAX_TOKENS + 1])
def test_config_update_rejects_invalid_task_budget_and_preserves_reply_budget(value):
    current = {"assistant_agent_max_tokens": 4096, "assistant_agent_task_max_tokens": DEFAULT_TASK_MAX_TOKENS}
    prepared = prepare_config_update(current, {
        "assistant_agent_max_tokens": 8192,
        "assistant_agent_task_max_tokens": value,
    })
    assert prepared.error
    assert prepared.state["assistant_agent_max_tokens"] == 8192


def test_settings_tool_enforces_task_budget_range_and_schema():
    config = {"assistant_agent_max_tokens": 4096, "assistant_agent_task_max_tokens": DEFAULT_TASK_MAX_TOKENS}
    patch = {tool.name: tool for tool in build_settings_tools(SettingsToolCallbacks(lambda: config))}["patch_settings"]
    validate_arguments({"changes": {"assistant_agent_task_max_tokens": MIN_TASK_MAX_TOKENS}}, patch.schema)
    with pytest.raises(ValueError, match="between"):
        patch.preview({"changes": {"assistant_agent_task_max_tokens": MAX_TASK_MAX_TOKENS + 1}}, "owner")
    with pytest.raises(ValueError, match="integer"):
        patch.preview({"changes": {"assistant_agent_task_max_tokens": True}}, "owner")
