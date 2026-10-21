"""OpenAI calls with schema-validated output, cost accounting and a call log.

Separate from app.core.llm: sectioning needs structured outputs, usage for
cost, and GPT-5 parameters (no temperature, max_completion_tokens,
reasoning_effort) that the template's generic LiteLLM wrapper doesn't pass.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel

from app.core.config import settings
from app.sectioning.bridge import BROWSER_PREFIX

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

CallSink = Callable[[dict], Awaitable[None]]


class CostCapExceeded(RuntimeError):
    pass


def price_of(model: str, inp: int, cached: int, out: int) -> float | None:
    price = settings.model_prices.get(model)
    if not price:
        return None
    return ((inp - cached) * price["input"] + cached * price["cached"] + out * price["output"]) / 1e6


@dataclass
class Usage:
    """Running totals for one run. Every attempt is also handed to `sink`
    (the audit log) as soon as it finishes."""

    calls: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    priced: bool = True
    sink: CallSink | None = None
    seq: int = 0
    bridge: object | None = None  # BrowserBridge for "browser/<model>" runs
    by_step: dict[str, float] = field(default_factory=dict)

    def add(self, model: str, usage) -> dict:
        tokens = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0}
        if usage is None:
            return tokens
        cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
        inp, out = usage.prompt_tokens or 0, usage.completion_tokens or 0
        cost = price_of(model, inp, cached, out)
        if cost is None:
            self.priced = False
        self.calls += 1
        self.input_tokens += inp
        self.cached_tokens += cached
        self.output_tokens += out
        self.reasoning_tokens += reasoning
        self.cost_usd += cost or 0.0
        return {
            "input_tokens": inp, "cached_tokens": cached, "output_tokens": out,
            "reasoning_tokens": reasoning, "cost_usd": None if cost is None else round(cost, 6),
        }

    async def record(self, entry: dict) -> None:
        self.seq += 1
        entry["seq"] = self.seq
        step = entry.get("step", "")
        self.by_step[step] = self.by_step.get(step, 0.0) + (entry.get("cost_usd") or 0.0)
        if self.sink:
            try:
                await self.sink(entry)
            except Exception:  # noqa: BLE001 — logging must never fail a run
                logger.exception("could not record LLM call")

    def summary(self) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "cached_tokens": self.cached_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cost_usd": round(self.cost_usd, 4) if self.priced else None,
            "cost_by_step": {k: round(v, 4) for k, v in self.by_step.items()},
        }


LOCAL_PREFIX = "ollama/"


def _client(model: str = ""):
    if model.startswith(LOCAL_PREFIX):
        # Local models through Ollama's OpenAI-compatible endpoint (dev and evaluation use; free, slower).
        from openai import AsyncOpenAI

        return AsyncOpenAI(base_url=settings.OLLAMA_BASE_URL, api_key="ollama",
                           timeout=settings.SECTIONING_LOCAL_TIMEOUT_SECONDS, max_retries=0)
    # Langfuse's drop-in client traces every call when keys are configured.
    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        from langfuse.openai import AsyncOpenAI
    else:
        from openai import AsyncOpenAI
    # max_retries=0: our own loop retries, and the SDK's hidden retries would spend past the cap.
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.SECTIONING_LLM_TIMEOUT_SECONDS, max_retries=0)


async def structured(
    *,
    model: str,
    system: str,
    user: str,
    schema: type[T],
    usage: Usage,
    cost_cap_usd: float,
    step: str,
    effort: str | None = "low",
    max_output_tokens: int = 32_000,
    attempts: int = 2,
    images: list[str] | None = None,
) -> T:
    """One schema-constrained completion. Retries once on refusal or an
    unparsable response; raises CostCapExceeded before spending past the cap."""
    if model.startswith(BROWSER_PREFIX):
        return await _structured_browser(model=model, system=system, user=user, schema=schema, usage=usage,
                                         step=step, max_output_tokens=max_output_tokens, attempts=attempts)
    if usage.priced and usage.cost_usd >= cost_cap_usd:
        raise CostCapExceeded(f"Run stopped at ${usage.cost_usd:.2f} (cap ${cost_cap_usd:.2f}).")
    content: list[dict] | str = user
    if images:
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": url, "detail": "high"}} for url in images
        ]
    local = model.startswith(LOCAL_PREFIX)
    kwargs = {
        "model": model.removeprefix(LOCAL_PREFIX),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        "response_format": schema,
        ("max_tokens" if local else "max_completion_tokens"): max_output_tokens,
    }
    if local:
        # Local models think by default on Ollama's OpenAI endpoint; that costs minutes per call on a laptop.
        kwargs["temperature"] = 0
        kwargs["reasoning_effort"] = "none"
    elif effort:
        kwargs["reasoning_effort"] = effort
    prompt = f"{system}\n\n{user}"
    base = {
        "step": step,
        "model": model,
        "reasoning_effort": effort,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "prompt_chars": len(prompt),
        "images": len(images or []),
        "prompt_text": prompt if settings.AUDIT_STORE_PROMPTS else None,
    }
    client = _client(model)
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        if usage.priced and usage.cost_usd >= cost_cap_usd:  # re-checked before every paid attempt
            raise CostCapExceeded(f"Run stopped at ${usage.cost_usd:.2f} (cap ${cost_cap_usd:.2f}).")
        t0 = time.monotonic()
        entry = {**base, "attempt": attempt, "status": "error", "error": None, "response": None}
        try:
            resp = await client.chat.completions.parse(**kwargs)
            entry.update(usage.add(model, resp.usage))
            msg = resp.choices[0].message
            if msg.refusal:
                entry["status"] = "refused"
                raise ValueError(f"model refused: {msg.refusal[:200]}")
            if msg.parsed is None:
                entry["status"] = "invalid"
                raise ValueError(f"unparsable response (finish={resp.choices[0].finish_reason})")
            entry["status"], entry["response"] = "ok", msg.parsed.model_dump()
            return msg.parsed
        except Exception as exc:  # noqa: BLE001 — retried, then surfaced
            last = exc
            entry["error"] = f"{type(exc).__name__}: {exc}"[:2000]
            logger.warning("sectioning LLM attempt %s failed: %s", attempt, exc)
        finally:
            entry["latency_ms"] = int((time.monotonic() - t0) * 1000)
            await usage.record(entry)
    raise RuntimeError(f"LLM call failed after {attempts} attempts: {last}")


async def _structured_browser(
    *, model: str, system: str, user: str, schema: type[T], usage: Usage, step: str, max_output_tokens: int, attempts: int
) -> T:
    """The visitor's own model, through their browser (see bridge.py). Free; validated like any output."""
    if usage.bridge is None:
        raise RuntimeError("browser model used without a browser bridge")
    payload = {"model": model.removeprefix(BROWSER_PREFIX), "system": system, "user": user,
               "schema": schema.model_json_schema(), "max_output_tokens": max_output_tokens}
    prompt = f"{system}\n\n{user}"
    base = {"step": step, "model": model, "reasoning_effort": None,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "prompt_chars": len(prompt), "images": 0,
            "prompt_text": prompt if settings.AUDIT_STORE_PROMPTS else None}
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        t0 = time.monotonic()
        entry = {**base, "attempt": attempt, "status": "error", "error": None, "response": None,
                 "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0}
        try:
            text = await usage.bridge.call(payload, wait_seconds=settings.BROWSER_LLM_TIMEOUT_SECONDS)
            usage.calls += 1
            text = text.strip()
            if text.startswith("```"):  # some local models wrap JSON in a code fence
                text = text.strip("`").removeprefix("json").strip()
            parsed = schema.model_validate_json(text)
            entry["status"], entry["response"] = "ok", parsed.model_dump()
            return parsed
        except Exception as exc:  # noqa: BLE001 - retried, then surfaced
            last = exc
            entry["error"] = f"{type(exc).__name__}: {exc}"[:2000]
            logger.warning("browser model attempt %s failed: %s", attempt, type(exc).__name__)
        finally:
            entry["latency_ms"] = int((time.monotonic() - t0) * 1000)
            await usage.record(entry)
    raise RuntimeError(f"local model call failed after {attempts} attempts: {last}")
