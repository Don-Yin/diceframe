"""plugin_host 测试共享辅助（自原 test_plugin_host.py 拆分）。"""
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


def write_plugin(root, plugin_id="example", *, plugin_type="channel-adapter", entrypoint=True, manifest_extra=None):
    folder = root / plugin_id
    folder.mkdir(parents=True)
    manifest = {
        "schema_version": 1, "id": plugin_id, "name": "Example", "version": "1",
        "description": "test",
        "config_schema": "config.schema.json",
    }
    if plugin_type is not None:
        manifest["plugin_type"] = plugin_type
    if entrypoint:
        manifest["entrypoint"] = ["{python}", "-c", "pass"]
    if manifest_extra:
        manifest.update(manifest_extra)
    (folder / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "config.schema.json").write_text(json.dumps({
        "type": "object", "properties": {
            "enabled": {"type": "boolean", "default": False, "ui": {"control": "switch"}},
            "names": {"type": "array", "default": [], "ui": {"control": "string-list"}},
            "token": {"type": "string", "ui": {"control": "secret", "sensitive": True}},
        },
    }), encoding="utf-8")



def write_png(path: Path, *, size: tuple[int, int] = (32, 32)) -> None:
    Image.new("RGBA", size, (74, 116, 142, 255)).save(path, format="PNG")



def make_plugin_zip(path, plugin_id="demo-plugin"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{plugin_id}/plugin.json", json.dumps({
            "schema_version": 1,
            "id": plugin_id,
            "name": "Demo",
            "version": "1",
            "description": "demo",
            "plugin_type": "channel-adapter",
            "entrypoint": ["{python}", "-c", "pass"],
            "config_schema": "config.schema.json",
        }))
        archive.writestr(f"{plugin_id}/config.schema.json", json.dumps({
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": False, "ui": {"control": "switch"}},
            },
        }))


