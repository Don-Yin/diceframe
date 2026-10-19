from types import SimpleNamespace

import pytest
import asyncio

from src.game_preferences import default_preferences
from src.webui.config_controller import ConfigController, ConfigControllerDependencies
from src.webui.services.assistant_settings_tools import config_digest


def controller(state, saved=None):
    saved = saved if saved is not None else []
    deps = ConfigControllerDependencies(
        state=state, environ={}, cors_env_value="", public_config=lambda: dict(state),
        save_config=lambda: saved.append(dict(state)), ensure_bot_token=lambda: "token",
        delete_access_token_file=lambda: None, build_subsystems=lambda **kwargs: None,
        make_api=lambda *args, **kwargs: None, activate_api_runtime=lambda *args: None,
    )
    return ConfigController(deps), saved


@pytest.mark.asyncio
async def test_apply_values_is_shared_non_http_config_writer():
    state = {"game_defaults": default_preferences()}
    ctl, saved = controller(state)
    app = {"subsystems": None, "api": None, "plugin_host": None}
    response = await ctl.apply_values(app, {"game_defaults": {"story_mode": "dialogue"}})
    assert response.status == 200
    assert state["game_defaults"]["story_mode"] == "dialogue"
    assert saved


@pytest.mark.asyncio
async def test_attach_agent_actions_registers_public_actions_and_reuses_apply_values():
    state = {"game_defaults": default_preferences()}
    ctl, _ = controller(state)

    class API:
        def __init__(self):
            self.actions = ()

        def register_application_actions(self, actions):
            self.actions = tuple(actions)

        def list_plugins(self):
            return {"plugins": []}

    api = API()
    app = {"subsystems": None, "api": api, "plugin_host": None}
    ctl.attach_agent_actions(app, api)
    actions = {action.name: action for action in api.actions}
    assert {"read_settings", "patch_settings", "list_plugins"} <= set(actions)
    patch = actions["patch_settings"]
    result = await patch.handler({"changes": {"game_defaults": {"story_mode": "dialogue"}}}, "owner")
    assert result["ok"] is True
    assert state["game_defaults"]["story_mode"] == "dialogue"


@pytest.mark.asyncio
async def test_guarded_agent_write_rechecks_digest_after_waiting_for_reload_lock():
    state = {"game_defaults": default_preferences()}
    ctl, saved = controller(state)

    class API:
        def register_application_actions(self, actions):
            self.actions = tuple(actions)

    api = API()
    lock = asyncio.Lock()
    await lock.acquire()
    app = {"subsystems": None, "api": api, "plugin_host": None, "_config_reload_lock": lock}
    ctl.attach_agent_actions(app, api)
    action = next(item for item in api.actions if item.name == "patch_settings")
    old_digest = config_digest(state)
    pending = asyncio.create_task(action.handler(
        {"changes": {"game_defaults": {"story_mode": "dialogue"}}, "expected_config_digest": old_digest},
        "owner",
    ))
    await asyncio.sleep(0)
    state["model"] = "changed-while-waiting"
    lock.release()
    with pytest.raises(ValueError, match="Settings changed"):
        await pending
    assert saved == []


def test_attach_agent_actions_skips_legacy_api_without_registry():
    state = {"game_defaults": default_preferences()}
    ctl, _ = controller(state)
    ctl.attach_agent_actions({}, SimpleNamespace())
