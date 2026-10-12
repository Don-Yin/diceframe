from __future__ import annotations

import pytest
from pathlib import Path

from src.webui.services import system
from src.webui.services.system import is_newer_version


def test_is_newer_version_compares_numeric_segments():
    assert is_newer_version("v0.10.0", "0.9.9")
    assert is_newer_version("1.0", "0.10.0")
    assert not is_newer_version("0.9.9", "0.10.0")


def test_is_newer_version_orders_prerelease_before_release():
    assert is_newer_version("1.2.0-beta.1", "1.1.9")
    # 同号预览版不新于正式版（beta 不能覆盖正式版）
    assert not is_newer_version("1.2.0-beta.1", "1.2.0")
    # 正式版新于同号预览版（转正可被检测到）
    assert is_newer_version("1.2.0", "1.2.0-beta.1")


def test_is_newer_version_orders_prerelease_identifiers():
    assert is_newer_version("1.9.12-beta.3", "1.9.12-beta.2")
    assert is_newer_version("1.9.12-rc.1", "1.9.12-beta.9")
    assert is_newer_version("1.9.12-beta.2.1", "1.9.12-beta.2")
    assert not is_newer_version("1.9.12-beta.2", "1.9.12-beta.3")
    assert not is_newer_version("1.9.12+build.2", "1.9.12+build.1")


def test_is_newer_version_returns_false_for_unknown_formats():
    assert not is_newer_version("nightly", "0.1.0")
    assert not is_newer_version("0.2.0", "local-dev")


def _release_payload(version: str) -> dict:
    return {
        "tag_name": f"v{version}",
        "name": version,
        "body": "",
        "html_url": f"https://github.com/example/repo/releases/tag/v{version}",
        "published_at": "2026-08-01T00:00:00Z",
        "prerelease": False,
        "assets": [],
    }


class _FakeState:
    def __init__(self, channel: str):
        self.config = {"update_channel": channel}

    def dependencies(self) -> system.SystemDependencies:
        return system.SystemDependencies(
            data_dir=Path("data"),
            config_state=lambda: self.config,
            proxy_url=lambda: "",
            mirrors=lambda: None,
        )


@pytest.mark.asyncio
async def test_check_updates_preview_channel_uses_releases_and_marks_channel(monkeypatch):
    dependencies = _FakeState(channel="preview").dependencies()
    captured = {}

    async def fake_fetch(mirrors, repo, include_prerelease, proxy_url):
        captured["include_prerelease"] = include_prerelease
        return _release_payload("1.2.0-beta.1"), {"mode": "github-api"}

    monkeypatch.setattr(system, "_fetch_release_with_mirrors", fake_fetch)

    result = await system.check_updates(dependencies)

    assert captured["include_prerelease"] is True
    assert result["channel"] == "preview"
    assert result["latest"]["version"] == "1.2.0-beta.1"


@pytest.mark.asyncio
async def test_check_updates_stable_channel_uses_latest_and_marks_channel(monkeypatch):
    dependencies = _FakeState(channel="stable").dependencies()
    captured = {}

    async def fake_fetch(mirrors, repo, include_prerelease, proxy_url):
        captured["include_prerelease"] = include_prerelease
        return _release_payload("1.2.0"), {"mode": "github-api"}

    monkeypatch.setattr(system, "_fetch_release_with_mirrors", fake_fetch)

    result = await system.check_updates(dependencies)

    assert captured["include_prerelease"] is False
    assert result["channel"] == "stable"


@pytest.mark.asyncio
async def test_check_updates_explicit_override_wins_over_channel(monkeypatch):
    # stable 频道但显式传 include_prerelease=True → 走 preview
    dependencies = _FakeState(channel="stable").dependencies()
    captured = {}

    async def fake_fetch(mirrors, repo, include_prerelease, proxy_url):
        captured["include_prerelease"] = include_prerelease
        return _release_payload("1.3.0-beta.2"), {"mode": "github-api"}

    monkeypatch.setattr(system, "_fetch_release_with_mirrors", fake_fetch)

    result = await system.check_updates(dependencies, include_prerelease=True)

    assert captured["include_prerelease"] is True
    assert result["channel"] == "preview"
