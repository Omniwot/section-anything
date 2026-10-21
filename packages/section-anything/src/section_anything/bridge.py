"""Browser bridge: answer a run's model calls with a model on someone else's machine.

A run whose model is "browser/<name>" never calls a provider. Each model call is queued here; a
client (for example a web page that can reach the user's own Ollama or LM Studio) long-polls
`next()`, sends the prompt to its model and posts the reply back with `resolve()`. The reply is
validated against the call's schema like any other model output.

The queue is in memory and per process: the host application must route a run's polling
requests to the process that runs it.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from section_anything.config import BROWSER_PREFIX
from section_anything.errors import SectionAnythingError

__all__ = ["BROWSER_PREFIX", "BridgeError", "BridgeTimeout", "BrowserBridge"]


class BridgeError(SectionAnythingError, RuntimeError):
    """The remote model reported an error."""


class BridgeTimeout(BridgeError, TimeoutError):
    """No reply arrived in time."""


class BrowserBridge:
    def __init__(self, wait_seconds: float = 300.0) -> None:
        self.wait_seconds = wait_seconds
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._pending: dict[str, asyncio.Future[str]] = {}

    async def call(self, payload: dict[str, Any], wait_seconds: float | None = None) -> str:
        """Queue one model call and wait for the reply text."""
        rid = uuid.uuid4().hex
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self._queue.put({"id": rid, **payload})
        try:
            async with asyncio.timeout(self.wait_seconds if wait_seconds is None else wait_seconds):
                return await fut
        except TimeoutError as exc:
            raise BridgeTimeout(
                "no reply from your local model: keep the page open and check that the model is running"
            ) from exc
        finally:
            self._pending.pop(rid, None)

    async def next(self, wait: float) -> dict[str, Any] | None:
        """The next queued call, or None after `wait` seconds."""
        try:
            async with asyncio.timeout(wait):
                return await self._queue.get()
        except TimeoutError:
            return None

    def resolve(self, rid: str, content: str | None, error: str | None) -> bool:
        fut = self._pending.get(rid)
        if fut is None or fut.done():
            return False
        if error is not None:
            fut.set_exception(BridgeError(f"local model error: {error[:300]}"))
        else:
            fut.set_result(content or "")
        return True
