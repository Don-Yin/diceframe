"""插件沙箱与权限边界测试（自 test_plugin_host 拆分）。"""

from __future__ import annotations

import io
import json
import textwrap
import zipfile
import base64

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from src.plugin_host import PluginHost
from src.plugin_host.runtime_protocol import PluginInvocationError, PluginProtocolError
from src.rules.rule_system import RuleSystem
from src.webui.services import content_pack_maps as content_pack_map_service
from src.webui.services import maps as map_service
from src.webui.services import plugins as plugin_service
from src.webui.services import rules as rule_service
from src.webui.services import worlds as world_service


from plugin_host_common import write_plugin, write_png, make_plugin_zip


def _write_provider_env_observer(plugin_dir: Path) -> None:
    """写入一个最小合法 provider，通过其实际进程记录收到的环境。"""
    (plugin_dir / "main.py").write_text(textwrap.dedent('''
        import json
        import os
        import sys
        from pathlib import Path

        data_dir = Path(os.environ["DICEFRAME_PLUGIN_DATA_DIR"])
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "observed-env.json").write_text(json.dumps({
            key: os.environ.get(key) for key in (
                "DF_IMAGEGEN_BASE_URL",
                "DF_IMAGEGEN_API_KEY",
                "DF_IMAGEGEN_API_FORMAT",
            )
        }), encoding="utf-8")
        for line in sys.stdin:
            request = json.loads(line)
            result = {
                "protocol_version": 1,
                "capabilities": [{
                    "kind": "text-transform",
                    "version": 1,
                    "methods": {"generate": "provider.text-transform.generate"},
                }],
            }
            print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
    '''), encoding="utf-8")


def test_invalid_manifest_isolated_from_other_plugins(tmp_path):
    plugins = tmp_path / "plugins"
    write_plugin(plugins, "good")
    bad = plugins / "bad"
    bad.mkdir(parents=True)
    (bad / "plugin.json").write_text("{}", encoding="utf-8")
    host = PluginHost(plugins, tmp_path / "data")

    found = host.discover()

    assert next(item for item in found if item["id"] == "good")["status"] == "disabled"
    assert next(item for item in found if item["id"] == "bad")["status"] == "failed"


def test_unknown_plugin_type_is_rejected_but_isolated(tmp_path):
    plugins = tmp_path / "plugins"
    write_plugin(plugins, "good")
    write_plugin(plugins, "weird", plugin_type="unknown-kind")
    host = PluginHost(plugins, tmp_path / "data")

    found = host.discover()

    assert next(item for item in found if item["id"] == "good")["status"] == "disabled"
    bad = next(item for item in found if item["id"] == "weird")
    assert bad["status"] == "failed"
    assert "不支持的 plugin_type" in bad["error"]


def test_missing_plugin_type_is_rejected(tmp_path):
    plugins = tmp_path / "plugins"
    write_plugin(plugins, "missing-type", plugin_type=None)
    host = PluginHost(plugins, tmp_path / "data")

    found = host.discover()

    bad = found[0]
    assert bad["status"] == "failed"
    assert "不支持的 plugin_type" in bad["error"]


@pytest.mark.asyncio
async def test_tool_plugin_with_invalid_handshake_fails_closed(tmp_path):
    plugins = tmp_path / "plugins"
    write_plugin(
        plugins,
        "bad-tool",
        plugin_type="tool",
        manifest_extra={"entrypoint": ["{python}", "{plugin_dir}/main.py"]},
    )
    (plugins / "bad-tool" / "main.py").write_text(
        "import sys\nfor line in sys.stdin:\n print('not-json', flush=True)\n",
        encoding="utf-8",
    )
    host = PluginHost(plugins, tmp_path / "data")
    host.discover()

    detail = await host.update_config("bad-tool", {"enabled": True})

    assert detail["status"] == "failed"
    assert "stdout 只能输出协议消息" in detail["error"]
    assert detail["running"] is False
    assert host.list_tools() == []


def test_bot_extension_requires_extend_permission_when_explicit(tmp_path):
    plugins = tmp_path / "plugins"
    write_plugin(
        plugins,
        "under-declared-bridge",
        plugin_type="bot-extension",
        manifest_extra={"permissions": ["process.spawn", "plugin.data"]},
    )
    host = PluginHost(plugins, tmp_path / "data")

    detail = host.discover()[0]

    assert detail["status"] == "failed"
    assert "bot.extend" in detail["error"]


def test_tool_plugin_requires_execute_permission_when_permissions_are_explicit(tmp_path):
    plugins = tmp_path / "plugins"
    write_plugin(
        plugins,
        "under-declared-tool",
        plugin_type="tool",
        manifest_extra={"permissions": ["process.spawn", "plugin.data"]},
    )
    host = PluginHost(plugins, tmp_path / "data")

    detail = host.discover()[0]

    assert detail["status"] == "failed"
    assert "tool.execute" in detail["error"]


