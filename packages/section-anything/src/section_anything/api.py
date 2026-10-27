"""Public API: `section(pdf, mode)` -> `SectionTree`.

Modes, cheapest first:

- ``free``: no model. PDF bookmarks or the printed table of contents as the outline, then
  typography and numbering rules. Nothing leaves the machine.
- ``quick``: the rules propose candidate heading lines; a small model keeps the real ones and
  sets their levels. Sends only the candidate lines (plus a short peek at the next line).
- ``standard``: a model reads every line, with font hints, and marks where sections start and
  end. Sends the document text.
- ``local:<model>``: quick, answered by a local Ollama model. Free; nothing leaves the machine.

Costs: a cloud model with no known price is refused before anything is read. Before a paid mode
runs, its estimated cost is checked against the per-document cap (`max_usd`); a run over the cap
is downgraded (standard -> quick -> free) or refused (``over_budget="fail"``). While it runs, the
cap is re-checked before every call and each call's output is limited to what the remaining budget
can pay for.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import importlib.util
import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from section_anything.config import ANTHROPIC_EXTRA, LOCAL_PREFIX, Price, Settings
from section_anything.errors import ConfigError, CostCapExceeded, PdfError, UnpricedModelError
from section_anything.export import heading_text, markdown_hashes, section_bodies
from section_anything.extract import Extraction
from section_anything.isolate import extract_pdf
from section_anything.llm import Usage

MODES = ("free", "quick", "standard", "local")
STRATEGY = {"free": "rules", "quick": "llm_review", "standard": "llm_text", "local": "llm_review"}
DOWNGRADE = {"standard": "quick", "quick": "free", "local": None, "free": None}
SECTION_KEYS = ("number", "title", "level", "page_start", "page_end", "start", "end", "flags")

Progress = Callable[[float, str], None]


def resolve_mode(mode: str, settings: Settings, model: str | None = None) -> tuple[str, str | None]:
    """'free' | 'quick' | 'standard' | 'local:<ollama model>' -> (mode, model id or None).

    `model` replaces the configured model of a quick or standard run, or names the local model."""
    m = (mode or "free").strip()
    if m == "local" or m.startswith("local:"):
        tag = m.partition(":")[2].strip() or (model or "").strip() or settings.local_model.strip()
        if not tag:
            raise ConfigError("local mode needs a model: mode='local:<ollama model>' or SECTIONANY_LOCAL_MODEL")
        return "local", LOCAL_PREFIX + tag
    if m == "free":
        return "free", None
    if m == "quick":
        return "quick", model or settings.quick_model
    if m == "standard":
        return "standard", model or settings.standard_model
    raise ConfigError(f"unknown mode {m!r}: use free, quick, standard or local:<ollama model>")


def _require_price(mode: str, model: str | None, settings: Settings) -> Price | None:
    if model is None:
        return None
    price = settings.price_for(model)
    if price is None:
        raise UnpricedModelError(
            f"no price for model {model!r}: pass prices={{{model!r}: {{'input': ..., 'output': ...}}}} "
            "(USD per 1M tokens) or set SECTIONANY_PRICES, so the per-document cost cap can be enforced"
        )
    if mode in ("quick", "standard"):
        _require_provider(mode, model, settings)
    return price


def _require_provider(mode: str, model: str, settings: Settings) -> None:
    """A cloud model's client can be built: its key (and, for Claude, the anthropic extra) is there."""
    if settings.provider_for(model) == "anthropic":
        if importlib.util.find_spec("anthropic") is None:
            raise ConfigError(ANTHROPIC_EXTRA)
        if settings.api_key_for(model) is None:
            raise ConfigError(f"{mode} mode with {model!r} needs an Anthropic API key: set ANTHROPIC_API_KEY "
                              "or SECTIONANY_API_KEY, or pass api_key=")
    elif settings.api_key_for(model) is None:
        raise ConfigError(f"{mode} mode needs an API key: set SECTIONANY_API_KEY or pass api_key=")


