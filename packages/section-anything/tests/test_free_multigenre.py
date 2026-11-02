"""Free mode on layouts from the multi-genre test set (research finding F045): flat outlines, bookmark
titles glued to their number, contents pages that span pages, headers repeated on consecutive pages,
table rows and bare structural labels above their title."""

from __future__ import annotations

from conftest import body, write_pdf

from section_anything import section
from section_anything.extract import Extraction, Line, OutlineItem, Page
from section_anything.strategies.rules import _flat_outline_levels, candidates
from section_anything.structure import Anchored, anchor_bookmarks


def _ext(rows: list[tuple[int, str, float, bool, float, float]], outline: list[OutlineItem] | None = None) -> Extraction:
    """An extraction from (page, text, size, bold, x0, y0) rows, in reading order."""
    lines, pos = [], 0
    for i, (page, text, size, bold, x0, y0) in enumerate(rows):
        lines.append(Line(i=i, page=page, text=text, x0=x0, y0=y0, x1=x0 + 5.5 * len(text), y1=y0 + size,
                          size=size, bold=bold, start=pos, end=pos + len(text)))
        pos += len(text) + 1
    pages = [Page(n=n, width=612, height=792, origin_x=0, origin_y=0, rotation=0, has_text=True)
             for n in range(1, max(r[0] for r in rows) + 1)]
    return Extraction(pages, lines, "\n".join(ln.text for ln in lines), outline=outline or [])


def _anchored(titles: list[str]) -> tuple[list[Anchored], list[Line]]:
    ext = _ext([(1, t, 10, True, 72, 700 - 20 * k) for k, t in enumerate(titles)])
    return [Anchored(line=k, level=1, number="", title=t) for k, t in enumerate(titles)], ext.lines


def test_flat_outline_takes_levels_from_its_labels():
    titles = ["Gesetz über Beispiele", "Teil 1 Allgemeines", "Kapitel 1 Anwendungsbereich", "§ 1 Zweck",
              "§ 2 Begriffe", "Kapitel 2 Verfahren", "Abschnitt 1 Antrag", "§ 3 Form", "§ 4 Frist",
              "Teil 2 Besonderes", "Kapitel 1 Aufsicht", "§ 5 Zuständigkeit", "§ 6 Befugnisse"]
    backbone, lines = _anchored(titles)
    _flat_outline_levels(backbone, lines)
    level = {a.title: a.level for a in backbone}
    assert level["Teil 1 Allgemeines"] < level["Kapitel 1 Anwendungsbereich"] < level["Abschnitt 1 Antrag"]
    assert level["Abschnitt 1 Antrag"] < level["§ 3 Form"]
    assert level["Gesetz über Beispiele"] < level["Teil 1 Allgemeines"]
    assert level["§ 1 Zweck"] == level["§ 6 Befugnisse"]


def test_numbered_sections_and_cross_headings_of_a_flat_outline():
    titles = ["Part 1 General", "Interpretation", "1 Meaning of terms", "2 Application", "Powers",
              "3 Power to make rules", "Part 2 Final", "Commencement", "4 Commencement", "5 Short title"]
    backbone, lines = _anchored(titles)
    _flat_outline_levels(backbone, lines)
    level = {a.title: a.level for a in backbone}
    assert level["Part 1 General"] < level["Interpretation"] < level["1 Meaning of terms"]
    assert level["Powers"] == level["Interpretation"]


def test_outline_with_levels_or_without_labels_is_left_alone():
    backbone, lines = _anchored(["Teil 1 A", "Kapitel 1 B", "§ 1 C", "§ 2 D", "Kapitel 2 E", "§ 3 F"])
    backbone[1].level = 2
    _flat_outline_levels(backbone, lines)
    assert [a.level for a in backbone] == [1, 2, 1, 1, 1, 1]
    backbone, lines = _anchored(["Introduction", "Background", "Method", "Results", "Discussion", "Summary"])
    _flat_outline_levels(backbone, lines)
    assert {a.level for a in backbone} == {1}


