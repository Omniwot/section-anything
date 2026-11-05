"""Candidate rules that threw away real headings with a heading signal (research finding F062): a bare
"§ 97" set like a heading has no letters; a section number longer than its title ("13.3.11 Hint"); a
number split off a title set in body type ("A." | "The Glucoamylase"); and a bare label's title that
Docling calls body text. Each rule still removes what it was built to remove."""

from __future__ import annotations

from section_anything.docling_input import DoclingHints
from section_anything.extract import Extraction, Line, Page
from section_anything.strategies.llm_text import LlmReviewStrategy
from section_anything.strategies.rules import candidates

BODY = "Ordinary body text runs on for a while in the regular face at the body size of the page."
# (text, size, bold, x0, y0): y0 is the baseline, top of the page first; one page.
Row = tuple[str, float, bool, float, float]


def _ext(rows: list[Row]) -> Extraction:
    lines, cursor = [], 0
    for i, (t, size, bold, x0, y0) in enumerate(rows):
        lines.append(Line(i=i, page=1, text=t, x0=x0, y0=y0, x1=x0 + 0.5 * size * len(t), y1=y0 + size,
                          size=size, bold=bold, start=cursor, end=cursor + len(t)))
        cursor += len(t) + 1
    pages = [Page(n=1, width=612, height=792, origin_x=0, origin_y=0, rotation=0, has_text=True)]
    return Extraction(pages, lines, "\n".join(r[0] for r in rows))


def _body(y0: float, n: int, x0: float = 72) -> list[Row]:
    return [(BODY, 10, False, x0, y0 - 12 * k) for k in range(n)]


def _texts(ext: Extraction, loose: bool = False) -> list[str]:
    return [ln.text for ln, _ in candidates(ext, loose=loose)]


def test_a_bare_paragraph_sign_set_bold_is_a_heading():
    ext = _ext([("§ 96 Übergangsvorschrift", 10, True, 72, 740), *_body(720, 3),
                ("§ 97", 10, True, 72, 670), ("(weggefallen)", 10, False, 72, 650), *_body(630, 3)])
    assert "§ 97" in _texts(ext)
    assert "§ 97" in _texts(ext, loose=True)


def test_a_bare_paragraph_sign_in_body_type_is_not():
    # Contents lists and cross-reference columns print bare "§ 102" lines in the body face.
    ext = _ext([("§ 1 Anwendungsbereich", 10, True, 72, 740), *_body(720, 2),
                ("§ 102", 10, False, 72, 690), ("§ 103", 10, False, 72, 678), *_body(660, 3)])
    assert not {"§ 102", "§ 103"} & set(_texts(ext))
    assert not {"§ 102", "§ 103"} & set(_texts(ext, loose=True))


def test_a_number_longer_than_its_title_does_not_count_against_it():
    ext = _ext([("13.3 Attributes", 12, False, 72, 740), *_body(720, 3),
                ("13.3.11 Hint", 12, False, 72, 670), *_body(650, 3),
                ("10.3 AVCs – JPS 2015", 10, True, 72, 600), *_body(580, 3)])
    assert {"13.3.11 Hint", "10.3 AVCs – JPS 2015"} <= set(_texts(ext))


def test_bold_maths_and_figures_are_still_left_out():
    ext = _ext([("1 Introduction", 12, True, 72, 740), *_body(720, 3),
                ("A, B", 10, True, 200, 670), *_body(650, 2), ("12.5 cm 13.2 cm 14.1", 10, True, 200, 610),
                *_body(590, 3)])
    assert not {"A, B", "12.5 cm 13.2 cm 14.1"} & set(_texts(ext))


def _split(title: str, after: list[Row]) -> Extraction:
    """A heading whose number the extractor split off (same baseline, a wide gap), in body type."""
    return _ext([("Part One", 14, True, 72, 760), *_body(740, 3), ("2.3", 10, False, 72, 690),
                 (title, 10, False, 92, 690), *after])


def test_split_number_with_a_body_type_title_is_a_heading():
    ext = _split("Data Sources", _body(665, 4))  # a gap below the heading, then the paragraph
    assert {"2.3", "Data Sources"} <= set(_texts(ext))
    rows = [r for _, r in LlmReviewStrategy()._rows(ext)]
    assert any(" 2.3 Data Sources  ⟶ " in r for r in rows)


def test_split_numbered_paragraph_is_not_a_heading():
    # "1.1 This is a companion paper, which ..." runs on under its first line at the line spacing.
    para = _split("This is a companion paper, which provides underpinning evidence",
                  [("to support the publication and is read with it as a reference.", 10, False, 92, 678),
                   ("It provides the detail behind each of the practices it lists.", 10, False, 92, 666),
                   *_body(640, 2)])
    assert not {"2.3", "This is a companion paper, which provides underpinning evidence"} & set(_texts(para))
    tight = _split("Data Sources", _body(678, 4))  # no gap: the line runs on into a paragraph
    assert "2.3" not in _texts(tight)
    lower = _split("durch öffentliche Stellen", _body(665, 4))  # a list item, not a title
    assert "2.3" not in _texts(lower, loose=True)


def test_split_letter_number_is_offered_to_quick_check_only():
    ext = _ext([("Part One", 14, True, 72, 760), *_body(740, 3), ("A.", 10, False, 72, 690),
                ("The Glucoamylase", 10, False, 88, 690), *_body(665, 4)])
    assert "A." not in _texts(ext)  # Free keeps single-level numbers in body type out
    rows = [r for _, r in LlmReviewStrategy()._rows(ext)]
    assert any(" A. The Glucoamylase  ⟶ " in r for r in rows)


def test_label_title_called_body_text_by_docling_stays_with_its_label():
    ext = _ext([("Teil 3", 12, True, 72, 740), ("Pflichten der Betreiber", 12, True, 72, 724), *_body(700, 3),
                ("Teil 4", 12, True, 72, 650), ("Datenbanken der Registrierungsdaten", 12, True, 72, 634),
                *_body(610, 3), ("Wichtiger Hinweis", 12, True, 72, 560), *_body(540, 3)])
    ext._derived["docling"] = DoclingHints(headers={0, 1, 5}, body={6, 10} | {2, 3, 4, 7, 8, 9, 11, 12, 13})
    texts = _texts(ext)
    assert {"Teil 4", "Datenbanken der Registrierungsdaten"} <= set(texts)
    assert "Wichtiger Hinweis" not in texts  # a bold line Docling calls body text, under no label
