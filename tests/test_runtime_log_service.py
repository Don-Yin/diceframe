from __future__ import annotations

import io
import zipfile
from pathlib import Path

from src.runtime_diagnostics import assistant_runtime_log_context
from src.runtime_logging import LOG_FILENAME
from src.webui.services.system import SystemDependencies, SystemService


def test_system_service_uses_persistent_log_root_for_versioned_runtime_data(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TRPG_INSTALL_MODE", "docker-managed")
    monkeypatch.setenv("TRPG_DOCKER_DATA_HOME", str(tmp_path / "data"))
    host_data = tmp_path / "data"
    versioned_data = host_data / "_updater" / "data-versions" / "v3"
    log_dir = host_data / "logs"
    log_dir.mkdir(parents=True)
    versioned_data.mkdir(parents=True)
    (versioned_data / "saves").mkdir()
    (versioned_data / "saves" / "state.json").write_text("business data", encoding="utf-8")
    (log_dir / LOG_FILENAME).write_text(
        'ERROR api_key="sk-secret-value" runtime probe', encoding="utf-8"
    )

    service = SystemService(
        SystemDependencies(
            data_dir=versioned_data,
            config_state=lambda: {},
            proxy_url=lambda: "",
            mirrors=lambda: None,
        )
    )

    assert service.runtime_log_status()["file_count"] == 1
    assert service.runtime_log_status()["total_bytes"] > 0

    payload, count = service.export_runtime_logs()
    assert count == 1
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.namelist() == [LOG_FILENAME]
        exported = archive.read(LOG_FILENAME).decode("utf-8")
    assert "sk-secret-value" not in exported
    assert "[REDACTED]" in exported

    context, context_count = assistant_runtime_log_context(versioned_data)
    assert context_count == 1
    assert "runtime probe" in context

    cleared = service.clear_runtime_logs()
    assert cleared["cleared_files"] == 1
    assert cleared["file_count"] == 0
    assert (versioned_data / "saves" / "state.json").read_text(encoding="utf-8") == "business data"