def test_bookmark_glued_to_its_number_is_anchored():
    ext = _ext([(1, "Teil 1", 12, True, 72, 700), (1, "Gemeinsame Bestimmungen", 12, True, 72, 680),
                (1, "Body text of the first part.", 10, False, 72, 650)],
               outline=[OutlineItem(level=1, title="Teil 1Gemeinsame Bestimmungen", page=1, y=712)])
    (a,) = anchor_bookmarks(ext)
    assert a.line == 0 and a.title == "Teil 1 Gemeinsame Bestimmungen"


def test_cells_of_a_table_row_are_not_headings():
    rows = [(1, "Results", 14, True, 72, 700), (1, "Ordinary body text runs here for a while.", 10, False, 72, 670),
            (1, "Total", 10, True, 72, 640), (1, "1,234", 10, True, 300, 640), (1, "5,678", 10, True, 400, 640),
            (1, "Ordinary body text runs here for a while.", 10, False, 72, 610),
            (1, "Ordinary body text runs here for a while.", 10, False, 72, 595)]
    texts = [ln.text for ln, _ in candidates(_ext(rows))]
    assert "Results" in texts and "Total" not in texts


def test_a_heading_beside_another_column_is_kept():
    rows = [(1, "2 Methods", 12, True, 72, 700), (1, "the other column's body text, set at the same height", 10,
                                                   False, 320, 700),
            (1, "Ordinary body text runs here for a while.", 10, False, 72, 680),
            (1, "Ordinary body text runs here for a while.", 10, False, 72, 665)]
    assert "2 Methods" in [ln.text for ln, _ in candidates(_ext(rows))]


def _two_columns(y0: float) -> list[tuple[int, str, float, bool, float, float]]:
    """Body text of a two-column page, five lines per column, from y0 down."""
    text = "Column body text runs on for a while."
    return [(1, text, 10, False, x0, y0 - 15 * k) for k in range(5) for x0 in (72, 320)]


def test_a_heading_beside_an_equation_in_the_other_column_is_kept():
    rows = _two_columns(500) + [(1, "f + r = g", 10, False, 72, 700), (1, "(3.1)", 10, False, 250, 700),
                                (1, "4. EXPERIMENTS", 10, True, 320, 700)]
    assert "4. EXPERIMENTS" in [ln.text for ln, _ in candidates(_ext(rows))]


def test_a_table_row_across_both_columns_is_still_cells():
    rows = _two_columns(500) + [(1, "Total", 10, True, 72, 700), (1, "1,234", 10, True, 200, 700),
                                (1, "5,678", 10, True, 400, 700)]
    assert "Total" not in [ln.text for ln, _ in candidates(_ext(rows))]


def test_the_abstract_heading_is_never_a_cell():
    rows = [(1, "Abstract—", 10, True, 72, 700), (1, "We study a thing", 10, False, 125, 700),
            (1, "and its use.", 10, False, 300, 700),
            (1, "Ordinary body text runs here for a while.", 10, False, 72, 680)]
    assert "Abstract—" in [ln.text for ln, _ in candidates(_ext(rows))]


def test_bare_label_above_its_title_joins_it(tmp_path):
    pdf = write_pdf(tmp_path / "reg.pdf", [
        [("CHAPITRE I", 9, False), ("OBJET ET DEFINITIONS", 9, True), ("Article premier", 10, False),
         ("Objet", 10, True), *body(4), ("Article 2", 10, False), ("Definitions", 10, True), *body(4)],
    ])
    titles = [f"{s['number']} {s['title']}".strip() for s in (dict(x) for x in section(pdf, mode="free").sections)]
    assert "CHAPITRE I OBJET ET DEFINITIONS" in titles
    assert "Article premier Objet" in titles and "Article 2 Definitions" in titles


