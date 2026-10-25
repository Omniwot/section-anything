"""The abstract's heading is a candidate whatever its size or weight, and takes the level of the
section that follows it (READoc arXiv papers set "Abstract" small and bold, or run it in)."""

from __future__ import annotations

import asyncio

from section_anything.extract import Extraction, Line, OutlineItem, Page
from section_anything.llm import Usage
from section_anything.strategies.base import Context
from section_anything.strategies.rules import RulesStrategy, candidates

BODY = "Ordinary body text runs on for a while in the regular face at the body size of the page."
RUNIN = "Abstract—We study how long documents split into sections that a reader can use on their own."


def _ext(rows: list[tuple[str, float, bool]], outline: list[tuple[int, str, int]] = (), per_page: int = 12) -> Extraction:
    """rows: (text, size, bold), top to bottom, `per_page` lines a page; outline: (level, title, page)."""
    lines, cursor = [], 0
    for i, (t, size, bold) in enumerate(rows):
        page, k = i // per_page + 1, i % per_page
        lines.append(Line(i=i, page=page, text=t, x0=72, y0=700 - k * 20, x1=500, y1=712 - k * 20,
                          size=size, bold=bold, start=cursor, end=cursor + len(t)))
        cursor += len(t) + 1
    pages = [Page(n=p, width=612, height=792, origin_x=0, origin_y=0, rotation=0, has_text=True)
             for p in range(1, lines[-1].page + 1)]
    ext = Extraction(pages, lines, "\n".join(t for t, _, _ in rows))
    ext.outline = [OutlineItem(level=lv, title=t, page=p) for lv, t, p in outline]
    return ext


def _cand_text(ext: Extraction, loose: bool = False) -> list[str]:
    return [ln.text for ln, _ in candidates(ext, loose=loose)]


def _free(ext: Extraction) -> list[tuple[str, int]]:
    ctx = Context(model="none", usage=Usage(), cost_cap_usd=0.0)
    return [(s.title, s.level) for s in asyncio.run(RulesStrategy().run(ext, ctx))]


def _paper(abstract: tuple[str, float, bool], page: int = 1) -> Extraction:
    """A title, the abstract heading on `page`, then numbered sections."""
    pad = [(BODY, 10, False)] * (12 * (page - 1))
    return _ext([("A Study of Sectioning", 18, True), *pad, abstract, (BODY, 10, False), (BODY, 10, False),
                 ("1 Introduction", 12, True), (BODY, 10, False), ("2 Methods", 12, True), (BODY, 10, False),
                 (BODY, 10, False), (BODY, 10, False)], per_page=12)


def test_small_bold_abstract_is_a_candidate():
    ext = _paper(("Abstract", 9, True))
    assert "Abstract" in _cand_text(ext) and "Abstract" in _cand_text(ext, loose=True)
    assert ("Abstract", 1) in _free(ext)


def test_small_regular_and_letter_spaced_abstract_are_candidates():
    for heading in ("ABSTRACT", "A B S T R A C T", "Abstract."):
        ext = _paper((heading, 8, False))
        assert heading in _cand_text(ext), heading
        assert heading in _cand_text(ext, loose=True), heading


def test_run_in_abstract_is_a_candidate_titled_abstract():
    for runin, title in ((RUNIN, "Abstract"), ("Abstract. Let G be a finite group and H a subgroup of G.", "Abstract"),
                         ("ABSTRACT: We measure how often headings are found.", "ABSTRACT")):
        ext = _paper((runin, 10, False))
        assert runin in _cand_text(ext) and runin in _cand_text(ext, loose=True), runin
        titles = [t for t, _ in _free(ext)]
        assert title in titles and runin not in titles, runin


def test_abstract_as_a_word_in_body_text_is_not_a_candidate():
    for text in ("Abstract algebra is the study of groups, rings and fields and their maps.",
                 "Abstracts of the talks are listed in the appendix at the end of the volume."):
        ext = _paper((text, 10, False))
        assert text not in _cand_text(ext) and text not in _cand_text(ext, loose=True), text


def test_abstract_after_page_two_is_not_a_candidate():
    late, early = _paper(("Abstract", 9, False), page=3), _paper(("Abstract", 9, False), page=2)
    assert [ln.page for ln in late.lines if ln.text == "Abstract"] == [3]
    assert [ln.page for ln in early.lines if ln.text == "Abstract"] == [2]
    assert "Abstract" not in _cand_text(late) and "Abstract" not in _cand_text(late, loose=True)
    assert "Abstract" in _cand_text(early)


def test_abstract_takes_the_next_sections_level():
    # Unnumbered headings: title 18 bold (level 1), sections 13 bold (level 2), subsection 11 bold.
    ext = _ext([("A Study of Sectioning", 18, True), ("Abstract", 9, True), (BODY, 10, False),
                ("Introduction", 13, True), (BODY, 10, False), ("Scope", 11, True), (BODY, 10, False),
                ("Methods", 13, True), (BODY, 10, False), (BODY, 10, False)])
    assert _free(ext) == [("A Study of Sectioning", 1), ("Abstract", 2), ("Introduction", 2), ("Scope", 3),
                          ("Methods", 2)]


def test_abstract_style_does_not_shift_other_levels():
    # "Abstract" in 12 pt regular would rank between the 12 pt bold sections and the 10 pt bold
    # subsections and push the subsections down a level; excluded from ranking, it cannot.
    ext = _ext([("Abstract", 12, False), (BODY, 10, False), ("Introduction", 12, True), (BODY, 10, False),
                ("Background", 10, True), (BODY, 10, False), ("Methods", 12, True), (BODY, 10, False),
                (BODY, 10, False), (BODY, 10, False)])
    assert _free(ext) == [("Abstract", 1), ("Introduction", 1), ("Background", 2), ("Methods", 1)]


def test_abstract_with_bookmarks_takes_the_next_sections_level():
    rows = [("A Study of Sectioning", 18, True), ("Abstract", 9, True), (BODY, 10, False),
            ("1 Introduction", 14, True), (BODY, 10, False), ("2 Methods", 14, True), (BODY, 10, False),
            ("2.1 Data", 12, True), (BODY, 10, False), ("3 Results", 14, True), (BODY, 10, False)]
    outline = [(1, "A Study of Sectioning", 1), (2, "1 Introduction", 1), (2, "2 Methods", 1),
               (3, "2.1 Data", 1), (2, "3 Results", 1)]
    heads = _free(_ext(rows, outline))
    assert ("Abstract", 2) in heads
    assert [lv for t, lv in heads if t != "Abstract"] == [1, 2, 2, 3, 2]
