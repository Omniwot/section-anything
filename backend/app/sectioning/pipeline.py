"""`section_anything.pipeline` with the app's settings injected into runs."""

from __future__ import annotations

from collections.abc import Callable

from section_anything import pipeline as _core
from section_anything.extract import Extraction
from section_anything.llm import Usage
from section_anything.pipeline import (
    BY_ID,
    FRONT_MATTER_MIN_CHARS,
    STRATEGIES,
    estimates,
    finish,
    mark_doc_title,
    metrics,
    resolve,
)
from section_anything.strategies.base import RawSection

from app.core.config import settings

__all__ = [
    "BY_ID",
    "FRONT_MATTER_MIN_CHARS",
    "STRATEGIES",
    "estimates",
    "finish",
    "mark_doc_title",
    "metrics",
    "resolve",
    "run",
]


async def run(
    ext: Extraction,
    strategy_id: str,
    model: str,
    cost_cap_usd: float,
    progress: Callable[[float, str], None] | None = None,
    usage: Usage | None = None,
) -> tuple[list[RawSection], list[dict], dict]:
    """`section_anything.pipeline.run` with the app's model key, prices and timeouts."""
    return await _core.run(ext, strategy_id, model, cost_cap_usd, progress, usage=usage,
                           settings=settings.sectioning_settings())
