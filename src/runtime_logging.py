"""Persistent runtime logging shared by every DiceFrame launch mode."""

from __future__ import annotations

import logging
import os
import re
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

RETENTION_DAYS = 30
LOG_FILENAME = "diceframe.log"
_HANDLER_MARKER = "_diceframe_runtime_log_handler"


def resolve_runtime_log_dir(data_dir: Path) -> Path:
    """Return the persistent log directory without coupling launchers to logging."""
    explicit = str(os.getenv("TRPG_LOG_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    install_root = str(os.getenv("TRPG_INSTALL_ROOT") or "").strip()
    if install_root:
        return (Path(install_root).expanduser().resolve() / "logs")

    install_mode = str(os.getenv("TRPG_INSTALL_MODE") or "").strip().lower()
    if install_mode.startswith("docker"):
        return data_dir.resolve() / "logs"

    return Path(__file__).resolve().parent.parent / "logs"


def _matches_runtime_log(path: Path) -> bool:
    return path.is_file() and (path.name == LOG_FILENAME or path.name.startswith(f"{LOG_FILENAME}."))


def cleanup_expired_runtime_logs(
    log_dir: Path,
    *,
    now: float | None = None,
    retention_days: int = RETENTION_DAYS,
) -> int:
    """Delete only rotated DiceFrame logs older than the retention window."""
    if not log_dir.exists():
        return 0
    cutoff = (time.time() if now is None else now) - retention_days * 24 * 60 * 60
    deleted = 0
    for path in log_dir.iterdir():
        if path.name == LOG_FILENAME or not _matches_runtime_log(path):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted += 1
        except FileNotFoundError:
            continue
    return deleted


# Credentials that can appear in a request URL; never written to a log.
_URL_SECRET_PARAMS = re.compile(r'(?i)(?<![\w-])(room_token|ticket|seat|seat_token)=[^&\s"]*')
_REDACTION_MARKER = "_diceframe_access_log_redaction"


class _AccessLogRedaction(logging.Filter):
    """Redact credential query values from aiohttp access log lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed record, leave as is
            message = None
        if message is not None:
            redacted = _redact_url_secrets(message)
            if redacted != message:
                record.msg = redacted
                record.args = None
        # aiohttp also attaches the raw request line as structured "extra" data,
        # which JSON or custom formatters may print.
        line = getattr(record, "first_request_line", None)
        if isinstance(line, str):
            record.first_request_line = _redact_url_secrets(line)
        return True


def _redact_url_secrets(text: str) -> str:
    return _URL_SECRET_PARAMS.sub(lambda match: f"{match.group(1)}=[redacted]", text)


def install_access_log_redaction(logger: logging.Logger | None = None) -> None:
    """Attach the redaction filter to the aiohttp access logger (once)."""
    target = logger or logging.getLogger("aiohttp.access")
    if not any(getattr(item, _REDACTION_MARKER, False) for item in target.filters):
        redaction = _AccessLogRedaction()
        setattr(redaction, _REDACTION_MARKER, True)
        target.addFilter(redaction)


def configure_runtime_logging(
    data_dir: Path,
    *,
    logger: logging.Logger | None = None,
    log_dir: Path | None = None,
) -> Path:
    """Add one daily rotating file handler while preserving console logging."""
    target_logger = logger or logging.getLogger()
    install_access_log_redaction()
    directory = (log_dir or resolve_runtime_log_dir(data_dir)).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    cleanup_expired_runtime_logs(directory)

    for handler in target_logger.handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            return Path(handler.baseFilename)  # type: ignore[attr-defined]

    path = directory / LOG_FILENAME
    handler = TimedRotatingFileHandler(
        path,
        when="midnight",
        interval=1,
        backupCount=RETENTION_DAYS,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s %(message)s")
    )
    setattr(handler, _HANDLER_MARKER, True)
    target_logger.addHandler(handler)
    return path


def runtime_log_status(data_dir: Path, *, log_dir: Path | None = None) -> dict[str, Any]:
    directory = (log_dir or resolve_runtime_log_dir(data_dir)).resolve()
    files = [] if not directory.exists() else [path for path in directory.iterdir() if _matches_runtime_log(path)]
    total_bytes = 0
    for path in files:
        try:
            total_bytes += path.stat().st_size
        except FileNotFoundError:
            continue
    return {
        "ok": True,
        "retention_days": RETENTION_DAYS,
        "file_count": len(files),
        "total_bytes": total_bytes,
    }


def clear_runtime_logs(
    data_dir: Path,
    *,
    logger: logging.Logger | None = None,
    log_dir: Path | None = None,
) -> dict[str, Any]:
    """Clear active and rotated runtime logs without touching unrelated files."""
    target_logger = logger or logging.getLogger()
    directory = (log_dir or resolve_runtime_log_dir(data_dir)).resolve()
    active_path = directory / LOG_FILENAME
    cleared_files = 0
    cleared_bytes = 0

    active_handlers = [
        handler
        for handler in target_logger.handlers
        if getattr(handler, _HANDLER_MARKER, False)
        and Path(handler.baseFilename).resolve() == active_path  # type: ignore[attr-defined]
    ]
    if active_path.exists():
        try:
            cleared_bytes += active_path.stat().st_size
            cleared_files += 1
        except FileNotFoundError:
            pass
        if active_handlers:
            for handler in active_handlers:
                handler.acquire()
                try:
                    handler.flush()
                    stream = getattr(handler, "stream", None)
                    if stream is not None:
                        stream.seek(0)
                        stream.truncate(0)
                    else:
                        active_path.write_text("", encoding="utf-8")
                finally:
                    handler.release()
        else:
            active_path.unlink(missing_ok=True)

    if directory.exists():
        for path in directory.iterdir():
            if path.name == LOG_FILENAME or not _matches_runtime_log(path):
                continue
            try:
                cleared_bytes += path.stat().st_size
                path.unlink()
                cleared_files += 1
            except FileNotFoundError:
                continue

    return {
        **runtime_log_status(data_dir, log_dir=directory),
        "cleared_files": cleared_files,
        "cleared_bytes": cleared_bytes,
    }
