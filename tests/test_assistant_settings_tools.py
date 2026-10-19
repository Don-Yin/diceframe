import pytest

from src.webui.services.assistant_settings_tools import (
    SettingsToolCallbacks,
    build_settings_actions,
    build_settings_tools,
)
from src.webui.services.assistant_agent import validate_arguments


@pytest.fixture
def config():
    return {
        "game_defaults": {"story_mode": "prose"},
        "model": "local-small",
        "assistant_agent_max_tokens": 2048,
        "ai_providers": [{"id": "local", "name": "Local", "base_url": "http://127.0.0.1:8000/v1?api_key=secret&x=ok#token=hidden", "models": ["local-small"]}],
        "llm_provider_ref": "local",
        "ai_provider_key_local": "top-secret",
    }


@pytest.mark.asyncio
async def test_read_settings_is_sanitized_and_provider_catalogue_has_no_credentials(config):
    tools = {tool.name: tool for tool in build_settings_tools(SettingsToolCallbacks(lambda: config))}
    result = await tools["read_settings"].handler({}, "owner")
    assert result["settings"]["ai_providers"][0]["base_url"].startswith("http://")
    assert "secret" not in result["settings"]["ai_providers"][0]["base_url"]
    assert "ai_provider_key_local" not in result["settings"]
    assert "top-secret" not in repr(result)


@pytest.mark.asyncio
async def test_patch_routes_through_owner_validator_and_rejects_legacy_and_unknown(config):
    writes = []
    callbacks = SettingsToolCallbacks(lambda: config, write_config=lambda value: writes.append(value))
    patch = {tool.name: tool for tool in build_settings_tools(callbacks)}["patch_settings"]
    with pytest.raises(ValueError, match="unsupported AI config"):
        await patch.handler({"changes": {"api_key": "inline-secret"}}, "owner")
    with pytest.raises(ValueError, match="unknown settings fields"):
        await patch.handler({"changes": {"made_up_setting": True}}, "owner")
    with pytest.raises(ValueError, match="greater than 0"):
        await patch.handler({"changes": {"assistant_agent_max_tokens": 0}}, "owner")
    await patch.handler({"changes": {"assistant_agent_max_tokens": 4096}}, "owner")
    assert writes[-1]["assistant_agent_max_tokens"] == 4096


@pytest.mark.asyncio
async def test_patch_has_framework_schema_guard_preview_and_preserves_writer_failure(config):
    callbacks = SettingsToolCallbacks(lambda: config, write_config=lambda value: (_ for _ in ()).throw(RuntimeError("disk full")))
    patch = {tool.name: tool for tool in build_settings_tools(callbacks)}["patch_settings"]
    args = {"changes": {"assistant_agent_max_tokens": 4096}}
    validate_arguments(args, patch.schema)
    digest = patch.guard(args, "owner")
    preview = patch.preview(args, "owner")
    assert preview["changed"] == ["assistant_agent_max_tokens"]
    args["expected_config_digest"] = digest
    with pytest.raises(RuntimeError, match="disk full"):
        await patch.handler(args, "owner")
    config["model"] = "changed"
    with pytest.raises(ValueError, match="Settings changed"):
        await patch.handler(args, "owner")


@pytest.mark.asyncio
async def test_failed_writer_result_is_not_reported_as_success(config):
    callbacks = SettingsToolCallbacks(lambda: config, write_config=lambda value: {"ok": False, "error": "rejected"})
    patch = {tool.name: tool for tool in build_settings_tools(callbacks)}["patch_settings"]
    with pytest.raises(ValueError, match="rejected"):
        await patch.handler({"changes": {"model": "next"}}, "owner")


@pytest.mark.asyncio
async def test_plugin_activation_requires_explicit_authorization_and_uses_existing_callback():
    calls = []
    callbacks = SettingsToolCallbacks(
        lambda: {},
        activate_plugin=lambda plugin_id: calls.append(plugin_id) or {"id": plugin_id, "status": "active", "token": "secret"},
        authorize=lambda operation, args, owner: operation == "plugins.activate" and owner == "gm",
    )
    activate = {tool.name: tool for tool in build_settings_tools(callbacks)}["activate_plugin"]
    with pytest.raises(PermissionError):
        await activate.handler({"plugin_id": "safe-pack"}, "guest")
    result = await activate.handler({"plugin_id": "safe-pack"}, "gm")
    assert calls == ["safe-pack"]
    assert "secret" not in repr(result)


def test_actions_have_explicit_domain_and_effect_metadata():
    actions = {item.name: item for item in build_settings_actions(SettingsToolCallbacks(lambda: {}, activate_plugin=lambda _: {"ok": True}))}
    assert actions["patch_settings"].domain == "settings"
    assert actions["patch_settings"].effect == "external"
    assert actions["activate_plugin"].domain == "plugins"
    assert actions["activate_plugin"].effect == "external"
