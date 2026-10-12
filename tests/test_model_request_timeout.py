from __future__ import annotations

import pytest

from src.webui.config_update import prepare_config_update


def test_model_request_timeout_is_saved_independently_from_connection_test_timeout():
    prepared = prepare_config_update(
        {"test_timeout_seconds": 30},
        {"model_request_timeout_seconds": 240},
    )

    assert prepared.error == ""
    assert prepared.state["model_request_timeout_seconds"] == 240
    assert prepared.state["test_timeout_seconds"] == 30


@pytest.mark.parametrize("timeout", [9, 601, "bad"])
def test_model_request_timeout_rejects_invalid_values(timeout):
    prepared = prepare_config_update({}, {"model_request_timeout_seconds": timeout})

    assert prepared.error
    assert "model_request_timeout_seconds" not in prepared.state
