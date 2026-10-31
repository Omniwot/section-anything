"""Many PDFs: `section_many(pdfs, mode)` -> one `DocumentResult` per PDF, with a total budget.

Documents run one at a time. Extraction already runs in a worker process, and one document at a
time keeps a laptop usable and the total budget exact: each document's cap is what is left after
the documents before it.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from section_anything.api import Progress, SectionTree, _settings_for, asection, resolve_mode, section
from section_anything.errors import ConfigError, CostCapExceeded, SectionAnythingError
from section_anything.llm import Usage

ON_ERROR = ("record", "raise")


@dataclass(frozen=True)
class DocumentResult:
    """One PDF of a `section_many` run: its tree, or the error that stopped it."""

    path: Path
    tree: SectionTree | None
    error: SectionAnythingError | None  # the exception: type(error).__name__ and str(error)
    cost_usd: float  # what this document's model calls cost, including those of a run that failed
    max_usd: float  # the per-document cap it ran with, after the total budget lowered it

    @property
    def ok(self) -> bool:
        return self.error is None


class _Batch:
    """Budget and error bookkeeping shared by `section_many` and `asection_many`."""

    def __init__(self, pdfs: Iterable[str | os.PathLike[str]], mode: str, max_usd_total: float | None,
                 on_error: str, progress: Progress | None, kwargs: dict[str, Any]) -> None:
        if isinstance(pdfs, str | bytes | os.PathLike):
            raise TypeError("pdfs is a list of paths; for a folder, pass sorted(Path(folder).glob('*.pdf'))")
        if on_error not in ON_ERROR:
            raise ConfigError(f"on_error must be 'record' or 'raise', not {on_error!r}")
        if max_usd_total is not None and not max_usd_total >= 0:  # also refuses NaN
            raise ConfigError(f"max_usd_total must be 0 or more, not {max_usd_total!r}")
        self.paths = [Path(p) for p in pdfs]
        self.mode, self.total, self.on_error, self.progress, self.kwargs = mode, max_usd_total, on_error, progress, kwargs
        s = _settings_for(kwargs.get("settings"), max_usd_per_doc=kwargs.get("max_usd"),
                          prices=kwargs.get("prices"), over_budget=kwargs.get("over_budget"))
        self.base_cap = s.max_usd_per_doc
        _mode, model = resolve_mode(mode, s, kwargs.get("model"))  # an unknown mode is refused here
        price = s.price_for(model) if model else None
        # A paid run that would be refused rather than downgraded once the total is spent.
        self.refuses = s.over_budget == "fail" and price is not None and (price.input > 0 or price.output > 0)
        self.spent = 0.0
        self.cap = self.base_cap
        self._unread = False

    def options(self, k: int, usage: Usage) -> dict[str, Any] | None:
        """`section` options for document `k`, or None when the total budget is spent and the run
        would be refused anyway: then the PDF is not read for nothing."""
        opts = {**self.kwargs, "_usage": usage}
        self.cap, self._unread = self.base_cap, False
        if self.total is not None:
            left = self.total - self.spent
            self.cap = opts["max_usd"] = min(self.base_cap, max(0.0, left))
            if left <= 0 and self.refuses:
                self._unread = True
                return None
        if self.progress is not None:
            report, n, name = self.progress, len(self.paths), self.paths[k].name
            opts["progress"] = lambda f, msg: report((k + f) / n, f"{name} ({k + 1} of {n}): {msg}")
        return opts

    def _more(self) -> str:
        return f"{max((self.total or 0.0) * 2, 0.5):.2f}"

    def spent_out(self) -> CostCapExceeded:
        more = self._more()
        return CostCapExceeded(
            f"the ${self.total:.2f} total budget is spent (${self.spent:.4f} so far), so the PDF was not read "
            f"(a safety limit; to allow more, use --max-usd-total {more}, or max_usd_total={more} in Python)")

    def success(self, path: Path, tree: SectionTree, usage: Usage) -> DocumentResult:
        self.spent += usage.cost_usd
        return DocumentResult(path, tree, None, usage.cost_usd, self.cap)

    def failure(self, path: Path, exc: SectionAnythingError, usage: Usage) -> DocumentResult:
        """Record `exc`, or raise it: a configuration error is about the setup, not the document, and
        would fail every document the same way, so it is always raised."""
        self.spent += usage.cost_usd
        err = exc
        if isinstance(exc, CostCapExceeded) and self.total is not None and self.cap < self.base_cap and not self._unread:
            more = self._more()
            err = CostCapExceeded(
                f"{exc} This document's cap was ${self.cap:.4f}, what was left of the ${self.total:.2f} total "
                f"budget (to allow more, use --max-usd-total {more}, or max_usd_total={more} in Python)")
        if isinstance(exc, ConfigError) or self.on_error == "raise":
            if err is exc:
                raise exc
            raise err from exc
        return DocumentResult(path, None, err, usage.cost_usd, self.cap)


def section_many(
    pdfs: Iterable[str | os.PathLike[str]],
    mode: str = "free",
    *,
    max_usd_total: float | None = None,
    on_error: str = "record",
    progress: Progress | None = None,
    **section_kwargs: Any,
) -> Iterator[DocumentResult]:
    """Section many PDFs, one at a time, in the order given.

    Returns an iterator: each document is read when you ask for its result, so results (and files
    you write from them) arrive as the run goes, only the current document is in memory unless you
    keep the trees, and stopping the loop stops the run. ``list(section_many(...))`` collects them.

    `section_kwargs` go to `section` (`model`, `max_usd`, `over_budget`, `settings`, `api_key`, ...).
    `max_usd_total` caps the whole run: each document's cap is the smaller of its own (`max_usd` or
    the configured one) and what is left of the total, so a paid mode is downgraded (standard ->
    quick -> free) or, with ``over_budget="fail"``, refused with `CostCapExceeded` as the budget runs
    out. What is spent counts every model call, including those of a document that then failed.
    Free and local modes never spend.

    `on_error="record"` keeps going: a document that fails with a `SectionAnythingError` gets a
    result with `error` set and `tree` None. ``"raise"`` raises the first such error. A
    `ConfigError` (unknown mode, no API key, a model with no price) is always raised, before any PDF
    is read. Other exceptions are not caught.

    `progress(fraction, message)` reports on the whole run: fraction of all documents, and a message
    naming the document. Documents run sequentially; extraction already runs in a worker process.
    """
    batch = _Batch(pdfs, mode, max_usd_total, on_error, progress, section_kwargs)

    def run() -> Iterator[DocumentResult]:
        for k, path in enumerate(batch.paths):
            usage = Usage()
            opts = batch.options(k, usage)
            try:
                if opts is None:
                    raise batch.spent_out()
                tree = section(path, mode, **opts)
            except SectionAnythingError as exc:
                result = batch.failure(path, exc, usage)
            else:
                result = batch.success(path, tree, usage)
            yield result

    return run()


def asection_many(
    pdfs: Iterable[str | os.PathLike[str]],
    mode: str = "free",
    *,
    max_usd_total: float | None = None,
    on_error: str = "record",
    progress: Progress | None = None,
    **section_kwargs: Any,
) -> AsyncIterator[DocumentResult]:
    """Async form of `section_many`: ``async for result in asection_many(pdfs): ...``. Documents
    still run one at a time."""
    batch = _Batch(pdfs, mode, max_usd_total, on_error, progress, section_kwargs)

    async def run() -> AsyncIterator[DocumentResult]:
        for k, path in enumerate(batch.paths):
            usage = Usage()
            opts = batch.options(k, usage)
            try:
                if opts is None:
                    raise batch.spent_out()
                tree = await asection(path, mode, **opts)
            except SectionAnythingError as exc:
                result = batch.failure(path, exc, usage)
            else:
                result = batch.success(path, tree, usage)
            yield result

    return run()