@dataclass
class SectionTree:
    """The sections of one document, in reading order.

    `sections` holds one dict per section with number, title, level (1 = top), page_start,
    page_end, start and end (character offsets into `text`) and flags (for example
    ``doc_title``, ``front_matter``, ``start_marker_fuzzy``)."""

    sections: list[dict]
    mode: str
    model: str | None
    pages: int
    usage: dict
    seconds: float
    downgraded: list[str] = field(default_factory=list)
    extraction: Extraction | None = field(default=None, repr=False)
    resolved: list[dict] = field(default_factory=list, repr=False)  # full pipeline output

    @property
    def text(self) -> str:
        """The document text the character offsets refer to."""
        return self.extraction.text if self.extraction is not None else ""

    @property
    def cost_usd(self) -> float:
        return float(self.usage.get("cost_usd") or 0.0)

    def summary(self) -> dict:
        """Mode, model, size, calls, tokens and cost of the run."""
        return {
            "mode": self.mode,
            "model": self.model,
            "pages": self.pages,
            "sections": len(self.sections),
            "flagged": sum(bool(s["flags"]) for s in self.sections),
            "calls": self.usage.get("calls", 0),
            "input_tokens": self.usage.get("input_tokens", 0),
            "output_tokens": self.usage.get("output_tokens", 0),
            "cost_usd": self.cost_usd,
            "seconds": self.seconds,
            "downgraded": list(self.downgraded),
        }

    def to_markdown(self, body: bool = False) -> str:
        """Headings as Markdown: the document title (flag ``doc_title``) as '#', other headings
        as '#' x (level + 1), capped at six. With `body`, each heading is followed by its section's
        text reflowed into paragraphs; otherwise front matter is left out."""
        out: list[str] = []
        if body and self.extraction is not None and self.resolved:
            from section_anything.structure import furniture_of

            bodies = section_bodies(self.extraction, self.resolved, furniture_of(self.extraction))
            for sec, paras in zip(self.resolved, bodies, strict=True):
                if "front_matter" not in sec["flags"]:
                    out.append(f"{markdown_hashes(sec)} {heading_text(sec)}")
                out.extend(paras)
            return "\n\n".join(out) + "\n"
        for sec in self.sections:
            if "front_matter" in sec["flags"]:
                continue
            out.append(f"{markdown_hashes(sec)} {heading_text(sec)}")
        return "\n".join(out) + ("\n" if out else "")

    def to_dict(self) -> dict:
        from section_anything import __version__

        return {"section_anything": __version__, **self.summary(), "usage": self.usage,
                "sections": self.sections}

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def _public(sec: dict) -> dict:
    out = {k: (list(sec[k]) if k == "flags" else sec[k]) for k in SECTION_KEYS}
    if sec.get("title_from_text") is False and "front_matter" not in out["flags"]:
        out["flags"].append("generated_title")
    return out


def _settings_for(settings: Settings | None, **overrides: Any) -> Settings:
    base = settings if settings is not None else Settings()
    prices = overrides.pop("prices", None)
    if prices is not None:
        overrides["prices"] = {m: Price.model_validate(p) for m, p in dict(prices).items()}
    return base.with_overrides(**overrides)


