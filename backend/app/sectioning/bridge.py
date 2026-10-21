"""Browser bridge: lets a run use a model on the visitor's own machine (Ollama, LM Studio).

A run whose model is "browser/<name>" never calls a model from the server. Each model call is
queued here; the signed-in browser that owns the run long-polls `next()`, sends the prompt to its
local model (http://localhost:11434 by default) and posts the reply back with `resolve()`. The
server validates the reply against the call's schema like any other model output.

In memory and per process: run the API with one worker (uvicorn default) for browser runs.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

BROWSER_PREFIX = "browser/"


class BrowserBridge:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._pending: dict[str, asyncio.Future[str]] = {}

    async def call(self, payload: dict[str, Any], wait_seconds: float) -> str:
        """Queue one model call and wait for the browser's reply text."""
        rid = uuid.uuid4().hex
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self._queue.put({"id": rid, **payload})
        try:
            async with asyncio.timeout(wait_seconds):
                return await fut
        except TimeoutError as exc:
            raise TimeoutError(
                "no reply from your local model: keep the page open and check that the model is running"
            ) from exc
        finally:
            self._pending.pop(rid, None)

    async def next(self, wait: float) -> dict[str, Any] | None:
        """The next queued call for the browser, or None after `wait` seconds."""
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
            fut.set_exception(RuntimeError(f"local model error: {error[:300]}"))
        else:
            fut.set_result(content or "")
        return True


BRIDGES: dict[int, BrowserBridge] = {}
