"""Bounded REST recovery for appliances whose push feed missed an update."""

import asyncio
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class HonStateRecovery:
    """Refresh all devices without one failure preventing the others."""

    def __init__(self, hon: Any, timeout: float = 30) -> None:
        self.hon = hon
        self.timeout = timeout
        self.available = {device.unique_id: True for device in hon.appliances}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[Any] | None = None
        self._closed = False

    async def refresh(self) -> dict[str, bool]:
        async with self._lock:
            if self._closed:
                return self.available.copy()
            self._task = asyncio.current_task()
            try:
                for device in self.hon.appliances:
                    try:
                        async with asyncio.timeout(self.timeout):
                            await device.update(force=True)
                    except Exception as error:  # Isolate a failed appliance refresh.
                        self.available[device.unique_id] = False
                        _LOGGER.warning(
                            "Appliance state refresh failed: %s", type(error).__name__
                        )
                    else:
                        self.available[device.unique_id] = True
                return self.available.copy()
            finally:
                self._task = None

    async def close(self) -> None:
        self._closed = True
        if self._task and self._task is not asyncio.current_task():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
