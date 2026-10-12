"""Asyncio runtime helpers shared by the DiceFrame server entry point."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Mapping
from typing import Any


logger = logging.getLogger("trpg.asyncio")


def _is_windows_proactor_disconnect(
    context: Mapping[str, Any],
    *,
    platform: str | None = None,
) -> bool:
    """Return whether *context* is the harmless Windows Proactor reset noise."""

    if (platform or sys.platform) != "win32":
        return False

    exception = context.get("exception")
    if not isinstance(exception, ConnectionResetError):
        return False
    if getattr(exception, "winerror", None) != 10054 and exception.errno != 10054:
        return False

    handle = context.get("handle")
    callback = getattr(handle, "_callback", None)
    owner = getattr(callback, "__self__", None)
    owner_types = {base.__name__ for base in type(owner).__mro__}
    return (
        getattr(callback, "__name__", "") == "_call_connection_lost"
        and "_ProactorBasePipeTransport" in owner_types
    )


def install_runtime_exception_handler(loop: asyncio.AbstractEventLoop) -> None:
    """Keep expected Windows disconnects out of the error log."""

    previous_handler = loop.get_exception_handler()

    def handle_exception(
        current_loop: asyncio.AbstractEventLoop,
        context: dict[str, Any],
    ) -> None:
        if _is_windows_proactor_disconnect(context):
            logger.debug("客户端连接已在服务切换或页面关闭时断开（WinError 10054）")
            return
        if previous_handler is not None:
            previous_handler(current_loop, context)
            return
        current_loop.default_exception_handler(context)

    loop.set_exception_handler(handle_exception)
