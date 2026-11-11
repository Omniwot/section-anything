"""Public API: `section(pdf, mode)` -> `SectionTree`. `pdf` is a path, or the PDF itself as bytes
or a binary file-like object.

Modes, cheapest first:

- ``free``: no model. PDF bookmarks or the printed table of contents as the outline, then
  typography and numbering rules. Nothing leaves the machine.
- ``quick``: the rules propose candidate heading lines; a small model keeps the real ones and
  sets their levels. Sends only the candidate lines (plus a short peek at the next line).
- ``standard``: a model reads every line, with font hints, and marks where sections start and
  end. Sends the document text.
- ``local:<model>``: quick, answered by a local Ollama model. Free; nothing leaves the machine.
- ``auto``: free first, then quick only when Free is unsure of its headings (fewer than three, or
  their mean ``confidence`` below ``Settings.auto_threshold``). Most documents cost nothing.

Costs: a cloud model with no known price is refused before anything is read. Before a paid mode
runs, its estimated cost is checked against the per-document cap (`max_usd`); a run over the cap
is downgraded (standard -> quick -> free; an explicit `model` stays with the run) or refused
(``over_budget="fail"``). While it runs, the cap is re-checked before every call and each call's
output is limited to what the remaining budget can pay for.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import importlib.util
import json
import math
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NotRequired

from typing_extensions import TypedDict  # pydantic needs typing_extensions' TypedDict before Python 3.12

from section_anything.config import ANTHROPIC_EXTRA, LOCAL_PREFIX, Price, Settings
from section_anything.errors import (
    ConfigError,
    CostCapExceeded,
    PdfError,
    UnpricedModelError,
    limit_hint,
    too_many_pages,
    too_much_text,
)
from section_anything.export import heading_boxes, heading_text, markdown_hashes, section_bodies
from section_anything.extract import Extraction
from section_anything.isolate import PdfInput, extract_pdf
from section_anything.llm import Usage

if TYPE_CHECKING:
    from docling_core.types.doc import DoclingDocument

    from section_anything.chunking import Chunk

MODES = ("free", "quick", "standard", "local", "auto")
STRATEGY = {"free": "rules", "quick": "llm_review", "standard": "llm_text", "local": "llm_review"}
DOWNGRADE = {"standard": "quick", "quick": "free", "local": None, "free": None}
SECTION_KEYS = ("number", "title", "level", "page_start", "page_end", "start", "end", "flags", "confidence")
LINK_KEYS = ("parent", "heading_path")  # derived from the levels by `SectionTree`
BOX_KEYS = ("heading_bbox",)  # derived from the extraction by `SectionTree`

Progress = Callable[[float, str], None]


class HeadingBox(TypedDict):
    """Where a section's heading is printed: its page and box in PDF points from the page's
    bottom-left corner (the union box of a heading that wraps onto several lines)."""

    page: int  # 1-based physical page
    x0: float
    y0: float
    x1: float
    y1: float


class Section(TypedDict):
    """One section of `SectionTree.sections`, in reading order."""

    number: str  # numbering as printed ("2.3", "Chapter 4") or ""
    title: str
    level: int  # 1 = top level
    page_start: int  # 1-based physical pages
    page_end: int
    start: int  # character range of the section's own text in `SectionTree.text`
    end: int
    flags: list[str]
    confidence: float | None  # Free only: 0-1, how much of Free's evidence backs this heading; else None
    parent: int | None  # index of the nearest enclosing section, or None
    heading_path: list[str]  # headings from the outermost enclosing section down to this one
    heading_bbox: HeadingBox | None  # None: no printed heading (front matter, a model-written title) or no geometry
    text: NotRequired[str]  # only from `to_dict(text=True)`: text[start:end]


class AutoInfo(TypedDict):
    """Mode "auto": which mode ran and why."""

    path: str  # "free", or "quick" when Free was unsure (or what a downgrade left)
    reason: str
    confidence: float  # Free's document confidence: mean heading confidence, 0 with under three headings
    threshold: float


class PossibleMiss(TypedDict):
    """A line with heading evidence that the result does not have as a heading (`possible_misses`)."""

    page: int | None  # None: a contents entry that names no page and was not found
    text: str
    evidence: list[str]
    score: float  # 0-1, for ranking


class TreeDict(TypedDict):
    """What `SectionTree.to_dict()` returns and `to_json()` writes."""

    section_anything: str  # library version
    mode: str  # after any downgrade
    model: str | None
    pages: int
    sections: list[Section]
    flagged: int
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    seconds: float
    downgraded: list[str]
    auto: NotRequired[AutoInfo]  # only from mode "auto"
    usage: dict[str, Any]
    possible_misses: list[PossibleMiss]


def link_sections(sections: list[dict]) -> None:
    """Set each section's `parent` (index of the nearest enclosing section, or None) and
    `heading_path` (headings from the outermost enclosing section down to this one, as
    "number title"). The document title (flag ``doc_title``) and front matter are outside the
    hierarchy: the title's path is the title alone, front matter's is empty, and neither is a
    parent. The LangChain and LlamaIndex loaders' `heading_path` follows the same rule."""
    open_: list[tuple[int, int]] = []  # (level, index) of the sections enclosing the next one
    for k, sec in enumerate(sections):
        flags = sec.get("flags") or []
        if "front_matter" in flags or "doc_title" in flags:
            sec["parent"] = None
            sec["heading_path"] = [heading_text(sec)] if "doc_title" in flags else []
            continue
        level = int(sec.get("level") or 1)
        open_ = [p for p in open_ if p[0] < level]
        parent = open_[-1][1] if open_ else None
        sec["parent"] = parent
        sec["heading_path"] = [*(sections[parent]["heading_path"] if parent is not None else []), heading_text(sec)]
        open_.append((level, k))


