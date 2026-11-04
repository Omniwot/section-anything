"""Contents check: every bookmark or contents entry no section covers is looked for in the body and
added as a heading; entries not found are listed in `possible_misses` (research finding F057)."""

from __future__ import annotations

import asyncio

from section_anything import Settings, pipeline
from section_anything.contents_check import _usable, check_contents, entries_of, locate
from section_anything.extract import Extraction, Line, OutlineItem, Page
from section_anything.llm import Usage
from section_anything.possible_misses import possible_misses
from section_anything.strategies.base import RawSection, Strategy

WORDS = ("archive", "budget", "council", "deposit", "estate", "finance", "grant", "harbour", "inquiry", "journal")
HEADINGS = ["1 Scope of the archive", "2 Budget rules", "3 Council duties", "4 Deposit accounts"]


def _body(k: int) -> tuple[str, float, bool]:
    a, b = WORDS[k % len(WORDS)], WORDS[(k // len(WORDS)) % len(WORDS)]
    return (f"Ordinary body text about the {a} and the {b} runs on in the regular face, line {k}.", 10.0, False)


def _doc(rows: list[tuple[str, float, bool]], per_page: int = 20, outline=None) -> Extraction:
    lines, cursor = [], 0
    for i, (text, size, bold) in enumerate(rows):
        page, y0 = i // per_page + 1, 850 - 30 * (i % per_page)
        lines.append(Line(i=i, page=page, text=text, x0=72, y0=y0, x1=72 + 0.5 * size * len(text), y1=y0 + size,
                          size=size, bold=bold, start=cursor, end=cursor + len(text)))
        cursor += len(text) + 1
    pages = [Page(n=n, width=612, height=950, origin_x=0, origin_y=0, rotation=0, has_text=True)
             for n in range(1, lines[-1].page + 1)]
    return Extraction(pages, lines, "\n".join(r[0] for r in rows), outline=outline or [])


def _report() -> tuple[Extraction, dict[str, int]]:
    """Four bold headings, one per page, each followed by body text; bookmarks for all four and for
    a fifth heading that is not in the text."""
    rows, at = [], {}
    for h in HEADINGS:
        at[h] = len(rows)
        rows.append((h, 14.0, True))
        rows += [_body(len(rows) + k) for k in range(19)]
    ext = _doc(rows)
    ext.outline = [OutlineItem(level=1, title=h, page=ext.lines[at[h]].page, y=ext.lines[at[h]].y1) for h in HEADINGS]
    ext.outline.append(OutlineItem(level=1, title="5 Estate transfers", page=4, y=None))
    return ext, at


class _Partial(Strategy):
    """A model mode that listed every heading except the third one."""

    id = "llm_review"
    uses_llm = True

    def __init__(self, at: dict[str, int]) -> None:
        self.at = at

    async def run(self, ext, ctx):
        return [RawSection(title=h.split(" ", 1)[1], number=h.split(" ", 1)[0], level=1, start_marker=h,
                           start_line=self.at[h]) for h in HEADINGS if h != HEADINGS[2]]


def _run(ext, at, settings, monkeypatch):
    monkeypatch.setitem(pipeline.BY_ID, "llm_review", _Partial(at))
    _raw, sections, metrics = asyncio.run(pipeline.run(ext, "llm_review", "m", 1.0, usage=Usage(), settings=settings))
    return sections, metrics


def test_a_bookmarked_heading_the_mode_left_out_is_added(monkeypatch):
    ext, at = _report()
    sections, metrics = _run(ext, at, Settings(contents_check=["quick"]), monkeypatch)
    added = [s for s in sections if "from_contents" in s["flags"]]
    assert [(s["number"], s["title"], s["first_line"], s["level"]) for s in added] == [("3", "Council duties", at[HEADINGS[2]], 1)]
    assert metrics["contents_check"]["added"] == 1
    assert metrics["contents_check"]["unresolved"] == 1  # "5 Estate transfers" is not in the text


def test_the_check_can_be_turned_off(monkeypatch):
    ext, at = _report()
    sections, metrics = _run(ext, at, Settings(contents_check=[]), monkeypatch)
    assert len([s for s in sections if "front_matter" not in s["flags"]]) == 3
    assert "contents_check" not in metrics


def test_an_entry_not_found_is_listed_as_a_possible_miss_not_guessed(monkeypatch):
    ext, at = _report()
    sections, metrics = _run(ext, at, Settings(contents_check=["quick"]), monkeypatch)
    assert not any("Estate" in s["title"] for s in sections)
    misses = metrics["possible_misses"]
    entry = next(m for m in misses if m["text"] == "5 Estate transfers")
    assert entry["page"] == 4 and entry["evidence"] == ["listed in the PDF's bookmarks, not found in the text"]
    assert all(set(m) == {"page", "text", "evidence", "score"} for m in misses)


def test_possible_misses_rank_a_heading_like_line_the_result_left_out(monkeypatch):
    ext, at = _report()
    sections, _ = _run(ext, at, Settings(contents_check=[]), monkeypatch)
    misses = possible_misses(sections, ext)
    assert misses and misses[0]["text"] == HEADINGS[2] and misses[0]["page"] == 3
    assert "its number fills a gap in the headings' numbering" in misses[0]["evidence"]
    assert len(misses) <= max(3, len(ext.pages) // 5)


def test_a_printed_contents_entry_is_found_near_its_page_not_at_an_earlier_mention():
    titles = ["Ranking rules", "Bundling offers", "Pricing notes", "Final remarks"]
    rows = [("Contents", 14.0, True)] + [(f"{t} ........ {3 + 2 * k}", 10.0, False) for k, t in enumerate(titles)]
    rows += [_body(k) for k in range(35)]  # pages 1 and 2
    for t in titles:
        rows += [(t, 14.0, True)] + [_body(len(rows) + k) for k in range(39)]  # pages 3, 5, 7, 9
    rows[45] = ("Bundling offers", 10.0, False)  # page 3: a mention under "Ranking rules", before its heading
    ext = _doc(rows)
    entries = entries_of(ext)
    locate(ext, entries)
    found = {e.title: ext.lines[e.line].page for e in entries if e.line is not None}
    assert found == {"Ranking rules": 3, "Bundling offers": 5, "Pricing notes": 7, "Final remarks": 9}
    check = check_contents([], ext)
    assert len(check.added) == 4


def test_entries_that_are_not_headings_are_skipped():
    for text in ("PART 1", "Section 7.2", "[RFC3756]", "5.5.5 Error budget . . . . . . . 225", "keq−",
                 "contravariantly terminal,", "Table of contents", "Front cover"):
        assert not _usable(text), text
    for text in ("4.1.1. Request Cancellation and Rejection", "PART 1 Preliminary", "Annex II Technical documentation"):
        assert _usable(text), text
