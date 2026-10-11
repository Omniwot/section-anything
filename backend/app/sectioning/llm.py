"""OpenAI calls with schema-validated output and cost accounting.

Separate from app.core.llm: sectioning needs structured outputs, usage for
cost, and GPT-5 parameters (no temperature, max_completion_tokens,
reasoning_effort) that the template's generic LiteLLM wrapper doesn't pass.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class CostCapExceeded(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    priced: bool = True
    per_call: list[dict] = field(default_factory=list)

    def add(self, model: str, usage) -> None:
        if usage is None:
            return
        cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
        inp, out = usage.prompt_tokens or 0, usage.completion_tokens or 0
        price = settings.model_prices.get(model)
        cost = 0.0
        if price:
            cost = ((inp - cached) * price["input"] + cached * price["cached"] + out * price["output"]) / 1e6
        else:
            self.priced = False
        self.calls += 1
        self.input_tokens += inp
        self.cached_tokens += cached
        self.output_tokens += out
        self.reasoning_tokens += reasoning
        self.cost_usd += cost
        self.per_call.append({"input": inp, "cached": cached, "output": out, "reasoning": reasoning, "cost": round(cost, 5)})

    def summary(self) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "cached_tokens": self.cached_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cost_usd": round(self.cost_usd, 4) if self.priced else None,
        }


def _client():
    # Langfuse's drop-in client traces every call when keys are configured.
    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        from langfuse.openai import AsyncOpenAI
    else:
        from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.SECTIONING_LLM_TIMEOUT_SECONDS)


async def structured(
    *,
    model: str,
    system: str,
    user: str,
    schema: type[T],
    usage: Usage,
    cost_cap_usd: float,
    effort: str | None = "low",
    max_output_tokens: int = 32_000,
    attempts: int = 2,
    images: list[str] | None = None,
) -> T:
    """One schema-constrained completion. Retries once on refusal or an
    unparsable response; raises CostCapExceeded before spending past the cap."""
    if usage.priced and usage.cost_usd >= cost_cap_usd:
        raise CostCapExceeded(f"Run stopped at ${usage.cost_usd:.2f} (cap ${cost_cap_usd:.2f}).")
    content: list[dict] | str = user
    if images:
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": url, "detail": "high"}} for url in images
        ]
    kwargs = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        "response_format": schema,
        "max_completion_tokens": max_output_tokens,
    }
    if effort:
        kwargs["reasoning_effort"] = effort
    client = _client()
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            resp = await client.chat.completions.parse(**kwargs)
            usage.add(model, resp.usage)
            msg = resp.choices[0].message
            if msg.refusal:
                raise ValueError(f"model refused: {msg.refusal[:200]}")
            if msg.parsed is None:
                raise ValueError(f"unparsable response (finish={resp.choices[0].finish_reason})")
            return msg.parsed
        except CostCapExceeded:
            raise
        except Exception as exc:  # noqa: BLE001 — retried, then surfaced
            last = exc
            logger.warning("sectioning LLM attempt %s failed: %s", attempt, exc)
    raise RuntimeError(f"LLM call failed after {attempts} attempts: {last}")
