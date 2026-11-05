"""Headings set in italics at body size (research finding F061): a UK Act's cross-headings are italic lines
in the body face with no other signal. Emphasis, quotations and italic paragraphs stay out. In a short Act with
no Parts or Chapters, the cross-headings sit above the sections they head (research finding F064)."""

from __future__ import annotations

from section_anything.extract import Extraction, Line, Page
from section_anything.strategies.rules import RulesStrategy, candidates

TEXT = "The Secretary of State may by regulations make provision about the matters in this section."


def _ext(rows: list[tuple[str, float, bool, bool, float]]) -> Extraction:
    """One page from (text, size, bold, italic, y0) rows, in reading order."""
    lines, pos = [], 0
    for i, (text, size, bold, italic, y0) in enumerate(rows):
        lines.append(Line(i=i, page=1, text=text, x0=72, y0=y0, x1=72 + 5.0 * len(text), y1=y0 + size, size=size,
                          bold=bold, start=pos, end=pos + len(text), italic=italic))
        pos += len(text) + 1
    return Extraction([Page(n=1, width=612, height=792, origin_x=0, origin_y=0, rotation=0, has_text=True)], lines,
                      "\n".join(ln.text for ln in lines))


def _act() -> Extraction:
    rows, y = [], 760.0

    def add(text, bold=False, italic=False, gap=1.0):
        nonlocal y
        y -= 11 + gap
        rows.append((text, 11.0, bold, italic, y))

    for _ in range(4):
        add(TEXT)
    add("Types of sanction", italic=True, gap=13)  # a cross-heading
    add("3 Financial sanctions", bold=True, gap=13)
    for _ in range(3):
        add(TEXT)
    add("This is said in passing,", italic=True)  # emphasis inside a paragraph: no space around it
    add(TEXT)
    add("Nothing in this Act affects the prerogative.", italic=True, gap=13)  # ends like a sentence
    add(TEXT, gap=13)
    add("Enforcement", italic=True, gap=13)  # an italic paragraph's first line: italic below
    add("of the provisions above is a matter for the court", italic=True)
    add(TEXT, gap=13)
    add("Supplementary", italic=True, gap=13)
    add("4 Interpretation", bold=True, gap=13)
    add(TEXT)
    return _ext(rows)


def test_an_italic_cross_heading_set_apart_is_a_candidate():
    ext = _act()
    for loose in (False, True):
        texts = [ln.text for ln, _ in candidates(ext, loose=loose)]
        assert "Types of sanction" in texts and "Supplementary" in texts
        assert not any(t.startswith(("This is said", "Nothing in", "Enforcement", "of the")) for t in texts)


def test_without_italics_nothing_changes():
    ext = _act()
    for ln in ext.lines:
        ln.italic = False
    assert [ln.text for ln, _ in candidates(ext)] == ["3 Financial sanctions", "4 Interpretation"]


def _levels(ext: Extraction) -> dict[str, int]:
    return {f"{r.number} {r.title}".strip(): r.level for r in RulesStrategy()._rules(ext)}


def test_cross_headings_sit_above_the_sections_they_head():
    # A short Act with no Parts or Chapters: no labels set the levels, and the italic style ranks lowest.
    lv = _levels(_act())
    assert lv["Types of sanction"] < lv["3 Financial sanctions"]
    assert lv["Supplementary"] < lv["4 Interpretation"]


def test_one_italic_line_over_a_section_is_no_pattern():
    rows, y = [], 760.0
    for text, bold, italic, gap in [(TEXT, False, False, 1), ("Supplementary", False, True, 13),
                                    ("4 Interpretation", True, False, 13), (TEXT, False, False, 1),
                                    ("5 Commencement", True, False, 13), (TEXT, False, False, 1),
                                    ("Transitional matters", False, True, 13), (TEXT, False, False, 13)]:
        y -= 11 + gap
        rows.append((text, 11.0, bold, italic, y))
    lv = _levels(_ext(rows))
    assert lv["Supplementary"] > lv["4 Interpretation"]


def test_an_italic_heading_over_numbered_paragraphs_stays_below_them():
    # A report's minor headings over numbered paragraphs in body type ("6.12 Studies show ..."): not sections.
    rows, y = [], 760.0
    for text, size, bold, italic, gap in [("Defaults", 14.0, True, False, 13),
                                          ("Effect on consumers", 11.0, False, True, 13),
                                          ("6.12 Studies of defaults show strong effects", 11.0, False, False, 13),
                                          (TEXT, 11.0, False, False, 1),
                                          ("Literature on remedies", 11.0, False, True, 13),
                                          ("6.13 Defaults work best with many alternatives", 11.0, False, False, 13),
                                          (TEXT, 11.0, False, False, 1)]:
        y -= size + gap
        rows.append((text, size, bold, italic, y))
    lv = _levels(_ext(rows))
    assert lv["Effect on consumers"] > lv["6.12 Studies of defaults show strong effects"]
