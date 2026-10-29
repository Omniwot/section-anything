"""Free without a usable outline: an unnumbered heading set in the same style as numbered sections
(References, Acknowledgements, an appendix "A Proofs") takes their level, not one level deeper.
Numbered headings take their numbering depth as level; unnumbered ones used to take their style's
rank, and the paper title holds rank 1, so the section style ranked 2."""

from __future__ import annotations

import asyncio

from section_anything import pipeline
from section_anything.extract import Extraction, Line, Page
from section_anything.llm import Usage
from section_anything.strategies.base import Context
from section_anything.strategies.rules import RulesStrategy

BODY = "Ordinary body text runs on for a while in the regular face at the body size of the page."


def _ext(heads: list[tuple[str, float, bool]], per_page: int = 3) -> Extraction:
    """Each heading followed by two body lines, `per_page` headings to a page."""
    lines, rows, cursor = [], [], 0
    for k, (text, size, bold) in enumerate(heads):
        rows += [(text, size, bold, k // per_page + 1)] + [(BODY, 10, False, k // per_page + 1)] * 2
    y = {}
    for i, (t, size, bold, page) in enumerate(rows):
        y[page] = y.get(page, 720) - 20  # below the top margin, where small lines count as running headers
        lines.append(Line(i=i, page=page, text=t, x0=72, y0=y[page], x1=72 + 0.5 * size * len(t), y1=y[page] + size,
                          size=size, bold=bold, start=cursor, end=cursor + len(t)))
        cursor += len(t) + 1
    pages = [Page(n=n, width=612, height=792, origin_x=0, origin_y=0, rotation=0, has_text=True)
             for n in sorted({r[3] for r in rows})]
    return Extraction(pages, lines, "\n".join(r[0] for r in rows))


TITLE = ("A Study of Sectioning", 18, True)
PAPER = [TITLE, ("1 Introduction", 12, True), ("2 Methods", 12, True), ("2.1 Data", 10, True),
         ("2.2 Models", 10, True), ("3 Results", 12, True), ("Acknowledgements", 12, True),
         ("References", 12, True), ("A Proofs", 12, True), ("A.1 Lemma details", 10, True),
         ("B Extra results", 12, True)]


def _free(ext: Extraction) -> dict[str, int]:
    ctx = Context(model="none", usage=Usage(), cost_cap_usd=0.0)
    return {f"{s.number} {s.title}".strip(): s.level for s in asyncio.run(RulesStrategy().run(ext, ctx))}


def test_back_matter_takes_the_level_of_the_numbered_sections():
    levels = _free(_ext(PAPER))
    assert levels["1 Introduction"] == levels["3 Results"] == 1
    for title in ("Acknowledgements", "References", "A Proofs", "B Extra results"):
        assert levels[title] == 1, (title, levels)


def test_appendix_subsections_take_the_level_of_numbered_subsections():
    levels = _free(_ext(PAPER))
    assert levels["2.1 Data"] == levels["A.1 Lemma details"] == 2, levels


def test_exported_levels_put_references_next_to_the_sections():
    ext = _ext(PAPER)
    _raw, secs, _ = asyncio.run(pipeline.run(ext, "rules", "none", 0.0))
    by = {f"{s['number']} {s['title']}".strip(): s for s in secs}
    assert "doc_title" in by["A Study of Sectioning"]["flags"]
    assert by["References"]["level"] == by["1 Introduction"]["level"]
    assert by["A.1 Lemma details"]["level"] == by["2.1 Data"]["level"]


def test_unnumbered_documents_keep_their_style_ranks():
    # A README: no numbered headings, so the levels are the style ranks, as before.
    levels = _free(_ext([("Project", 16, True), ("Install", 13, True), ("From source", 11, True),
                         ("Usage", 13, True), ("Options", 11, True)]))
    assert levels == {"Project": 1, "Install": 2, "From source": 3, "Usage": 2, "Options": 3}


def test_one_numbered_heading_does_not_set_its_style_level():
    # A single numbered line in a style (a stray "2.1" in bold) is too little to tie the style to a depth.
    levels = _free(_ext([TITLE, ("Overview", 12, True), ("Details", 12, True), ("2.1 Note", 10, True),
                         ("Remarks", 10, True)]))
    assert levels["Remarks"] > levels["Details"], levels


def test_numbered_lines_on_one_page_do_not_set_their_style_level():
    # Numbered affiliations under the title, in the style of minor headings further on.
    heads = [TITLE, ("1 Institute of Testing, Somewhere", 10, True), ("2 School of Examples, Elsewhere", 10, True),
             ("Introduction", 14, True), ("Model", 12, True), ("Architecture", 10, True), ("Results", 14, True)]
    levels = _free(_ext(heads, per_page=4))
    assert levels["Introduction"] < levels["Model"] < levels["Architecture"], levels


def test_without_top_level_numbers_the_style_ranks_stay():
    # The sections' own headings were not found, only their "2.1"-style subsections: depth 2 says
    # nothing about the title or the unnumbered headings, so they keep their ranks.
    heads = [("A Paper Title In Bold", 10, True), ("Conflict of interest.", 10, True), ("2.1. Cells", 10, True),
             ("2.2. Maps", 10, True), ("2.3. Bundles", 10, True)]
    main_like = {"A Paper Title In Bold": 1, "Conflict of interest.": 1, "2.1. Cells": 2, "2.2. Maps": 2,
                 "2.3. Bundles": 2}
    assert _free(_ext(heads, per_page=2)) == main_like