async def asection(
    pdf_path: str | os.PathLike[str],
    mode: str = "free",
    *,
    settings: Settings | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    max_usd: float | None = None,
    prices: Mapping[str, Mapping[str, float] | Price] | None = None,
    over_budget: str | None = None,
    max_pages: int | None = None,
    extract_timeout: float | None = None,
    progress: Progress | None = None,
) -> SectionTree:
    """Async form of `section`."""
    from section_anything import pipeline

    s = _settings_for(settings, api_key=api_key, base_url=base_url, provider=provider, max_usd_per_doc=max_usd,
                      prices=prices, over_budget=over_budget, max_pages=max_pages,
                      extract_timeout_seconds=extract_timeout)
    mode, model = resolve_mode(mode, s, model)
    _require_price(mode, model, s)  # before the PDF is read: a refused run costs nothing
    report = progress or (lambda _f, _m: None)

    t0 = time.monotonic()
    ext = await asyncio.to_thread(
        extract_pdf, Path(pdf_path), settings=s,
        on_page=lambda n, total: report(0.5 * n / total, f"Reading page {n} of {total}"),
    )
    if not ext.text.strip():
        raise PdfError("no text layer: the PDF needs OCR first")

    cap = s.max_usd_per_doc
    usage = Usage()  # one tally per document: a downgrade continues the same budget
    downgraded: list[str] = []
    while True:
        strategy = pipeline.BY_ID[STRATEGY[mode]]
        price = s.price_for(model) if model else None
        if model and price is not None and strategy.uses_llm:
            est = strategy.estimate(ext)
            usd = price.estimate(est.input_tokens, est.output_tokens, est.calls)
            if usage.cost_usd + usd > cap:
                note = f"{mode}: estimated ${usd:.2f}, over the ${cap:.2f} per-document cap"
                if s.over_budget == "fail" or DOWNGRADE[mode] is None:
                    raise CostCapExceeded(f"{note} (max_usd, SECTIONANY_MAX_USD_PER_DOC)")
                downgraded.append(note)
                mode, model = _next_mode(mode, s, downgraded)
                continue

        def stage(f: float, msg: str) -> None:
            report(0.5 + 0.5 * f, msg)

        try:
            _raw, resolved, _metrics = await pipeline.run(
                ext, strategy.id, model or "", cap, stage, usage=usage, settings=s)
        except CostCapExceeded as exc:
            if s.over_budget == "fail" or DOWNGRADE[mode] is None:
                raise
            downgraded.append(f"{mode}: {exc}")
            mode, model = _next_mode(mode, s, downgraded)
            continue
        return SectionTree(
            sections=[_public(x) for x in resolved], mode=mode, model=model, pages=len(ext.pages),
            usage=usage.summary(), seconds=round(time.monotonic() - t0, 2), downgraded=downgraded,
            extraction=ext, resolved=resolved,
        )


def _next_mode(mode: str, s: Settings, notes: list[str]) -> tuple[str, str | None]:
    nxt = DOWNGRADE[mode]
    while nxt is not None:
        nxt_mode, nxt_model = resolve_mode(nxt, s)
        if nxt_model is None:
            return nxt_mode, nxt_model
        if s.price_for(nxt_model) is None:
            notes.append(f"{nxt}: skipped, no price for model {nxt_model!r}")
        else:
            try:  # the next mode's model can be on another provider, with no key configured
                _require_provider(nxt_mode, nxt_model, s)
                return nxt_mode, nxt_model
            except ConfigError as exc:
                notes.append(f"{nxt}: skipped, {exc}")
        nxt = DOWNGRADE[nxt]
    raise ConfigError("no mode left to downgrade to")  # unreachable: free is always available


def section(
    pdf_path: str | os.PathLike[str],
    mode: str = "free",
    **opts: Any,
) -> SectionTree:
    """Find the sections of a PDF.

    `mode` is "free", "quick", "standard" or "local:<ollama model>". Options (each overrides the
    matching ``SECTIONANY_*`` environment variable): `api_key`, `base_url`, `model`, `provider`
    ("openai" or "anthropic"; by default ``claude-*`` models use Anthropic), `max_usd`
    (per-document cap), `prices` ({model: {"input", "output"}} USD per 1M tokens, merged with the
    built-in list), `over_budget` ("downgrade" or "fail"), `max_pages`, `extract_timeout`
    (seconds), `progress` (callback(fraction, message)) and `settings` (a `Settings` object).
    """
    coro = asection(pdf_path, mode, **opts)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Called from inside an event loop (a notebook, an async app): run on a separate thread.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
