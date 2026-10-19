"""Resume hosted combat after a narrative round has released live locks."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("trpg")


class HostedCombatScheduler:
    def __init__(self, *, get_instance: Callable, seat_for: Callable,
                 resume: Callable[[str, str], Awaitable[dict]]):
        self._get_instance, self._seat_for, self._resume = get_instance, seat_for, resume
        self._tasks: dict[tuple, asyncio.Task] = {}
        self._closed = False

    def schedule(self, instance: Any) -> None:
        key = (instance.game_key, instance.run_id)
        if self._closed or key in self._tasks:
            return
        task = asyncio.create_task(self._run(instance, instance.run_id))
        self._tasks[key] = task
        task.add_done_callback(lambda _task: self._tasks.pop(key, None))

    async def _run(self, instance: Any, run_id: str) -> None:
        try:
            # A turn service may still own authority after the round processor
            # returns. Wait for both owners, then release them before model I/O.
            async with instance.authoritative_write() as entered:
                if not entered:
                    return
                async with instance._process_lock:
                    if self._get_instance(instance.game_key) is not instance or instance.run_id != run_id:
                        return
                    uid = self._seat_for(instance)
            if uid:
                result = await self._resume("|".join(instance.game_key), uid)
                if not result.get("ok"):
                    logger.warning("Hosted combat resume rejected: %s", result.get("error_code", result.get("code")))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Hosted combat resume failed; current turn remains retryable")

    async def wait_idle(self) -> None:
        await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)

    async def close(self) -> None:
        self._closed = True
        for task in list(self._tasks.values()):
            task.cancel()
        await self.wait_idle()
