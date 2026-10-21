"""`section_anything.llm` with the app's settings injected.

Separate from app.core.llm: sectioning needs structured outputs, usage for cost, and GPT-5-style
parameters (no temperature, max_completion_tokens, reasoning_effort) that the template's generic
LiteLLM wrapper doesn't pass.
"""

from __future__ import annotations

from typing import Any

from section_anything import llm as _core
from section_anything.llm import LOCAL_PREFIX, CallSink, CostCapExceeded, LlmCallFailed, Usage

from app.core.config import settings

__all__ = ["LOCAL_PREFIX", "CallSink", "CostCapExceeded", "LlmCallFailed", "Usage", "price_of", "structured"]


def price_of(model: str, inp: int, cached: int, out: int) -> float | None:
    return _core.price_of(model, inp, cached, out, settings.sectioning_settings())


async def structured(**kwargs: Any):
    """`section_anything.llm.structured`, using the app's settings unless `settings` is given."""
    kwargs.setdefault("settings", settings.sectioning_settings())
    return await _core.structured(**kwargs)
