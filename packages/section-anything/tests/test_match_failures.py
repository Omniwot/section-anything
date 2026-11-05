"""Free's run-on rule on layouts from the match-failure audit (research finding F063): a bold title that
wraps onto a lowercase line is kept whole, a bold paragraph still runs on, and wrapped titles still join.
F063's layout test in the merge stage (stacked headings in one style kept apart) is not in this release."""

from __future__ import annotations

from section_anything.extract import Extraction, Line, Page
from section_anything.strategies.rules import RulesStrategy

BODY = "Ordinary body text runs on here for a while, set at the size of the page's body text."


def _ext(rows: list[tuple[str, float, bool, float, float]], page: int = 2) -> Extraction:
    """An extraction from (text, size, bold, x0, y0) rows on one page (the second unless given), in reading
    order, with body text below."""
    rows = [*rows, *[(BODY, 10, False, 72, 300 - 14 * k) for k in range(12)]]
    lines, pos = [], 0
    for i, (text, size, bold, x0, y0) in enumerate(rows):
        lines.append(Line(i=i, page=page, text=text, x0=x0, y0=y0, x1=x0 + 5.0 * len(text), y1=y0 + size,
                          size=size, bold=bold, start=pos, end=pos + len(text)))
        pos += len(text) + 1
    pages = [Page(n=n, width=612, height=792, origin_x=0, origin_y=0, rotation=0, has_text=True)
             for n in range(1, page + 1)]
    return Extraction(pages, lines, "\n".join(ln.text for ln in lines), outline=[])


def _titles(rows, page: int = 2) -> list[str]:
    return [f"{r.number} {r.title}".strip() for r in RulesStrategy()._rules(_ext(rows, page))]


def test_a_title_wrapped_at_its_own_line_spacing_stays_one():
    titles = _titles([(BODY, 10, False, 72, 640), ("Social and Community Issues and", 18, True, 72, 600),
                      ("Environmental Matters", 18, True, 72, 578), (BODY, 10, False, 72, 550)])
    assert "Social and Community Issues and Environmental Matters" in titles


def test_a_title_ending_on_a_connecting_word_joins_its_next_line_set_further_down():
    titles = _titles([("Evidence Review of", 33, False, 72, 700), ("Online Choice Architecture", 33, False, 72, 643),
                      (BODY, 10, False, 72, 600)])
    assert "Evidence Review of Online Choice Architecture" in titles


def test_a_number_on_the_title_row_still_joins_it():
    titles = _titles([(BODY, 10, False, 72, 640), ("79", 10, True, 72, 610),
                      ("Annual report on security of electricity supply", 10, True, 102, 610), (BODY, 10, False, 72, 590)])
    assert "79 Annual report on security of electricity supply" in titles


def test_a_bold_title_wrapping_onto_a_lowercase_line_is_kept_whole():
    titles = _titles([(BODY, 10, False, 72, 640), ("Remuneration policy for executive", 10, True, 72, 610),
                      ("directors", 10, True, 72, 596), (BODY, 10, False, 72, 570)])
    assert "Remuneration policy for executive directors" in titles
    assert "directors" not in titles


def test_a_bold_paragraph_still_runs_on():
    para = [("Directions given to the Fund (operating as", 10, True, 72, 610), ("the Community Fund) under", 10, True, 72, 596),
            ("section 36 of the Act, as amended", 10, True, 72, 582), ("by the later Acts of 2013 and", 10, True, 72, 568),
            ("thereafter, in the following terms", 10, True, 72, 554)]
    titles = _titles([(BODY, 10, False, 72, 640), *para, (BODY, 10, False, 72, 530)])
    assert not any(t.startswith("Directions given") for t in titles)


def test_a_chapter_number_set_alone_joins_its_title_far_below():
    titles = _titles([("ONE", 14.3, True, 300, 700), ("INTRODUCTION", 14.3, True, 280, 645), (BODY, 10, False, 72, 600)])
    assert "ONE INTRODUCTION" in titles


def test_a_title_line_starting_in_lowercase_joins_the_line_above():
    titles = _titles([("Convergence of maximum likelihood supertree", 20.7, False, 112, 638),
                      ("reconstruction", 20.7, False, 247, 597), (BODY, 10, False, 72, 550)])
    assert "Convergence of maximum likelihood supertree reconstruction" in titles
