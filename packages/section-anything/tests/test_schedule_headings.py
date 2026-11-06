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


def test_a_paragraph_title_over_its_numbered_paragraph_is_a_heading_with_its_number():
    ext = _schedule_page([*_paragraph(1, "2", 682), *_body(1, 640, 3)])
    assert "Power to stop, board, divert and detain" in _texts(ext)
    assert "Power to stop, board, divert and detain" in _texts(ext, loose=True)
    assert _sections(ext)["Power to stop, board, divert and detain"][0] == "2"


def test_without_a_number_at_the_margin_the_close_line_is_not_a_heading():
    # Italic text close above a paragraph with no number of its own: emphasis or a quotation, as before.
    assert "Power to stop, board, divert and detain" not in _texts(_schedule_page(_body(1, 682, 4)))
    # A number run into the paragraph's first line is no bare paragraph number either.
    run_in = _schedule_page([(1, "2 " + BODY, 11.0, False, False, 93, 682), *_body(1, 670, 3)])
    assert "Power to stop, board, divert and detain" not in _texts(run_in)


def test_a_cross_heading_in_a_contents_list_is_not_a_paragraph_title():
    # Contents entries sit like numbered paragraphs, but each is a short title that neither fills its line
    # nor ends like a clause.
    ext = _schedule_page([(1, "1", 11.0, False, False, 96, 682),
                          (1, "Implementation of the 1996 Hague Convention", 11.0, False, False, 114, 682),
                          (1, "2", 11.0, False, False, 96, 670),
                          (1, "Implementation of other agreements", 11.0, False, False, 114, 670), *_body(1, 620, 3)])
    assert "Power to stop, board, divert and detain" not in _texts(ext)


def test_a_bold_section_heading_under_an_italic_line_lends_it_no_number():
    ext = _schedule_page([(1, "2 Interpretation of this Part of this Schedule and of the next", 11.0, True, False, 93,
                           682), *_body(1, 660, 3)])
    assert "Power to stop, board, divert and detain" not in _texts(ext)


def test_a_list_read_before_the_paragraph_line_does_not_continue_the_title():
    # The extractor can read the indented list under the paragraph's first line straight after the title.
    ext = _ext([*_body(1, 760, 4), _title(1, "Offences against the Person Act 1861 (c. 100)", 700),
                (1, "section 4 (soliciting murder)", 11.0, False, False, 162, 668),
                (1, "7", 11.0, False, False, 93, 682),
                (1, "An offence under any of the following provisions of that Act—", 11.0, False, False, 144, 682),
                (1, "section 16 (threats to kill)", 11.0, False, False, 162, 656), *_body(1, 620, 3)])
    sections = _sections(ext)
    assert sections["Offences against the Person Act 1861 (c. 100)"][0] == "7"
    assert not any(t.startswith("section") for t in _texts(ext))


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


def test_parts_and_paragraph_titles_nest_under_their_schedule():
    s = _sections(_act())
    # The body: Part, cross-heading, section.
    assert s["OFFENCES"][1] == 1 and s["Slavery"][1] == 2 and s["Slavery, servitude and forced labour"][1] == 3
    # A schedule sits beside the Parts; its Parts one level below it, their paragraph titles below them.
    assert s["ENFORCEMENT POWERS"] == ("SCHEDULE 2", 1)
    assert s["ENGLAND AND WALES"] == ("PART 1", 2) and s["SCOTLAND"] == ("PART 2", 2)
    assert s["Power to stop and board"] == ("2", 3) and s["Power of arrest"] == ("4", 3)
    # A schedule with no Parts holds its paragraph titles one level below it.
    assert s["Theft Act 1968 (c. 60)"] == ("1", 2) and s["Fraud Act 2006 (c. 35)"] == ("2", 2)


def test_a_label_with_an_amendment_mark_keeps_its_side_note_and_title():
    # A revised Act runs the amendment mark into the label ("[F76SCHEDULE 4A"), which sets the line taller.
    ext = _ext([*_body(1, 760, 3),
                (1, "[F76SCHEDULE 4A", 11.0, False, False, 254, 600), (1, "Section 54A", 8.0, False, False, 466, 603.5),
                (1, "INFORMATION GATEWAYS: SPECIFIED PERSONS", 9.0, False, False, 195, 576), *_body(1, 540, 3)])
    ext.lines[3].y1 = 612.9
    sections = _sections(ext)
    assert sections["INFORMATION GATEWAYS: SPECIFIED PERSONS"][0] == "SCHEDULE 4A"
    assert "Section 54A" not in " ".join(sections)


def test_a_title_read_before_its_label_joins_it():
    # The extractor reads the title, printed under the label, just before the label.
    ext = _ext([*_body(1, 760, 3),
                (1, "PUBLIC AUTHORITIES UNDER A DUTY TO CO-OPERATE", 9.0, False, False, 118, 576),
                (1, "SCHEDULE 3", 11.0, False, False, 265, 600), (1, "Section 43", 8.0, False, False, 471, 601.5),
                (1, "Commencement Information", 10.0, True, False, 97, 540), *_body(1, 500, 3)])
    sections = _sections(ext)
    assert sections["PUBLIC AUTHORITIES UNDER A DUTY TO CO-OPERATE"][0] == "SCHEDULE 3"
    assert "Commencement Information" not in sections
    # A title that wraps onto a second line comes whole.
    wrapped = _ext([*_body(1, 760, 3),
                    (1, "REDUCING CARBON EMISSIONS AND HOME-HEATING COSTS: MINOR AND", 8.8, False, False, 91, 576),
                    (1, "CONSEQUENTIAL AMENDMENTS", 8.8, False, False, 230, 565),
                    (1, "SCHEDULE 1", 11.0, False, False, 263, 600), (1, "Section 72", 8.0, False, False, 469, 601),
                    _title(1, "Gas Act 1986", 540), *_paragraph(1, "1", 522)])
    title = "REDUCING CARBON EMISSIONS AND HOME-HEATING COSTS: MINOR AND CONSEQUENTIAL AMENDMENTS"
    sections = _sections(wrapped)
    assert sections[title][0] == "SCHEDULE 1"
    assert sections["Gas Act 1986"][0] == "1"
