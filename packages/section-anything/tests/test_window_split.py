"""Standard reads a window as two halves when its answer is cut off at the output limit (research
finding F051). Fake model only."""

from __future__ import annotations

import asyncio

import pytest

from section_anything.errors import LlmCallFailed
from section_anything.extract import Extraction, Line, Page
from section_anything.llm import Usage
from section_anything.strategies import llm_text
from section_anything.strategies.base import Context
from section_anything.strategies.llm_text import LlmTextStrategy, TextResult, TextSection

PER_PAGE = 40
PAGES = 8
CUT_OFF = "model call failed after 2 attempts: _BadOutput: answer cut off at max_tokens=32000"
WORDS = ("archive", "budget", "council", "deposit", "estate", "finance", "grant", "harbour",
         "inquiry", "journal", "licence", "market", "notice", "office", "permit", "quota")
TITLES = [f"Heading about the {w}" for w in WORDS[:PAGES]]


def _book(titles: list[str] = TITLES) -> Extraction:
    """Eight pages of body lines, each page opened by a bold heading (two per page for 16 titles)."""
    lines, cursor, rows = [], 0, []
    per = len(titles) // PAGES
    for p in range(1, PAGES + 1):
        for t in titles[(p - 1) * per:p * per]:
            rows.append((t, True, p))
            rows += [(f"Body line {k} of part {p}, in the regular face at body size.", False, p) for k in range(PER_PAGE // per - 1)]
    for i, (text, bold, page) in enumerate(rows):
        y0 = 850 - 14 * (i % PER_PAGE)
        lines.append(Line(i=i, page=page, text=text, x0=72, y0=y0, x1=72 + 5 * len(text), y1=y0 + 10,
                          size=10.0, bold=bold, start=cursor, end=cursor + len(text)))
        cursor += len(text) + 1
    pages = [Page(n=n, width=612, height=950, origin_x=0, origin_y=0, rotation=0, has_text=True) for n in range(1, PAGES + 1)]
    return Extraction(pages, lines, "\n".join(r[0] for r in rows))


def _answer(user: str) -> TextResult:
    out = []
    for row in user.split("\n"):
        num, sep, rest = row.partition("| ")
        if sep and num.isdigit() and rest.startswith("⟨B⟩ "):
            title = rest.removeprefix("⟨B⟩ ")
            out.append(TextSection(start_line=int(num), number="", title=title, title_from_text=True, level=1,
                                   start_marker=title, end_marker=""))
    return TextResult(sections=out)


def _run(monkeypatch, max_lines: int, error: str = CUT_OFF):
    """A model whose answer is cut off for a slice of more than `max_lines` lines."""
    calls = []

    async def fake(**kw):
        n = sum(1 for r in kw["user"].split("\n") if r.partition("| ")[0].isdigit())
        calls.append(n)
        if n > max_lines:
            raise LlmCallFailed(error)
        return _answer(kw["user"])

    monkeypatch.setattr(llm_text, "structured", fake)
    ctx = Context(model="fake", usage=Usage(), cost_cap_usd=1.0)
    return asyncio.run(LlmTextStrategy().run(_book(), ctx)), ctx.usage, calls


def test_a_cut_off_window_is_read_as_two_halves(monkeypatch):
    found, usage, calls = _run(monkeypatch, max_lines=200)
    assert [s.title for s in found] == TITLES
    assert calls == [320, 160, 160]
    (split,) = usage.window_splits
    # Split at the page break nearest the middle: page 5 starts at line 160.
    assert split == {"lines": [0, 319], "halves": [[0, 159], [160, 319]]}
    assert usage.summary()["window_splits"] == [split]


def test_halves_are_split_again_while_long_enough(monkeypatch):
    found, usage, calls = _run(monkeypatch, max_lines=100)
    assert len(found) == PAGES and calls == [320, 160, 80, 80, 160, 80, 80]
    assert len(usage.window_splits) == 3


def test_a_window_too_short_to_split_fails(monkeypatch):
    with pytest.raises(LlmCallFailed):
        _run(monkeypatch, max_lines=50)


def test_other_failures_are_not_split(monkeypatch):
    with pytest.raises(LlmCallFailed):
        _run(monkeypatch, max_lines=200, error="model call failed after 2 attempts: APIConnectionError")


def test_a_cut_off_coverage_re_read_reads_the_window_as_two_halves(monkeypatch):
    # The first answer lists only the first of 16 headings; the re-read of the whole window is cut
    # off; each half is then read in full.
    titles = [f"Heading about the {w}" for w in WORDS]
    calls = []

    async def fake(**kw):
        n = sum(1 for r in kw["user"].split("\n") if r.partition("| ")[0].isdigit())
        calls.append((n, kw["step"].endswith("(coverage)")))
        if n == PAGES * PER_PAGE:
            if kw["step"].endswith("(coverage)"):
                raise LlmCallFailed(CUT_OFF)
            first = _answer(kw["user"]).sections[:1]
            return TextResult(sections=first)
        return _answer(kw["user"])

    monkeypatch.setattr(llm_text, "structured", fake)
    ctx = Context(model="fake", usage=Usage(), cost_cap_usd=1.0)
    found = asyncio.run(LlmTextStrategy().run(_book(titles), ctx))
    assert [s.title for s in found] == titles
    assert calls == [(320, False), (320, True), (160, False), (160, False)]
    assert ctx.usage.coverage_retries[0]["kept"] == "halves"
    assert ctx.usage.window_splits == [{"lines": [0, 319], "halves": [[0, 159], [160, 319]]}]
