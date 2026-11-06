"""A UK Act's schedules in Free (research finding F065): a schedule paragraph's own italic title sits close
above the paragraph, whose number stands alone at the margin; lines that open with a reference in body type
("section 4 (soliciting murder)") are not headings; Parts and paragraph titles inside a schedule nest under
it; a label with an amendment mark run into it, or read after its title, still opens a heading."""

from __future__ import annotations

from section_anything.extract import Extraction, Line, Page
from section_anything.strategies.rules import RulesStrategy, candidates

BODY = "(2) The constable may require any person on the ship to give information about the ship and its"
WORDS = iter(f"{a}{b}" for a in "bcdfghjklmnprstvwz" for b in ("ane", "ore", "ite", "ule", "age", "ive", "ent", "ory"))
# (page, text, size, bold, italic, x0, y0): y0 is the bottom of the line, top of the page first.
Row = tuple[int, str, float, bool, bool, float, float]


def _ext(rows: list[Row]) -> Extraction:
    lines, pos = [], 0
    for i, (page, text, size, bold, italic, x0, y0) in enumerate(rows):
        lines.append(Line(i=i, page=page, text=text, x0=x0, y0=y0, x1=x0 + 0.45 * size * len(text), y1=y0 + size,
                          size=size, bold=bold, start=pos, end=pos + len(text), italic=italic))
        pos += len(text) + 1
    pages = [Page(n=n, width=595, height=842, origin_x=0, origin_y=0, rotation=0, has_text=True)
             for n in range(1, max(r[0] for r in rows) + 1)]
    return Extraction(pages, lines, "\n".join(r[1] for r in rows))


def _body(page: int, y0: float, n: int, x0: float = 122) -> list[Row]:
    # Each line its own words: text repeated at one height on many pages reads as a running header.
    return [(page, f"{BODY} {next(WORDS)}", 11.0, False, False, x0, y0 - 12 * k) for k in range(n)]


def _title(page: int, text: str, y0: float) -> Row:
    """An italic paragraph title centred between the margins."""
    width = 0.45 * 11.0 * len(text)
    return (page, text, 11.0, False, True, 299 - width / 2, y0)


def _paragraph(page: int, number: str, y0: float, n: int = 3) -> list[Row]:
    """A numbered paragraph: its number alone at the margin, its first line on the same row."""
    return [(page, number, 11.0, False, False, 93, y0), *_body(page, y0, n)]


def _sections(ext: Extraction) -> dict[str, tuple[str, int]]:
    return {r.title: (r.number, r.level) for r in RulesStrategy()._rules(ext)}


def _texts(ext: Extraction, loose: bool = False) -> list[str]:
    return [ln.text for ln, _ in candidates(ext, loose=loose)]


def _schedule_page(below: list[Row]) -> Extraction:
    # The title sits 7 points above the row under it: closer than the most of a blank line a cross-heading has.
    return _ext([*_body(1, 760, 4), _title(1, "Power to stop, board, divert and detain", 700), *below])


def test_references_that_open_a_line_are_not_headings():
    ext = _ext([(1, "1 Offences", 11.0, True, False, 93, 760), *_body(1, 740, 3),
                (1, "An offence under any of the following provisions of the Offences against the", 11.0, False, False,
                 144, 690),
                (1, "Person Act 1861—", 11.0, False, False, 144, 678),
                (1, "section 4 (soliciting murder)", 11.0, False, False, 162, 664),
                (1, "section 16 (threats to kill)", 11.0, False, False, 162, 650),
                (1, "Part 7 of the Sentencing Code (sentencing)", 11.0, False, False, 122, 630), *_body(1, 618, 2),
                (1, "Section 5 Penalties", 11.0, False, False, 93, 580), *_body(1, 560, 3)])
    strict = _texts(ext)
    assert not any(t.startswith(("section 4", "section 16", "Part 7")) for t in strict)
    assert "Section 5 Penalties" in strict  # a capitalised label in body type that does not run on still counts
    assert "section 4 (soliciting murder)" in _texts(ext, loose=True)  # Quick's model still sees it


def _act() -> Extraction:
    rows: list[Row] = []

    def label(page: int, text: str, title: str, y0: float, note: str = "") -> None:
        rows.append((page, text, 11.0, text.startswith("PART"), False, 265, y0))
        if note:
            rows.append((page, note, 8.0, False, False, 471, y0 + 1.5))
        rows.append((page, title, 9.0, False, False, 220, y0 - 24))

    def cross(page: int, text: str, y0: float, section: str) -> None:
        rows.extend([_title(page, text, y0), (page, section, 11.0, True, False, 93, y0 - 30), *_body(page, y0 - 50, 3)])

    def paragraph(page: int, text: str, number: str, y0: float) -> None:
        rows.extend([_title(page, text, y0), *_paragraph(page, number, y0 - 18)])

    label(1, "PART 1", "OFFENCES", 760)
    cross(1, "Slavery", 700, "1 Slavery, servitude and forced labour")
    rows.extend([(1, "2 Human trafficking", 11.0, True, False, 93, 560), *_body(1, 540, 3)])
    label(2, "PART 2", "PREVENTION ORDERS", 520)
    cross(2, "Prevention orders", 460, "3 Prevention orders on sentencing")
    label(3, "SCHEDULE 1", "OFFENCES", 640, note="Section 1")
    paragraph(3, "Theft Act 1968 (c. 60)", "1", 580)
    paragraph(3, "Fraud Act 2006 (c. 35)", "2", 480)
    label(4, "SCHEDULE 2", "ENFORCEMENT POWERS", 400, note="Section 3")
    label(4, "PART 1", "ENGLAND AND WALES", 340)
    paragraph(4, "Introductory", "1", 280)
    paragraph(4, "Power to stop and board", "2", 200)
    label(5, "PART 2", "SCOTLAND", 300)
    paragraph(5, "Introductory", "3", 240)
    paragraph(5, "Power of arrest", "4", 160)
    return _ext(rows)
