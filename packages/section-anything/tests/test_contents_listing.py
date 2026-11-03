"""Standard and contents lists without page numbers: their entries are not section starts, and the
coverage check leaves them out, which lets it also count section titles set in bold at body size
(research finding F051). Fake model only."""

from __future__ import annotations

import asyncio

from section_anything import pipeline
from section_anything.extract import Extraction, Line, Page
from section_anything.llm import Usage
from section_anything.strategies import llm_text
from section_anything.strategies.base import Context
from section_anything.strategies.llm_text import LlmTextStrategy, TextResult, TextSection, _signals
from section_anything.structure import listing_of

WORDS = ("archive", "budget", "council", "deposit", "estate", "finance", "grant", "harbour", "inquiry", "journal",
         "licence", "market", "notice", "office", "permit", "quota", "record", "survey", "tariff", "union")
SECTIONS = len(WORDS)
TITLES = [f"Duties of the {w} registrar" for w in WORDS]


def _body(k: int) -> tuple[str, float, bool]:
    """A body line; each one differs, so none of them looks like a running header."""
    a, b = WORDS[k % SECTIONS], WORDS[(k // SECTIONS) % SECTIONS]
    return (f"Ordinary body text about the {a} and the {b} runs on in the regular face, line {k}.", 10.0, False)


def _doc(rows: list[tuple[str, float, bool]], per_page: int = 50) -> Extraction:
    lines, pages, cursor = [], [], 0
    for i, (text, size, bold) in enumerate(rows):
        page, y0 = i // per_page + 1, 850 - 14 * (i % per_page)
        lines.append(Line(i=i, page=page, text=text, x0=72, y0=y0, x1=72 + 0.5 * size * len(text), y1=y0 + size,
                          size=size, bold=bold, start=cursor, end=cursor + len(text)))
        cursor += len(text) + 1
    for n in range(1, lines[-1].page + 1):
        pages.append(Page(n=n, width=612, height=950, origin_x=0, origin_y=0, rotation=0, has_text=True))
    return Extraction(pages, lines, "\n".join(r[0] for r in rows))


def _act(labels: int = 0) -> Extraction:
    """An act: a contents list of plain lines with no page numbers, then the sections, each titled in
    bold at body size. `labels`: a bold "Penalty" line (a repeated label, not a title) in that many sections."""
    rows = [("CONTENTS OF ACT", 10.0, True)] + [(t, 10.0, False) for t in TITLES]
    for n, t in enumerate(TITLES):
        rows.append((t, 10.0, True))
        rows += [_body(len(rows) + k) for k in range(6)]
        if n < labels:
            rows += [("Penalty", 10.0, True), _body(len(rows) + 1)]
        rows += [_body(len(rows) + k) for k in range(6)]
    return _doc(rows)


def test_a_contents_list_without_page_numbers_is_found():
    ext = _act()
    assert listing_of(ext) == set(range(1, SECTIONS + 1))


def test_repeated_rows_are_not_a_contents_list():
    # The same ten bold rows twice, one block each: a table header repeated, not a contents list.
    head = [(f"Column heading {w}", 10.0, True) for w in WORDS[:10]]
    rows = head + [_body(k) for k in range(60)] + head + [_body(k) for k in range(60, 120)]
    assert listing_of(_doc(rows)) == set()


def _answer(user: str, keep) -> TextResult:
    """Every line of the slice that `keep` accepts, listed as a section start."""
    out = []
    for row in user.split("\n"):
        num, sep, rest = row.partition("| ")
        if not sep or not num.isdigit():
            continue
        text = rest.removeprefix("⟨B⟩ ")
        if keep(text, rest.startswith("⟨B⟩")):
            out.append(TextSection(start_line=int(num), number="", title=text, title_from_text=True, level=1,
                                   start_marker=text, end_marker=""))
    return TextResult(sections=out)


def test_standard_drops_sections_listed_from_the_contents_list(monkeypatch):
    # The model lists every title line, the contents list's copies included: only the body's are kept.
    async def fake(**kw):
        return _answer(kw["user"], lambda text, bold: text.startswith("Duties"))

    monkeypatch.setattr(llm_text, "structured", fake)
    ext = _act()
    _raw, sections, metrics = asyncio.run(pipeline.run(ext, "llm_text", "fake", 1.0, usage=Usage()))
    starts = [s["first_line"] for s in sections if "front_matter" not in s["flags"]]
    assert len(starts) == SECTIONS and min(starts) > SECTIONS
    assert metrics["toc_lines"] == SECTIONS


def _run(monkeypatch, ext: Extraction, keep, again) -> tuple[list, Usage]:
    async def fake(**kw):
        return _answer(kw["user"], again if kw["step"].startswith("re-read") else keep)

    monkeypatch.setattr(llm_text, "structured", fake)
    ctx = Context(model="fake", usage=Usage(), cost_cap_usd=1.0)
    return asyncio.run(LlmTextStrategy().run(ext, ctx)), ctx.usage


def test_skipped_bold_body_size_titles_are_read_again(monkeypatch):
    every = lambda text, bold: bold and text.startswith("Duties")  # noqa: E731
    first_five = lambda text, bold: every(text, bold) and text in TITLES[:5]  # noqa: E731
    found, usage = _run(monkeypatch, _act(), first_five, every)
    assert len(found) == SECTIONS
    (note,) = usage.coverage_retries
    # The 15 titles left out, and the contents list's own title ("CONTENTS OF ACT", bold at body size).
    assert note["kept"] == "retry" and note["unlisted"] == SECTIONS - 5 + 1


def test_the_contents_list_is_not_counted_as_unlisted(monkeypatch):
    # Every body title listed: the contents list's 20 plain copies are not missing headings.
    every = lambda text, bold: bold and text.startswith("Duties")  # noqa: E731
    found, usage = _run(monkeypatch, _act(), every, every)
    assert len(found) == SECTIONS and not usage.coverage_retries


def test_repeated_bold_labels_are_not_titles():
    ext = _act(labels=12)
    sig = _signals(ext)
    penalty = {ln.i for ln in ext.lines if ln.text == "Penalty"}
    titles = {ln.i for ln in ext.lines if ln.bold and ln.text.startswith("Duties")}
    assert not penalty & set(sig.large) and titles <= set(sig.large)