@pytest.mark.asyncio
async def test_process_environment_does_not_inherit_unrelated_host_secrets(tmp_path, monkeypatch):
    plugins = tmp_path / "plugins"
    write_plugin(
        plugins,
        "chat-adapter",
        plugin_type="channel-adapter",
        manifest_extra={
            "entrypoint": ["{python}", "{plugin_dir}/main.py"],
        },
    )
    (plugins / "chat-adapter" / "main.py").write_text(textwrap.dedent('''
        import json
        import os
        import time
        from pathlib import Path

        data_dir = Path(os.environ["DICEFRAME_PLUGIN_DATA_DIR"])
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "observed-env.json").write_text(json.dumps({
            "plugin_id": os.environ.get("DICEFRAME_PLUGIN_ID"),
            "plugin_data_dir": os.environ.get("DICEFRAME_PLUGIN_DATA_DIR"),
            "host_secret": os.environ.get("DICEFRAME_TEST_HOST_SECRET"),
            "api_base": os.environ.get("TRPG_API_BASE"),
            "bot_token": os.environ.get("TRPG_BOT_TOKEN"),
        }), encoding="utf-8")
        time.sleep(60)
    '''), encoding="utf-8")
    monkeypatch.setenv("DICEFRAME_TEST_HOST_SECRET", "must-not-leak")
    host = PluginHost(
        plugins,
        tmp_path / "data",
        base_env={"TRPG_API_BASE": "http://127.0.0.1:18000", "TRPG_BOT_TOKEN": "bot-secret"},
    )
    host.discover()
    observed_path = tmp_path / "data" / "chat-adapter" / "runtime" / "observed-env.json"

    try:
        await host.start("chat-adapter", require_enabled=False)
        for _ in range(100):
            if observed_path.exists():
                break
            await asyncio.sleep(0.02)
        observed = json.loads(observed_path.read_text(encoding="utf-8"))

        assert observed["host_secret"] is None
        assert observed["plugin_id"] == "chat-adapter"
        assert Path(observed["plugin_data_dir"]).resolve() == observed_path.parent.resolve()
        assert observed["api_base"] == "http://127.0.0.1:18000"
        assert observed["bot_token"]
        assert observed["bot_token"] != "bot-secret"
    finally:
        await host.cleanup()


@pytest.mark.asyncio
async def test_ai_provider_reference_injects_only_resolved_connection_fields(tmp_path):
    plugins = tmp_path / "plugins"
    write_plugin(
        plugins,
        "image-provider",
        plugin_type="provider",
        entrypoint=True,
        manifest_extra={
            "entrypoint": ["{python}", "{plugin_dir}/main.py"],
            "permissions": ["network.client", "plugin.config", "ai.providers", "process.spawn", "plugin.data"],
        },
    )
    (plugins / "image-provider" / "config.schema.json").write_text(json.dumps({
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean", "default": False, "ui": {"control": "switch"}},
            "provider_ref": {
                "type": "string",
                "default": "images",
                "ui": {
                    "control": "select",
                    "options_source": "ai_providers",
                    "api_format": "openai",
                    "provider_base_url_env": "DF_IMAGEGEN_BASE_URL",
                    "provider_api_key_env": "DF_IMAGEGEN_API_KEY",
                    "provider_api_format_env": "DF_IMAGEGEN_API_FORMAT",
                },
            },
        },
    }), encoding="utf-8")
    _write_provider_env_observer(plugins / "image-provider")
    host = PluginHost(
        plugins,
        tmp_path / "data",
        ai_provider_resolver=lambda ref: {
            "base_url": "https://images.example/v1",
            "api_key": "provider-secret",
            "api_format": "openai",
        } if ref == "images" else None,
    )
    host.discover()
    try:
        await host.start("image-provider", require_enabled=False)
        observed = json.loads((
            tmp_path / "data" / "image-provider" / "runtime" / "observed-env.json"
        ).read_text(encoding="utf-8"))

        assert observed["DF_IMAGEGEN_BASE_URL"] == "https://images.example/v1"
        assert observed["DF_IMAGEGEN_API_KEY"] == "provider-secret"
        assert observed["DF_IMAGEGEN_API_FORMAT"] == "openai"
    finally:
        await host.cleanup()


@pytest.mark.asyncio
async def test_ai_provider_reference_requires_explicit_permission(tmp_path):
    plugins = tmp_path / "plugins"
    write_plugin(
        plugins,
        "image-provider",
        plugin_type="provider",
        entrypoint=True,
        manifest_extra={
            "entrypoint": ["{python}", "{plugin_dir}/main.py"],
            "permissions": ["network.client", "plugin.config", "process.spawn", "plugin.data"],
        },
    )
    (plugins / "image-provider" / "config.schema.json").write_text(json.dumps({
        "type": "object",
        "properties": {
            "provider_ref": {
                "type": "string",
                "default": "images",
                "ui": {
                    "control": "select",
                    "options_source": "ai_providers",
                    "provider_api_key_env": "DF_IMAGEGEN_API_KEY",
                },
            },
        },
    }), encoding="utf-8")
    _write_provider_env_observer(plugins / "image-provider")
    host = PluginHost(
        plugins,
        tmp_path / "data",
        ai_provider_resolver=lambda _ref: {"api_key": "provider-secret", "api_format": "openai"},
    )
    host.discover()
    try:
        await host.start("image-provider", require_enabled=False)
        observed = json.loads((
            tmp_path / "data" / "image-provider" / "runtime" / "observed-env.json"
        ).read_text(encoding="utf-8"))

        assert observed["DF_IMAGEGEN_API_KEY"] is None
    finally:
        await host.cleanup()


def test_unknown_plugin_permission_is_rejected(tmp_path):
    plugins = tmp_path / "plugins"
    write_plugin(plugins, "bad-permission", manifest_extra={"permissions": ["network.client", "system.full"]})
    host = PluginHost(plugins, tmp_path / "data")

    found = host.discover()

    bad = found[0]
    assert bad["status"] == "failed"
    assert "未知插件权限" in bad["error"]


def test_channel_adapter_still_requires_entrypoint(tmp_path):
    plugins = tmp_path / "plugins"
    write_plugin(plugins, "bad-adapter", plugin_type="channel-adapter", entrypoint=False)
    host = PluginHost(plugins, tmp_path / "data")

    found = host.discover()

    bad = found[0]
    assert bad["status"] == "failed"
    assert "entrypoint" in bad["error"]


