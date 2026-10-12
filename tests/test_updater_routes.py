"""Application restart route contract and handoff tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.webui.routes import updater as updater_routes


def _payload(response) -> dict:
    return json.loads(response.text)


@pytest.mark.asyncio
async def test_application_restart_schedules_graceful_shutdown(monkeypatch):
    called = False

    async def fake_restart_after_response() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        updater_routes,
        "_restart_after_response",
        fake_restart_after_response,
    )
    control = {
        "boot_id": "boot-old",
        "restart_requested": False,
        "restart_task": None,
    }
    request = SimpleNamespace(
        headers={"X-TRPG-Confirm": "true"},
        app={"runtime_control": control},
    )

    response = await updater_routes.api_application_restart(request)
    await control["restart_task"]

    assert response.status == 200
    assert _payload(response) == {
        "ok": True,
        "restarting": True,
        "boot_id": "boot-old",
    }
    assert control["restart_requested"] is True
    assert called is True


@pytest.mark.asyncio
async def test_application_restart_rejects_missing_confirmation_and_duplicates():
    control = {
        "boot_id": "boot-old",
        "restart_requested": False,
        "restart_task": None,
    }
    missing = SimpleNamespace(headers={}, app={"runtime_control": control})
    denied = await updater_routes.api_application_restart(missing)
    assert denied.status == 403
    assert control["restart_requested"] is False

    control["restart_requested"] = True
    duplicate = SimpleNamespace(
        headers={"X-TRPG-Confirm": "true"},
        app={"runtime_control": control},
    )
    conflict = await updater_routes.api_application_restart(duplicate)
    assert conflict.status == 409
    assert _payload(conflict)["ok"] is False


@pytest.mark.asyncio
async def test_update_health_exposes_current_boot_id():
    request = SimpleNamespace(app={"runtime_control": {"boot_id": "boot-new"}})
    response = await updater_routes.api_update_health(request)
    payload = _payload(response)
    assert payload["ok"] is True
    assert payload["boot_id"] == "boot-new"
    assert isinstance(payload["pid"], int)