def test_contents_continued_on_the_next_page_are_not_headings(tmp_path):
    entries = [(f"{c}.{k}. Topic {c}.{k}", 10, False) for c in range(1, 4) for k in range(1, 6)]
    pdf = write_pdf(tmp_path / "toc.pdf", [
        [("Table of Contents", 14, True), *entries[:9]],
        [*entries[9:]],
        [("1. Introduction", 14, True), *body(5), ("1.1. Topic 1.1", 12, True), *body(4)],
    ])
    found = [(s["page_start"], s["title"]) for s in (dict(x) for x in section(pdf, mode="free").sections)]
    assert all(page == 3 for page, _ in found), found


def test_header_repeated_on_three_pages_in_a_row_is_not_a_heading(tmp_path):
    pages = [[(f"Chapter {k + 1}", 14, True), *body(6)] for k in range(12)]
    for k in (4, 5, 6):
        pages[k] = [("Part 2 - General Provisions", 11, True), *body(6)]
    titles = [s["title"] for s in section(write_pdf(tmp_path / "hdr.pdf", pages), mode="free").sections]
    assert "Part 2 - General Provisions" not in " ".join(titles)


def test_regulation_labels_set_the_levels_when_typography_inverts_them(tmp_path):
    """An EU regulation sets "KAPITEL I" smaller than "Artikel 1"; the labels still put chapters above
    articles, and a title wrapped onto a second bold line stays one heading."""
    pdf = write_pdf(tmp_path / "eu.pdf", [
        [("KAPITEL I", 9, False), ("ALLGEMEINE BESTIMMUNGEN", 9, True), ("Artikel 1", 10, False),
         ("Gegenstand und Ziele der Verordnung", 10, True), *body(4), ("Artikel 2", 10, False),
         ("Bestimmungen uber die Forderfahigkeit von Personen", 10, True), ("und Stellen im Rahmen der Fazilitat", 10, True),
         *body(4)],
        [("KAPITEL II", 9, False), ("FINANZIERUNG", 9, True), ("Artikel 3", 10, False), ("Mittel", 10, True), *body(4)],
    ])
    secs = {f"{s['number']} {s['title']}".strip(): s["level"] for s in (dict(x) for x in section(pdf, mode="free").sections)}
    assert secs["KAPITEL I ALLGEMEINE BESTIMMUNGEN"] < secs["Artikel 1 Gegenstand und Ziele der Verordnung"]
    assert secs["KAPITEL II FINANZIERUNG"] == secs["KAPITEL I ALLGEMEINE BESTIMMUNGEN"]
    assert "Artikel 2 Bestimmungen uber die Forderfahigkeit von Personen und Stellen im Rahmen der Fazilitat" in secs


def test_a_title_in_capitals_under_a_bold_label_joins_it(tmp_path):
    pdf = write_pdf(tmp_path / "act.pdf", [
        [("CHAPTER 2", 9, True), ("REVIEW BY APPROPRIATE MINISTER", 9, False), *body(6)],
    ])
    titles = [f"{s['number']} {s['title']}".strip() for s in (dict(x) for x in section(pdf, mode="free").sections)]
    assert "CHAPTER 2 REVIEW BY APPROPRIATE MINISTER" in titles


def test_papers_keep_numbering_levels_with_appendices():
    """Numbered sections plus "Appendix A" are one label kind: the typography path keeps its levels."""
    from section_anything.strategies.rules import _label_levels

    texts = ["1 Introduction", "2 Method", "2.1 Data", "3 Results", "References", "Appendix A Proofs"]
    assert _label_levels(texts, numbers_count=False, min_share=0.3) is None


def test_flat_outline_of_a_paper_is_left_alone():
    backbone, lines = _anchored(["Abstract", "1 Introduction", "2 Method", "3 Results", "References", "Appendix A Proofs"])
    _flat_outline_levels(backbone, lines)
    assert {a.level for a in backbone} == {1}


def test_thesis_chapters_and_appendices_keep_typography_levels():
    from section_anything.strategies.rules import _label_levels

    texts = ["Abstract", "Chapter 1 Introduction", "1.1 Background", "Chapter 2 Method", "Appendix A Proofs"]
    assert _label_levels(texts, numbers_count=False, min_share=0.3) is None
