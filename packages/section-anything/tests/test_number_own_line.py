"""A section number the extractor split off its title ("1" | "Introduction" on one baseline) stays
with the heading: Free keeps the number and its level, Quick check shows the model one row, and
an outline whose bookmarks leave the number out still starts the section at it. (pdfminer splits
a line where a space is wider than twice the characters beside it: after "1" before a narrow "I".)"""

from __future__ import annotations

import asyncio

from section_anything.extract import Extraction, Line, OutlineItem, Page
from section_anything.llm import Usage
from section_anything.strategies import llm_text
from section_anything.strategies.base import Context
from section_anything.strategies.llm_text import LlmReviewStrategy, ReviewItem, ReviewResult
from section_anything.strategies.rules import RulesStrategy, candidates
from section_anything.structure import furniture_of, split_number

BODY = "Ordinary body text runs on for a while in the regular face at the body size of the page."
# (text, size, bold, x0, y0): y0 is the baseline, top of the page first.
Row = tuple[str, float, bool, float, float]


def _ext(rows: list[Row], outline: list[tuple[int, str, int]] = ()) -> Extraction:
    """One page; a row's right edge is estimated from its length."""
    lines, cursor = [], 0
    for i, (t, size, bold, x0, y0) in enumerate(rows):
        lines.append(Line(i=i, page=1, text=t, x0=x0, y0=y0, x1=x0 + 0.5 * size * len(t), y1=y0 + size,
                          size=size, bold=bold, start=cursor, end=cursor + len(t)))
        cursor += len(t) + 1
    pages = [Page(n=1, width=612, height=792, origin_x=0, origin_y=0, rotation=0, has_text=True)]
    ext = Extraction(pages, lines, "\n".join(r[0] for r in rows))
    ext.outline = [OutlineItem(level=lv, title=t, page=p) for lv, t, p in outline]
    return ext


def _paper(number: Row, title: Row) -> Extraction:
    """A title, then section 1 as two extracted lines, then sections 2 and 3 on one line each."""
    return _ext([("A Study of Sectioning", 18, True, 150, 740), (BODY, 10, False, 72, 700), number, title,
                 (BODY, 10, False, 72, 640), (BODY, 10, False, 72, 628), ("2 Methods", 12, True, 72, 600),
                 (BODY, 10, False, 72, 580), ("2.1 Data", 10, True, 72, 560), (BODY, 10, False, 72, 540),
                 ("3 Results", 12, True, 72, 520), (BODY, 10, False, 72, 500), (BODY, 10, False, 72, 488)])


SPLIT = (("1", 12, True, 72, 660), ("Introduction", 12, True, 86, 660))  # 8 pt gap after the number


def _free(ext: Extraction) -> list[tuple[str, str, int, int]]:
    ctx = Context(model="none", usage=Usage(), cost_cap_usd=0.0)
    return [(s.number, s.title, s.level, s.start_line) for s in asyncio.run(RulesStrategy().run(ext, ctx))]


def test_split_number_is_recognised_and_not_furniture():
    ext = _paper(*SPLIT)
    assert split_number(ext, ext.lines[2])
    assert 2 not in furniture_of(ext)  # a bare "1" alone would look like a page number


def test_free_keeps_the_number_and_its_level():
    heads = _free(_paper(*SPLIT))
    assert ("1", "Introduction", 1, 2) in heads
    assert [(n, lv) for n, _, lv, _ in heads if n] == [("1", 1), ("2", 1), ("2.1", 2), ("3", 1)]


def test_quick_check_row_joins_number_and_title():
    rows = [r for _, r in LlmReviewStrategy()._rows(_paper(*SPLIT))]
    assert any(r.startswith("2| ") and " 1 Introduction  ⟶ " in r for r in rows)
    assert not any(r.startswith("3| ") for r in rows)  # the title line is not a row of its own


def test_quick_check_marker_and_title_come_from_both_lines(monkeypatch):
    async def fake(**_kw):
        return ReviewResult(items=[ReviewItem(id=2, is_heading=True, level=1, number="1", title="Introduction")])

    monkeypatch.setattr(llm_text, "structured", fake)
    ctx = Context(model="fake", usage=Usage(), cost_cap_usd=1.0)
    (sec,) = asyncio.run(LlmReviewStrategy().run(_paper(*SPLIT), ctx))
    assert (sec.number, sec.title, sec.start_line, sec.start_marker) == ("1", "Introduction", 2, "1 Introduction")


def test_number_above_the_title_or_in_another_style_is_left_alone():
    for number, title in ((("1", 12, True, 72, 676), ("Introduction", 12, True, 72, 660)),  # line above
                          (("1", 12, False, 72, 660), ("Introduction", 12, True, 86, 660)),  # not bold
                          (("1", 12, True, 72, 660), ("Introduction", 12, True, 200, 660))):  # far apart
        ext = _paper(number, title)
        assert not split_number(ext, ext.lines[2]), (number, title)
        assert "1" not in [ln.text for ln, _ in candidates(ext)]


def test_numbers_in_a_row_are_not_headings():
    # Roman column labels of a table or figure, "I II III IV", each extracted as its own line.
    ext = _ext([(BODY, 10, False, 72, 700), ("II", 9, False, 100, 680), ("III", 9, False, 112, 680),
                ("IV", 9, False, 126, 680), (BODY, 10, False, 72, 660), (BODY, 10, False, 72, 648)])
    assert not split_number(ext, ext.lines[1]) or not split_number(ext, ext.lines[2])
    assert not {ln.text for ln, _ in candidates(ext, loose=True)} & {"II", "III", "IV"}


def test_number_whose_title_line_is_not_a_heading_is_dropped():
    # Same baseline and style, but the "title" is body text: not a heading, so neither is the number.
    ext = _ext([(BODY, 10, False, 72, 700), ("4", 10, False, 72, 680), ("In this case the bound holds.", 10, False, 84, 680),
                (BODY, 10, False, 72, 660), (BODY, 10, False, 72, 648)])
    assert split_number(ext, ext.lines[1])
    assert "4" not in [ln.text for ln, _ in candidates(ext)]
    assert "4" not in [ln.text for ln, _ in candidates(ext, loose=True)]


def _rows_of(ext: Extraction) -> list[Row]:
    return [(ln.text, ln.size, ln.bold, ln.x0, ln.y0) for ln in ext.lines]


def test_bookmarks_without_numbers_keep_the_printed_number():
    # The bookmark "Introduction" names the title line; the section starts at the number before it.
    outline = [(1, "Introduction", 1), (1, "2 Methods", 1), (2, "2.1 Data", 1), (1, "3 Results", 1)]
    heads = _free(_ext(_rows_of(_paper(*SPLIT)), outline))
    assert ("1", "Introduction", 1, 2) in heads
    assert [(n, lv) for n, _, lv, _ in heads if n] == [("1", 1), ("2", 1), ("2.1", 2), ("3", 1)]


def test_bookmarks_with_numbers_anchor_on_the_split_line():
    # "1 Introduction" is found across the two lines, now that the "1" is not taken for a page number.
    outline = [(2, "1 Introduction", 1), (2, "2 Methods", 1), (3, "2.1 Data", 1), (2, "3 Results", 1)]
    heads = _free(_ext(_rows_of(_paper(*SPLIT)), outline))
    assert ("1", "Introduction", 2, 2) in heads
    assert [(n, lv) for n, _, lv, _ in heads if n] == [("1", 2), ("2", 2), ("2.1", 3), ("3", 2)]
