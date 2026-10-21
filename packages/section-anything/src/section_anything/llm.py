"""Model calls with schema-validated output, cost accounting and a call log.

- Any OpenAI-compatible endpoint: the client always gets an explicit `base_url` and `api_key`
  from `Settings`, so ambient ``OPENAI_BASE_URL`` settings of a host application never redirect
  these calls. Nothing is written to ``os.environ``.
- No hidden retries (`max_retries=0`): one retry on refusal or unparsable output, done here.
- Cost cap: checked before every attempt, and each call's output tokens are limited to what the
  remaining budget can pay for.
- Errors kept in logs and call records name the error type, HTTP status and error code, never
  prompt or response text (the prompt is the document). Prompt text is stored in call records
  only with `store_prompts`.
- Langfuse tracing only when `Settings.langfuse` is true and the `langfuse` extra is installed.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from section_anything.config import BROWSER_PREFIX, LOCAL_PREFIX, Price, Settings
from section_anything.errors import ConfigError, CostCapExceeded, LlmCallFailed

__all__ = ["BROWSER_PREFIX", "LOCAL_PREFIX", "CallSink", "CostCapExceeded", "LlmCallFailed", "Usage", "price_of",
           "structured"]

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

CallSink = Callable[[dict], Awaitable[None]]
CHARS_PER_TOKEN = 3.0  # conservative (English averages ~4): over- rather than under-estimates input cost
MIN_OUTPUT_TOKENS = 256  # below this a structured answer cannot fit: stop instead of calling


def price_of(model: str, inp: int, cached: int, out: int, settings: Settings | None = None) -> float | None:
    """USD for one call, or None when the model has no known price."""
    price = (settings or Settings()).price_for(model)
    return None if price is None else price.cost(inp, out, cached)


@dataclass
class Usage:
    """Running totals for one document. Every attempt is also handed to `sink` (an audit log, for
    example) as soon as it finishes."""

    calls: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    priced: bool = True
    sink: CallSink | None = None
    seq: int = 0
    bridge: Any | None = None  # BrowserBridge for "browser/<model>" runs
    by_step: dict[str, float] = field(default_factory=dict)

    def add(self, model: str, usage, price: Price | None = None) -> dict:
        tokens = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0}
        if usage is None:
            return tokens
        cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
        inp, out = usage.prompt_tokens or 0, usage.completion_tokens or 0
        cost = None if price is None else price.cost(inp, out, cached)
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
            except Exception as exc:  # noqa: BLE001 — logging must never fail a run
                # Type only: database errors can echo the record, which may hold document text.
                logger.warning("could not record LLM call: %s", type(exc).__name__)

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


class _BadOutput(Exception):
    """A response we reject. The message is ours and never quotes the response."""


def describe_error(exc: BaseException) -> str:
    """Error text safe to log or store: type, HTTP status and error code, never prompt or output
    text (provider and validation messages can quote either)."""
    from section_anything.bridge import BridgeError

    if isinstance(exc, _BadOutput | CostCapExceeded | ConfigError | BridgeError):
        return f"{type(exc).__name__}: {exc}"
    if isinstance(exc, ValidationError):
        return f"ValidationError: {exc.error_count()} error(s)"
    parts = [type(exc).__name__]
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        parts.append(f"HTTP {status}")
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.replace("_", "").isalnum() and len(code) <= 64:
        parts.append(code)
    return " ".join(parts)


def _client(model: str, settings: Settings):
    if model.startswith(LOCAL_PREFIX):
        # Local models through Ollama's OpenAI-compatible endpoint: free, slower.
        from openai import AsyncOpenAI

        return AsyncOpenAI(base_url=settings.ollama_base_url, api_key="ollama",
                           timeout=settings.local_timeout_seconds, max_retries=0)
    if settings.langfuse:
        try:
            from langfuse.openai import AsyncOpenAI
        except ImportError:
            raise ConfigError("langfuse=True needs the extra: pip install 'section-anything[langfuse]'") from None
    else:
        from openai import AsyncOpenAI
    if settings.api_key is None:
        raise ConfigError("no API key: set SECTIONANY_API_KEY or pass api_key=")
    # max_retries=0: our own loop retries; the SDK's hidden retries would spend past the cap.
    return AsyncOpenAI(api_key=settings.api_key.get_secret_value(), base_url=settings.base_url,
                       timeout=settings.llm_timeout_seconds, max_retries=0)


def _is_free(price: Price | None) -> bool:
    return price is not None and price.input == 0 and price.output == 0 and not price.cached


def _over_cap(usage: Usage, cap: float, price: Price | None) -> bool:
    return usage.priced and usage.cost_usd >= cap and not _is_free(price)


def _affordable_output(price: Price | None, prompt_chars: int, usage: Usage, cap: float, wanted: int) -> int:
    """Output tokens this call may use so that its worst case stays within the cap."""
    if price is None or not usage.priced or _is_free(price):
        return wanted
    left = cap - usage.cost_usd
    input_cost = prompt_chars / CHARS_PER_TOKEN * price.input / 1e6
    if price.output <= 0:
        if left - input_cost < 0:
            raise CostCapExceeded(f"Run stopped at ${usage.cost_usd:.2f}: the next call would pass the ${cap:.2f} cap.")
        return wanted
    afford = int((left - input_cost) * 1e6 / price.output)
    if afford < MIN_OUTPUT_TOKENS:
        raise CostCapExceeded(f"Run stopped at ${usage.cost_usd:.2f}: the next call would pass the ${cap:.2f} cap.")
    return min(wanted, afford)


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
    settings: Settings | None = None,
) -> T:
    """One schema-constrained completion. Retries once on refusal or an unparsable response;
    raises CostCapExceeded before spending past the cap."""
    s = settings or Settings()
    if model.startswith(BROWSER_PREFIX):
        return await _structured_browser(model=model, system=system, user=user, schema=schema, usage=usage,
                                         step=step, max_output_tokens=max_output_tokens, attempts=attempts,
                                         settings=s)
    price = s.price_for(model)
    if _over_cap(usage, cost_cap_usd, price):
        raise CostCapExceeded(f"Run stopped at ${usage.cost_usd:.2f} (cap ${cost_cap_usd:.2f}).")
    content: list[dict] | str = user
    if images:
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": url, "detail": "high"}} for url in images
        ]
    local = model.startswith(LOCAL_PREFIX)
    max_key = "max_tokens" if local else "max_completion_tokens"
    kwargs: dict[str, Any] = {
        "model": model.removeprefix(LOCAL_PREFIX),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        "response_format": schema,
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
        "prompt_text": prompt if s.store_prompts else None,
    }
    client = _client(model, s)
    last: BaseException | None = None
    try:
        for attempt in range(1, attempts + 1):
            if _over_cap(usage, cost_cap_usd, price):  # re-checked before every paid attempt
                raise CostCapExceeded(f"Run stopped at ${usage.cost_usd:.2f} (cap ${cost_cap_usd:.2f}).")
            kwargs[max_key] = _affordable_output(price, len(prompt), usage, cost_cap_usd, max_output_tokens)
            t0 = time.monotonic()
            entry = {**base, "attempt": attempt, "status": "error", "error": None, "response": None}
            try:
                resp = await client.chat.completions.parse(**kwargs)
                entry.update(usage.add(model, resp.usage, price))
                msg = resp.choices[0].message
                if msg.refusal:
                    entry["status"] = "refused"
                    if s.store_prompts:
                        entry["response"] = {"refusal": msg.refusal[:500]}
                    raise _BadOutput("model refused")
                if msg.parsed is None:
                    entry["status"] = "invalid"
                    raise _BadOutput(f"unparsable response (finish={resp.choices[0].finish_reason})")
                entry["status"], entry["response"] = "ok", msg.parsed.model_dump()
                return msg.parsed
            except Exception as exc:  # noqa: BLE001 — retried, then surfaced
                last = exc
                entry["error"] = describe_error(exc)
                logger.warning("sectioning model call attempt %s failed: %s", attempt, entry["error"])
            finally:
                entry["latency_ms"] = int((time.monotonic() - t0) * 1000)
                await usage.record(entry)
    finally:
        await client.close()
    raise LlmCallFailed(f"model call failed after {attempts} attempts: {describe_error(last) if last else 'unknown'}")


async def _structured_browser(
    *, model: str, system: str, user: str, schema: type[T], usage: Usage, step: str, max_output_tokens: int,
    attempts: int, settings: Settings,
) -> T:
    """A model reached through a BrowserBridge (see bridge.py). Free; validated like any output."""
    if usage.bridge is None:
        raise ConfigError("browser model used without a browser bridge")
    payload = {"model": model.removeprefix(BROWSER_PREFIX), "system": system, "user": user,
               "schema": schema.model_json_schema(), "max_output_tokens": max_output_tokens}
    prompt = f"{system}\n\n{user}"
    base = {"step": step, "model": model, "reasoning_effort": None,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "prompt_chars": len(prompt), "images": 0,
            "prompt_text": prompt if settings.store_prompts else None}
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        t0 = time.monotonic()
        entry = {**base, "attempt": attempt, "status": "error", "error": None, "response": None,
                 "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0}
        try:
            text = await usage.bridge.call(payload)
            usage.calls += 1
            text = text.strip()
            if text.startswith("```"):  # some local models wrap JSON in a code fence
                text = text.strip("`").removeprefix("json").strip()
            parsed = schema.model_validate_json(text)
            entry["status"], entry["response"] = "ok", parsed.model_dump()
            return parsed
        except Exception as exc:  # noqa: BLE001 - retried, then surfaced
            last = exc
            entry["error"] = describe_error(exc)
            logger.warning("browser model attempt %s failed: %s", attempt, entry["error"])
        finally:
            entry["latency_ms"] = int((time.monotonic() - t0) * 1000)
            await usage.record(entry)
    raise LlmCallFailed(f"local model call failed after {attempts} attempts: {describe_error(last) if last else 'unknown'}")
