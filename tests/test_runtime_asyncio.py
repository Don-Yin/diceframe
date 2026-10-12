from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from src.runtime_asyncio import (
    _is_windows_proactor_disconnect,
    install_runtime_exception_handler,
)


def _proactor_context(code: int = 10054) -> dict[str, Any]:
    def _call_connection_lost(self, exc) -> None:
        return None

    transport_type = type(
        "_ProactorBasePipeTransport",
        (),
        {"_call_connection_lost": _call_connection_lost},
    )
    exception = ConnectionResetError(code, "connection reset")
    exception.winerror = code
    callback = transport_type()._call_connection_lost
    return {
        "message": "Exception in callback",
        "exception": exception,
        "handle": SimpleNamespace(_callback=callback),
    }


def test_windows_proactor_disconnect_is_recognized() -> None:
    assert _is_windows_proactor_disconnect(_proactor_context(), platform="win32")


def test_filter_does_not_hide_unrelated_failures() -> None:
    assert not _is_windows_proactor_disconnect(_proactor_context(), platform="linux")
    assert not _is_windows_proactor_disconnect(_proactor_context(10053), platform="win32")
    assert not _is_windows_proactor_disconnect(
        {"exception": RuntimeError("boom")},
        platform="win32",
    )


class _FakeLoop:
    def __init__(self) -> None:
        self.handler = None
        self.default_contexts: list[dict[str, Any]] = []

    def get_exception_handler(self):
        return None

    def set_exception_handler(self, handler) -> None:
        self.handler = handler

    def default_exception_handler(self, context: dict[str, Any]) -> None:
        self.default_contexts.append(context)


def test_installed_handler_forwards_other_exceptions() -> None:
    loop = _FakeLoop()
    install_runtime_exception_handler(loop)  # type: ignore[arg-type]

    context = {"message": "unexpected", "exception": RuntimeError("boom")}
    loop.handler(loop, context)

    assert loop.default_contexts == [context]
