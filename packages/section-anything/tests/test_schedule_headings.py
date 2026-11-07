"""A UK Act's schedules in Free (research finding F065): a schedule paragraph's own italic title sits close
above the paragraph, whose number stands alone at the margin; lines that open with a reference in body type
("section 4 (soliciting murder)") are not headings; Parts and paragraph titles inside a schedule nest under
it; a label with an amendment mark run into it, or read after its title, still opens a heading. Also: titles
wrapped over two italic lines, numbers with an amendment mark, group headings in a schedule's lists, quoted
amendments, the Act's title block, and keep_strong putting a revised Act's italic headings back."""

from __future__ import annotations

import asyncio

from section_anything import keep, pipeline
from section_anything.extract import Extraction, Line, Page
from section_anything.llm import Usage
from section_anything.strategies.base import Context
from section_anything.strategies.rules import RulesStrategy, candidates

BODY = "(2) The constable may require any person on the ship to give information about the ship and its"
WORDS = iter(f"{a}{v}{b}" for a in "bcdfghjklmnprstvwz" for v in "aeiou" for b in ("ne", "re", "te", "le", "ge", "ve", "nt", "ry"))
# (page, text, size, bold, italic, x0, y0): y0 is the bottom of the line, top of the page first.
Row = tuple[int, str, float, bool, bool, float, float]