def resolve_mode(mode: str, settings: Settings, model: str | None = None) -> tuple[str, str | None]:
    """'free' | 'quick' | 'standard' | 'auto' | 'local:<ollama model>' -> (mode, model id or None).

    `model` replaces the configured model of a quick, standard or auto run, or names the local model."""
    m = (mode or "free").strip()
    if m == "local" or m.startswith("local:"):
        tag = m.partition(":")[2].strip() or (model or "").strip() or settings.local_model.strip()
        if not tag:
            raise ConfigError("local mode needs a model: mode='local:<ollama model>' or SECTIONANY_LOCAL_MODEL")
        return "local", LOCAL_PREFIX + tag
    if m == "free":
        return "free", None
    if m in ("quick", "auto"):
        return m, model or settings.quick_model
    if m == "standard":
        return "standard", model or settings.standard_model
    raise ConfigError(f"unknown mode {m!r}: use free, quick, standard, auto or local:<ollama model>")


def _require_price(mode: str, model: str | None, settings: Settings) -> Price | None:
    if model is None:
        return None
    price = settings.price_for(model)
    if price is None:
        raise UnpricedModelError(
            f"no price for model {model!r}: pass prices={{{model!r}: {{'input': ..., 'output': ...}}}} "
            "(USD per 1M tokens) or set SECTIONANY_PRICES, so the per-document cost cap can be enforced"
        )
    if mode in ("quick", "standard", "auto"):
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

    `sections` holds one dict per section (`Section`) with number, title, level (1 = top),
    page_start, page_end, start and end (character offsets into `text`), flags (for example
    ``doc_title``, ``front_matter``, ``start_marker_fuzzy``, ``from_contents``), confidence (Free
    only), parent, heading_path and heading_bbox (where the heading is printed: `HeadingBox`, or
    None). `auto` says which mode a mode "auto" run took and why.
    `possible_misses` lists, best first, the lines with heading evidence that are not headings of
    the result (`PossibleMiss`), and the contents entries the contents check could not find."""

    sections: list[Section]
    mode: str
    model: str | None
    pages: int
    usage: dict
    seconds: float
    downgraded: list[str] = field(default_factory=list)
    extraction: Extraction | None = field(default=None, repr=False)
    resolved: list[dict] = field(default_factory=list, repr=False)  # full pipeline output
    auto: AutoInfo | None = None
    possible_misses: list[PossibleMiss] = field(default_factory=list)

    def __post_init__(self) -> None:
        links = any(k not in s for s in self.sections for k in LINK_KEYS)
        boxes = any(k not in s for s in self.sections for k in BOX_KEYS)
        if links or boxes:
            self.sections = [dict(s) for s in self.sections]  # type: ignore[misc]
        if links:
            link_sections(self.sections)  # type: ignore[arg-type]
        if boxes:
            found = self._heading_boxes()
            for sec, box in zip(self.sections, found, strict=True):
                sec.setdefault("heading_bbox", box)

    def _heading_boxes(self) -> list[HeadingBox | None]:
        """Each heading's printed box from the extraction; all None for a tree built by hand."""
        if self.extraction is None or len(self.resolved) != len(self.sections):
            return [None] * len(self.sections)
        from section_anything.structure import furniture_of

        return heading_boxes(self.extraction, self.resolved, furniture_of(self.extraction))  # type: ignore[return-value]

    @property
    def text(self) -> str:
        """The document text the character offsets refer to."""
        return self.extraction.text if self.extraction is not None else ""

    @property
    def cost_usd(self) -> float:
        return float(self.usage.get("cost_usd") or 0.0)

    def summary(self) -> dict:
        """Mode, model, size, calls, tokens and cost of the run (and `auto`, for mode "auto")."""
        out = {
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
        if self.auto is not None:
            out["auto"] = dict(self.auto)
        return out

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

    def to_dict(self, text: bool = False) -> TreeDict:
        """The run summary, usage and sections (`TreeDict`). With `text`, each section also
        carries `text`: ``self.text[start:end]``, its own text exactly as extracted, from its
        heading up to the next heading of any level."""
        from section_anything import __version__

        sections = [{**s, "text": self.text[s["start"]:s["end"]]} for s in self.sections] if text else self.sections
        return {"section_anything": __version__, **self.summary(), "usage": self.usage,  # type: ignore[typeddict-item]
                "sections": sections, "possible_misses": [dict(m) for m in self.possible_misses]}

    def to_json(self, indent: int | None = 2, text: bool = False) -> str:
        return json.dumps(self.to_dict(text=text), ensure_ascii=False, indent=indent)

    def to_unstructured_elements(self, filename: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
        """The sections as Unstructured element dicts (its JSON format), for its `chunk_by_title`.

        In reading order: a ``Title`` per heading (``category_depth`` 0 for the document title and
        level - 1 for the others, ``parent_id`` the enclosing heading's ``element_id``), then a
        ``NarrativeText`` per body paragraph (``parent_id`` its heading). Front matter has no
        ``Title`` and no ``parent_id``. Every element has ``page_number`` and, from the
        extraction, ``coordinates`` (PDF points, top-left origin, on its first page); ids are
        Unstructured's own deterministic hash. `filename` sets ``filename`` (and
        ``file_directory``). Load with ``unstructured.staging.base.elements_from_dicts``; no extra
        package is needed to export."""
        from section_anything.interop import unstructured_elements

        return unstructured_elements(self, filename)

    def to_docling_document(self, filename: str | os.PathLike[str] | None = None) -> DoclingDocument:
        """The sections as a Docling `DoclingDocument`, for its `HybridChunker`.

        The document title (flag ``doc_title``) is a ``TitleItem``; every other heading a
        ``SectionHeaderItem`` at its level, under its enclosing heading; body paragraphs are
        ``TextItem``s under their heading (front matter's at the top level). Items carry
        provenance (page, box, character span) from the extraction, one per page a paragraph
        is on. `filename` names the document and, when it is the PDF's path, sets ``origin``
        with Docling's file hash. Needs the docling extra (``docling-core``)."""
        from section_anything.interop import docling_document

        return docling_document(self, filename)

    def chunks(self, max_chars: int = 2000, min_chars: int = 200, *, overlap_chars: int = 0,
               length: Callable[[str], int] = len, prefix: bool = False) -> list[Chunk]:
        """Section-aware chunks with a size cap (`section_anything.chunk_sections`), in reading
        order. Each section's text is its body as `to_markdown(body=True)` prints it (reflowed
        into paragraphs, heading lines and running headers and footers removed); a section over
        `max_chars` is split on paragraph breaks, then sentence ends, then cut; sibling sections
        under `min_chars` are merged; a heading with no body is one chunk of its own. Every
        `Chunk` has `text`, `heading_path`, `section_index`, `chunk_index`, `page_start` and
        `page_end`, and `prefixed_text` ("3 Safety > 3.2 Storage\n\n..."); with `prefix`, `text`
        is that. Sizes are in units of `length` (`len`; pass a token counter to cap by tokens)."""
        from section_anything.chunking import chunk_sections

        if self.extraction is not None and self.resolved:
            from section_anything.structure import furniture_of

            bodies = section_bodies(self.extraction, self.resolved, furniture_of(self.extraction))
            secs = []
            for sec, paras in zip(self.sections, bodies, strict=True):
                head = "" if "front_matter" in sec["flags"] else heading_text(sec)
                secs.append({**sec, "text": "\n".join(p for p in (head, "\n\n".join(paras)) if p)})
        else:
            secs = [{**s, "text": self.text[s["start"]:s["end"]]} for s in self.sections]
        return chunk_sections(secs, max_chars=max_chars, min_chars=min_chars, overlap_chars=overlap_chars,
                              length=length, prefix=prefix)

    @staticmethod
    def json_schema() -> dict:
        """JSON Schema of `to_dict()` / `to_json()` output, for tool definitions and validation."""
        from pydantic import TypeAdapter

        return TypeAdapter(TreeDict).json_schema()


def _public(sec: dict) -> dict:
    out = {k: (list(sec[k]) if k == "flags" else sec.get(k) if k == "confidence" else sec[k]) for k in SECTION_KEYS}
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
    pdf_path: PdfInput | DoclingDocument | Mapping[str, Any],
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
    docling: DoclingDocument | Mapping[str, Any] | str | os.PathLike[str] | None = None,
    _usage: Usage | None = None,
) -> SectionTree:
    """Async form of `section`."""
    from section_anything import docling_input, pipeline

    s = _settings_for(settings, api_key=api_key, base_url=base_url, provider=provider, max_usd_per_doc=max_usd,
                      prices=prices, over_budget=over_budget, max_pages=max_pages,
                      extract_timeout_seconds=extract_timeout)
    override = model  # an explicit model stays with the run through a downgrade (`_next_mode`)
    mode, model = resolve_mode(mode, s, model)
    _require_price(mode, model, s)  # before the PDF is read: a refused run costs nothing
    report = progress or (lambda _f, _m: None)

    t0 = time.monotonic()
    if docling_input.is_docling_document(pdf_path):
        if docling is not None:
            raise ConfigError("docling= gives hints for a PDF's own lines; the input is already a Docling document")
        ext = await asyncio.to_thread(docling_input.extraction_from_docling, pdf_path)
        if len(ext.pages) > s.max_pages:
            raise too_many_pages(len(ext.pages), s.max_pages)
        if len(ext.text) > s.max_chars:
            raise too_much_text(s.max_chars, len(ext.text))
        if not ext.text.strip():
            raise PdfError("the Docling document has no text")
    else:
        ext = await asyncio.to_thread(
            extract_pdf, pdf_path, settings=s,
            on_page=lambda n, total: report(0.5 * n / total, f"Reading page {n} of {total}"),
        )
        if not ext.text.strip():
            raise PdfError("no text layer: the PDF needs OCR first (or pass Docling's output of it)")
        if docling is not None:
            await asyncio.to_thread(docling_input.attach_hints, ext, docling)

    cap = s.max_usd_per_doc
    # One tally per document: a downgrade continues the same budget. `section_many` passes its own
    # (`_usage`) so that it can count what a document spent even when the run then fails.
    usage = _usage if _usage is not None else Usage()
    downgraded: list[str] = []
    auto: AutoInfo | None = None
    if mode == "auto":
        _raw, resolved, metrics = await pipeline.run(
            ext, "rules", "", cap, lambda f, msg: report(0.5 + 0.1 * f, msg), usage=usage, settings=s)
        auto = _auto_choice(resolved, s.auto_threshold)
        if auto["path"] == "free":
            return SectionTree(
                sections=[_public(x) for x in resolved], mode="free", model=None, pages=len(ext.pages),
                usage=usage.summary(), seconds=round(time.monotonic() - t0, 2), extraction=ext, resolved=resolved,
                auto=auto, possible_misses=metrics.get("possible_misses", []),
            )
        mode = "quick"
    while True:
        strategy = pipeline.BY_ID[STRATEGY[mode]]
        price = s.price_for(model) if model else None
        if model and price is not None and strategy.uses_llm:
            est = strategy.estimate(ext, model, s)
            usd = price.estimate(est.input_tokens, est.output_tokens, est.calls)
            if usage.cost_usd + usd > cap:
                note = f"{mode}: estimated ${usd:.2f}, over the ${cap:.2f} per-document cap"
                if s.over_budget == "fail" or DOWNGRADE[mode] is None:
                    need = f"{math.ceil((usage.cost_usd + usd) * 100) / 100:.2f}"
                    raise CostCapExceeded(f"{note} " + limit_hint("SECTIONANY_MAX_USD_PER_DOC", need, flag="--max-usd",
                                                                   python=f"max_usd={need}"))
                downgraded.append(note)
                mode, model = _next_mode(mode, s, downgraded, override)
                continue

        def stage(f: float, msg: str) -> None:
            report(0.5 + 0.5 * f, msg)

        try:
            _raw, resolved, metrics = await pipeline.run(
                ext, strategy.id, model or "", cap, stage, usage=usage, settings=s)
        except CostCapExceeded as exc:
            if s.over_budget == "fail" or DOWNGRADE[mode] is None:
                raise
            downgraded.append(f"{mode}: {exc}")
            mode, model = _next_mode(mode, s, downgraded, override)
            continue
        if auto is not None:
            auto["path"] = mode
        return SectionTree(
            sections=[_public(x) for x in resolved], mode=mode, model=model, pages=len(ext.pages),
            usage=usage.summary(), seconds=round(time.monotonic() - t0, 2), downgraded=downgraded,
            extraction=ext, resolved=resolved, auto=auto, possible_misses=metrics.get("possible_misses", []),
        )


def _auto_choice(free: list[dict], threshold: float) -> AutoInfo:
    """Mode "auto": keep Free's sections, or escalate to Quick check when Free is unsure."""
    from section_anything.confidence import MIN_HEADINGS, document_confidence

    conf = document_confidence(free)
    heads = sum("front_matter" not in s["flags"] and "doc_title" not in s["flags"] for s in free)
    if heads < MIN_HEADINGS:
        path, reason = "quick", f"Free found {heads} heading{'s' if heads != 1 else ''} (under {MIN_HEADINGS})"
    elif conf < threshold:
        path, reason = "quick", f"Free is unsure: confidence {conf:.2f} < {threshold:.2f}"
    else:
        path, reason = "free", f"Free is sure: confidence {conf:.2f} >= {threshold:.2f}"
    return {"path": path, "reason": reason, "confidence": conf, "threshold": threshold}


def _next_mode(mode: str, s: Settings, notes: list[str], model: str | None = None) -> tuple[str, str | None]:
    """The next mode down from `mode` that can run, and its model. An explicit `model` (the `model=`
    argument or ``--model``) stays with the run: Standard on Claude Haiku 5.5 over the cap goes to Quick
    on Claude Haiku 5.5, not to Quick's configured model, which can be on a provider with no key
    (research finding F065). A mode whose model has no price or no key is skipped, with a note."""
    nxt = DOWNGRADE[mode]
    while nxt is not None:
        nxt_mode, nxt_model = resolve_mode(nxt, s, model)
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
    pdf_path: PdfInput | DoclingDocument | Mapping[str, Any],
    mode: str = "free",
    **opts: Any,
) -> SectionTree:
    """Find the sections of a PDF.

    `pdf_path` is a path, or the PDF itself as bytes, a bytearray, a memoryview or a binary
    file-like object such as an open file or `io.BytesIO` (read to the end once and left open).
    Bytes go through the same caps and isolated extraction as a path, from a private temporary
    file that is removed afterwards.

    `pdf_path` can also be a Docling `DoclingDocument` (the object, its JSON as a dict, or the path
    of a ``.json`` file): its text items are then the lines, so a scanned PDF works through
    Docling's OCR. `docling=` passes Docling's output of the same PDF (in any of those forms) as
    hints: its section headers become heading candidates and its page headers and footers
    furniture, while the PDF's own fonts, bookmarks and table of contents still count. Hints from
    another PDF are refused with `ConfigError`. docling-core is not needed for either.

    `mode` is "free", "quick", "standard", "auto" (free, then quick only when Free is unsure: see
    `SectionTree.auto`) or "local:<ollama model>". Options (each overrides the
    matching ``SECTIONANY_*`` environment variable): `api_key`, `base_url`, `model` (also used by
    a downgrade from standard to quick), `provider`
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
