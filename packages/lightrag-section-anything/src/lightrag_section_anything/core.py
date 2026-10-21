"""Bridge to the Section Anything sectioning core, with per-document budgets.

The core still lives in ``section-anything/backend`` (``app.sectioning``); until it is packaged,
``SECTIONANY_BACKEND`` must point at that folder. Everything here runs synchronously inside
LightRAG's parser thread.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MODES = ("free", "quick", "standard", "local")
STRATEGY = {"free": "rules", "quick": "llm_review", "standard": "llm_text", "local": "llm_review"}
DOWNGRADE = {"standard": "quick", "quick": "free", "local": "free", "free": None}


def _core():
    """Import the sectioning core lazily (it reads its settings at import time)."""
    backend = os.getenv("SECTIONANY_BACKEND")
    if backend and backend not in sys.path:
        sys.path.insert(0, backend)
    try:
        from app.core.config import settings
        from app.sectioning import pipeline
        from app.sectioning.extract import extract
        from app.sectioning.llm import CostCapExceeded, Usage
    except ImportError as e:  # pragma: no cover - configuration error
        raise RuntimeError("Section Anything core not importable: set SECTIONANY_BACKEND to section-anything/backend") from e
    if os.getenv("SECTIONANY_API_KEY"):
        # Hand the key to the sectioning settings only; never write it into the shared process
        # environment, where the host (LightRAG's own LLM calls) would pick it up.
        settings.OPENAI_API_KEY = os.environ["SECTIONANY_API_KEY"]
    return settings, pipeline, extract, CostCapExceeded, Usage


def resolve_mode(mode: str | None) -> tuple[str, str | None]:
    """'free' | 'quick' | 'standard' | 'local:<ollama model>' -> (mode, local model)."""
    mode = (mode or os.getenv("SECTIONANY_MODE") or "free").strip()
    if mode.startswith("local"):
        model = mode.partition(":")[2] or os.getenv("SECTIONANY_LOCAL_MODEL", "")
        if not model:
            raise ValueError("local mode needs a model: SECTIONANY_MODE=local:<model> or SECTIONANY_LOCAL_MODEL")
        return "local", model
    if mode not in MODES:
        raise ValueError(f"unknown SECTIONANY_MODE {mode!r}; use free, quick, standard or local:<model>")
    return mode, None


@dataclass
class Result:
    ext: Any
    sections: list[dict]
    mode: str
    model: str | None
    cost_usd: float = 0.0
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0
    downgraded: list[str] = field(default_factory=list)


def section_pdf(path: Path, mode: str | None = None, *, max_pages: int | None = None) -> Result:
    settings, pipeline, extract, CostCapExceeded, Usage = _core()
    mode, local_model = resolve_mode(mode)
    cap = float(os.getenv("SECTIONANY_MAX_USD_PER_DOC", "0.50"))
    strict = os.getenv("SECTIONANY_OVER_BUDGET", "downgrade") == "fail"
    max_pages = max_pages or int(os.getenv("SECTIONANY_MAX_PAGES", "500"))

    t0 = time.monotonic()
    ext = extract(path)
    if len(ext.pages) > max_pages:
        raise ValueError(f"{len(ext.pages)} pages is over SECTIONANY_MAX_PAGES={max_pages}")
    if not ext.text.strip():
        raise ValueError("no text layer; re-upload with an OCR engine, e.g. name.[mineru-P].pdf")

    downgraded: list[str] = []
    usage = Usage()  # one tally per document: a downgrade continues the same budget
    while True:
        sid = STRATEGY[mode]
        model = None
        if mode == "quick":
            model = os.getenv("SECTIONANY_QUICK_MODEL") or settings.model_for("llm_review")
        elif mode == "standard":
            model = os.getenv("SECTIONANY_STANDARD_MODEL") or settings.model_for("llm_text")
        elif mode == "local":
            model = f"ollama/{local_model}"
        price = settings.model_prices.get(model) if model else None
        if model and not price and not model.startswith("ollama/"):
            raise ValueError(f"no price for model {model!r}: add it to MODEL_PRICES_JSON so the per-document cap applies")
        if model and price:
            est = pipeline.BY_ID[sid].estimate(ext)
            usd = (est.input_tokens * price["input"] + est.output_tokens * price["output"]) / 1e6
            if usage.cost_usd + usd > cap:
                if strict or DOWNGRADE[mode] is None:
                    raise ValueError(f"{mode} estimated ${usd:.2f}, over SECTIONANY_MAX_USD_PER_DOC=${cap:.2f}")
                downgraded.append(f"{mode}: estimate ${usd:.2f} over cap ${cap:.2f}")
                mode = DOWNGRADE[mode]
                continue
        try:
            _raw, sections, _metrics = asyncio.run(
                pipeline.run(ext, sid, model or "", cap if model else 0.0, usage=usage))
        except CostCapExceeded as e:
            if strict or DOWNGRADE[mode] is None:
                raise
            downgraded.append(f"{mode}: {e}")
            mode = DOWNGRADE[mode]
            continue
        return Result(ext=ext, sections=sections, mode=mode, model=model, cost_usd=round(usage.cost_usd, 6),
                      calls=usage.calls, tokens_in=usage.input_tokens, tokens_out=usage.output_tokens,
                      seconds=round(time.monotonic() - t0, 2), downgraded=downgraded)