def _ext(rows: list[Row]) -> Extraction:
    lines, pos = [], 0
    for i, (page, text, size, bold, italic, x0, y0) in enumerate(rows):
        lines.append(Line(i=i, page=page, text=text, x0=x0, y0=y0, x1=min(505.0, x0 + 0.45 * size * len(text)), y1=y0 + size,
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


def test_a_paragraph_title_wrapped_over_two_centred_italic_lines_is_one_heading():
    title = ("Human Trafficking and Exploitation (Criminal Justice and", "Support for Victims) Act (Northern Ireland) 2015")
    ext = _ext([*_body(1, 760, 4), _title(1, title[0], 696), _title(1, title[1], 684), *_paragraph(1, "8", 666),
                *_body(1, 620, 3)])
    assert _sections(ext)[" ".join(title)][0] == "8"
    # Two italic lines at the margin are an italic paragraph's lines, as before.
    flush = _ext([*_body(1, 760, 4), (1, title[0], 11.0, False, True, 122, 696), (1, title[1], 11.0, False, True, 122, 684),
                  *_paragraph(1, "8", 666), *_body(1, 620, 3)])
    assert not {title[0], title[1]} & set(_texts(flush))


def test_a_paragraph_number_with_an_amendment_mark_still_marks_the_title():
    def page(previous: str) -> Extraction:
        return _ext([*_body(1, 780, 2), _title(1, "Criminal Justice Act 1991 (c. 53)", 740), *_paragraph(1, previous, 722, 2),
                     _title(1, "Proceeds of Crime Act 2002 (c. 29)", 660),
                     (1, "[F8115", 8.8, True, False, 93, 642),
                     (1, "In section 13(3A) of the Proceeds of Crime Act 2002 (effect of confiscation orders", 11.0, False,
                      False, 144, 642), *_body(1, 630, 2)])
    # Paragraph 13 came before (14 was repealed): note F81, paragraph 15.
    assert _sections(page("13"))["Proceeds of Crime Act 2002 (c. 29)"][0] == "15"
    # No tail of the digits follows the last plain number: the title stays, without a number.
    assert _sections(page("7"))["Proceeds of Crime Act 2002 (c. 29)"][0] == ""


def _authorities(schedule: bool) -> Extraction:
    rows: list[Row] = [*_body(1, 780, 3)]
    if schedule:
        rows += [(1, "SCHEDULE 3", 11.0, False, False, 265, 720), (1, "PUBLIC AUTHORITIES", 9.0, False, False, 250, 696)]
    rows += [(1, "Local government", 11.0, False, True, 90, 660),
             (1, "A county council in England or Wales.", 11.0, False, False, 114, 646),
             (1, "A district council in England.", 11.0, False, False, 114, 632),
             (1, "Health bodies", 11.0, False, True, 90, 618),
             (1, "A Local Health Board established under section 11 of the Act.", 11.0, False, False, 114, 604),
             (1, "Other", 11.0, False, True, 287, 588),
             (1, "The Independent Anti-slavery Commissioner.", 11.0, False, False, 114, 574),
             (1, "SCHEDULE 5", 11.0, False, False, 265, 530), (1, "MINOR AMENDMENTS", 9.0, False, False, 240, 506),
             *_body(1, 480, 3)]
    return _ext(rows)


def test_group_headings_in_a_schedules_list_are_headings():
    sections = _sections(_authorities(schedule=True))
    assert {"Local government", "Health bodies", "Other"} <= set(sections)
    # A schedule's label after an italic group heading opens its own heading.
    assert sections["MINOR AMENDMENTS"][0] == "SCHEDULE 5"
    # Outside a schedule the same lines are left alone.
    assert not {"Local government", "Health bodies"} & set(_texts(_authorities(schedule=False)))


def test_a_quoted_heading_of_another_text_is_not_a_heading():
    ext = _ext([(1, "1 Offences", 11.0, True, False, 93, 760), *_body(1, 740, 3),
                (1, "“Slavery etc", 11.0, True, False, 162, 690), (1, "offences", 11.0, True, False, 162, 678),
                *_body(1, 660, 2, x0=162),
                (1, "32A “Victims of slavery, servitude or forced labour", 11.0, True, False, 132, 620),
                *_body(1, 600, 2),
                (1, "2 “Smart” contracts", 11.0, True, False, 93, 560), *_body(1, 540, 3)])
    texts = _texts(ext)
    assert not any(t.startswith(("“Slavery", "offences", "32A")) for t in texts)
    assert "2 “Smart” contracts" in texts  # a quotation it closes is its own


def _titled_act() -> Extraction:
    rows: list[Row] = [(1, "Modern Slavery Act 2015", 24.0, False, False, 173, 780),
                       (1, "2015 CHAPTER 30", 12.0, True, False, 247, 748),
                       (1, "An Act to make provision about slavery, servitude and forced or compulsory labour", 12.0,
                        False, False, 90, 712),
                       (1, "[26th March 2015]", 12.0, False, False, 414, 698), (1, "and for connected purposes.", 12.0,
                                                                             False, False, 90, 698),
                       *_body(1, 660, 2, x0=90),
                       (1, "PART 1", 11.0, True, False, 279, 620), (1, "OFFENCES", 9.0, False, False, 274, 596),
                       (1, "1 Slavery", 11.0, True, False, 93, 560), *_body(1, 540, 3),
                       (2, "PART 2", 11.0, True, False, 279, 760), (2, "ORDERS", 9.0, False, False, 274, 736),
                       (2, "2 Orders", 11.0, True, False, 93, 700), *_body(2, 680, 3),
                       (2, "SCHEDULE 1", 11.0, False, False, 265, 600), (2, "OFFENCES LISTED", 9.0, False, False, 240, 576),
                       *_body(2, 540, 3)]
    return _ext(rows)


def test_an_acts_citation_and_long_title_are_not_headings_and_its_parts_stay_at_the_top():
    sections = _sections(_titled_act())
    assert not any(t.startswith(("CHAPTER 30", "An Act", "and for connected", "[26th")) for t in sections)
    assert "Modern Slavery Act 2015" in sections
    # The document's title stands outside the hierarchy: the Parts and the schedule are level 1.
    assert sections["OFFENCES"] == ("PART 1", 1) and sections["OFFENCES LISTED"] == ("SCHEDULE 1", 1)


def test_keep_strong_puts_a_revised_acts_italic_headings_back_under_the_models_levels():
    ext = _act()
    ctx = Context(model="fake", usage=Usage(), cost_cap_usd=1.0, progress=lambda _f, _m: None)

    async def put_back():
        free = await pipeline.free_sections(ext)
        italic = keep.italic_headings(free, ext)
        # The model lists the labels and sections, one level deeper than Free, and none of the italic lines.
        model = [{**s, "level": s["level"] + 1} for s in free if s["first_line"] not in italic]
        return free, italic, await keep.put_back(free, model, ext, ctx, "ask")

    async def no_call(**kw):
        raise AssertionError("no ask call expected")

    keep.structured, saved = no_call, keep.structured
    try:
        free, italic, added = asyncio.run(put_back())
    finally:
        keep.structured = saved
    titles = {r.title: r.level for r in added}
    assert len(italic) >= keep.TITLED_PARAGRAPHS_MIN and "Power to stop and board" in titles
    # Placed against the model's own level for the Part above it: one deeper.
    assert titles["Power to stop and board"] == 4 and titles["Theft Act 1968 (c. 60)"] == 3
    assert all(r.get("italic_heading") for r in ctx.usage.kept_strong["restored"])


def _sections_with_marks() -> Extraction:
    """A revised Act's bold section headings, two of them inserted ("[F1111A") or omitted ("F5755") with the
    amendment note's mark run into the number."""
    rows: list[Row] = []
    heads = ["11 Forfeiture of land vehicle, ship or aircraft", "[F1111A Enforcement by Gangmasters and Labour Abuse Authority",
             "12 Detention of land vehicle, ship or aircraft", "54 Transparency in supply chains etc",
             "[F5454A Gangmasters and Labour Abuse Authority: information gateways", "F5755 Gangmasters Licensing Authority",
             "56 Interpretation", "F16 Engines and airframes"]
    for k, head in enumerate(heads):
        page = 1 + k // 2
        y0 = 760 if k % 2 == 0 else 420
        rows += [(page, head, 11.0, True, False, 87, y0), *_body(page, y0 - 18, 4)]
    return _ext(rows)


def test_quick_shows_an_amendment_marked_section_number_as_the_reader_sees_it():
    from section_anything.strategies.llm_text import LlmReviewStrategy, _amended_number

    assert _amended_number("1111", "A", 11) == "11A" and _amended_number("3630", "A", 30) == "30A"
    assert _amended_number("5755", "", 54) == "55" and _amended_number("4950", "A", 50) == "50A"
    assert _amended_number("5755", "", 12) is None and _amended_number("1111", "A", None) is None
    assert _amended_number("16", "", 15) is None  # no mark left once the number is taken
    ext = _sections_with_marks()
    rows = {ext.lines[i].text: row.split("  ⟶")[0].split("⟨B⟩ ", 1)[1] for i, row in LlmReviewStrategy()._rows(ext)}
    assert rows["[F1111A Enforcement by Gangmasters and Labour Abuse Authority"] == (
        "11A Enforcement by Gangmasters and Labour Abuse Authority")
    assert rows["[F5454A Gangmasters and Labour Abuse Authority: information gateways"].startswith("54A Gangmasters")
    assert rows["F5755 Gangmasters Licensing Authority"] == "55 Gangmasters Licensing Authority"
    assert rows["F16 Engines and airframes"] == "F16 Engines and airframes"  # 16 does not follow 56 with a mark left


def test_quick_keeps_an_amendment_marked_section_at_its_printed_line():
    import re

    from section_anything.strategies import llm_text
    from section_anything.strategies.llm_text import LlmReviewStrategy, ReviewItem, ReviewResult

    ext = _sections_with_marks()

    async def model(**kw):  # keeps a candidate only when its row opens with a section number
        items = []
        for m in re.finditer(r"^(\d+)\| p\d+ \S+ (\d+[A-Z]?) (.*?)  ⟶", kw["user"], re.M):
            items.append(ReviewItem(id=int(m.group(1)), is_heading=True, level=1, number=m.group(2), title=m.group(3)))
        return ReviewResult(items=items)

    llm_text.structured, saved = model, llm_text.structured
    try:
        ctx = Context(model="fake", usage=Usage(), cost_cap_usd=1.0, progress=lambda _f, _m: None)
        raw = asyncio.run(LlmReviewStrategy().run(ext, ctx))
    finally:
        llm_text.structured = saved
    sections, _ = pipeline.resolve(raw, ext, pipeline.Locator(ext.text))
    got = {(s["number"], s["title"]): ext.lines[s["first_line"]].text for s in sections}
    assert got[("11A", "Enforcement by Gangmasters and Labour Abuse Authority")].startswith("[F1111A")
    assert got[("55", "Gangmasters Licensing Authority")] == "F5755 Gangmasters Licensing Authority"
