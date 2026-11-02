"""Docling's output as input: a DoclingDocument as the lines (no PDF text layer needed), or as hints
for a PDF's own lines.

The documents here are DoclingDocument JSON built by hand, with boxes taken from our own extraction
of the test PDF, so no Docling run is needed. The round trip through `to_docling_document()` skips
unless docling-core is installed.
"""

from __future__ import annotations

from typing import Any

import pytest

import section_anything
from section_anything.docling_input import attach_hints, extraction_from_docling, is_docling_document
from section_anything.extract import Line, extract
from section_anything.strategies.rules import candidates

from conftest import body, write_pdf

PAGE = {"width": 612.0, "height": 792.0}


def docling_json(items: list[dict[str, Any]], pages: int = 1, page: dict | None = None) -> dict[str, Any]:
    """A DoclingDocument's JSON with one text item per entry: {label, text, page, box (l, b, r, t)
    and, for a section header, level}; page headers and footers go to the furniture tree."""
    texts, body_refs, furniture_refs = [], [], []
    for k, it in enumerate(items):
        furniture = it["label"] in ("page_header", "page_footer")
        left, b, r, t = it["box"]
        texts.append({
            "self_ref": f"#/texts/{k}", "parent": {"$ref": "#/furniture" if furniture else "#/body"}, "children": [],
            "content_layer": "furniture" if furniture else "body", "label": it["label"],
            "prov": [{"page_no": it.get("page", 1), "bbox": {"l": left, "t": t, "r": r, "b": b, "coord_origin": "BOTTOMLEFT"},
                      "charspan": [0, len(it["text"])]}],
            "orig": it["text"], "text": it["text"], **({"level": it["level"]} if "level" in it else {}),
        })
        (furniture_refs if furniture else body_refs).append({"$ref": f"#/texts/{k}"})
    root = {"children": [], "content_layer": "body", "name": "_root_", "label": "unspecified"}
    return {
        "schema_name": "DoclingDocument", "version": "1.10.0", "name": "test",
        "body": {**root, "self_ref": "#/body", "children": body_refs},
        "furniture": {**root, "self_ref": "#/furniture", "children": furniture_refs, "content_layer": "furniture"},
        "groups": [], "texts": texts, "pictures": [], "tables": [], "key_value_items": [], "form_items": [],
        "pages": {str(n): {"size": page or PAGE, "page_no": n} for n in range(1, pages + 1)},
    }


def item(label: str, text: str, top: float, height: float = 12.0, page: int = 1, **kw: Any) -> dict[str, Any]:
    return {"label": label, "text": text, "page": page, "box": (72.0, top - height, 400.0, top), **kw}


SCANNED = docling_json([
    item("page_header", "Annual Report 2026", 770, 8),
    item("title", "Annual Report", 720, 24),
    item("section_header", "1 Overview", 680, level=1),
    item("text", "The year in brief. " * 8, 660, 40),
    item("section_header", "1.1 Highlights", 610, level=2),
    item("text", "Revenue grew and costs fell. " * 6, 590, 40),
    item("section_header", "2 Outlook", 540, level=1),
    item("text", "Next year we expect more of the same. " * 5, 520, 40),
    item("page_footer", "Page 1", 30, 8),
])


def headings(tree) -> list[tuple[int, str]]:
    return [(s["level"], (s["number"] + " " + s["title"]).strip()) for s in tree.sections
            if "front_matter" not in s["flags"]]


# -- A DoclingDocument as the input --------------------------------------------------------------


def test_docling_document_alone_gives_its_headings_and_levels():
    assert is_docling_document(SCANNED)
    tree = section_anything.section(SCANNED)
    assert headings(tree) == [(1, "Annual Report"), (1, "1 Overview"), (2, "1.1 Highlights"), (1, "2 Outlook")]
    assert "doc_title" in tree.sections[0]["flags"]
    assert tree.text.startswith("Annual Report 2026\nAnnual Report\n1 Overview")  # page header first
    assert tree.text.endswith("Page 1")  # page footer last
    overview = next(s for s in tree.sections if s["title"] == "Overview")
    assert tree.text[overview["start"]:overview["end"]].startswith("1 Overview\nThe year in brief.")


def test_extraction_from_docling_marks_furniture_and_headings():
    ext = extraction_from_docling(SCANNED)
    found = {ln.text for ln, _ in candidates(ext)}
    assert found == {"Annual Report", "1 Overview", "1.1 Highlights", "2 Outlook"}  # not the page header or footer
    assert [ln.page for ln in ext.lines] == [1] * 9
    assert [(o.level, o.title) for o in ext.outline] == [  # Docling's levels act as the outline
        (1, "Annual Report"), (1, "1 Overview"), (2, "1.1 Highlights"), (1, "2 Outlook")]


def test_flat_levels_come_from_box_heights():
    """Docling's default pipeline gives every header level 1: the box heights decide, and heights
    within 10% of each other are one size."""
    doc = docling_json([
        item("section_header", "Part One", 700, 24, level=1),
        item("text", "Body text of part one. " * 5, 670, 30),
        item("section_header", "Background", 620, 14, level=1),
        item("text", "Body text of the background. " * 5, 600, 30),
        item("section_header", "Method", 550, 15, level=1),  # one size with "Background"
        item("text", "Body text of the method. " * 5, 530, 30),
        item("section_header", "Part Two", 480, 23, level=1),
        item("text", "Body text of part two. " * 5, 450, 30),
    ])
    tree = section_anything.section(doc)
    assert headings(tree) == [(1, "Part One"), (2, "Background"), (2, "Method"), (1, "Part Two")]


def test_docling_document_errors():
    with pytest.raises(section_anything.PdfError, match="no text"):
        section_anything.section(docling_json([]))
    assert not is_docling_document({"schema_name": "Other"})
    with pytest.raises(section_anything.PdfTooLarge):
        section_anything.section(docling_json([item("text", "x " * 5, 700)], pages=3), max_pages=2)


def test_round_trip_through_our_own_docling_export(paper_pdf):
    pytest.importorskip("docling_core")
    tree = section_anything.section(paper_pdf)
    again = section_anything.section(tree.to_docling_document(paper_pdf))  # the DoclingDocument object
    assert headings(again) == headings(tree)


# -- Hints for a PDF's own lines -----------------------------------------------------------------


@pytest.fixture
def plain_pdf(tmp_path):
    """Headings set like body text, so typography alone finds none; one bold line in the body."""
    return write_pdf(tmp_path / "plain.pdf", [[
        ("Getting started", 10, False), *body(3),
        ("Note well", 10, True), *body(2),
        ("Installing", 10, False), *body(3),
        ("Report title", 10, False),
    ]])


def boxed(lines: list[Line], labels: dict[str, str], dx: float = 0.0, dy: float = 0.0) -> list[dict]:
    """Docling items over our own lines, labelled by text (default `text`), shifted by (dx, dy)."""
    return [{"label": labels.get(ln.text, "text"), "text": ln.text, "page": ln.page,
             "box": (ln.x0 - dx, ln.y0 - dy, ln.x1 - dx, ln.y1 - dy)} for ln in lines]


def test_hints_make_headers_candidates_and_veto_body_lines(plain_pdf):
    labels = {"Getting started": "section_header", "Installing": "section_header", "Report title": "page_footer"}
    plain = section_anything.section(plain_pdf)
    assert [t for _, t in headings(plain)] == ["Note well"]  # bold: the only styled line

    lines = extract(plain_pdf).lines
    tree = section_anything.section(plain_pdf, docling=docling_json(boxed(lines, labels)))
    assert [t for _, t in headings(tree)] == ["Getting started", "Installing"]  # "Note well" is text to Docling

    ext = extract(plain_pdf)
    hints = attach_hints(ext, docling_json(boxed(lines, labels)), veto=False)
    assert {ext.lines[i].text for i in hints.headers} == {"Getting started", "Installing"}
    assert {ext.lines[i].text for i in hints.furniture} == {"Report title"}
    assert not hints.body
    assert {ln.text for ln, _ in candidates(ext)} == {"Getting started", "Note well", "Installing"}


def test_hints_find_a_cropped_page(plain_pdf):
    """Docling measures from the crop box: its boxes are shifted against ours."""
    lines = extract(plain_pdf).lines
    labels = {"Getting started": "section_header", "Installing": "section_header"}
    doc = docling_json(boxed(lines, labels, dx=50, dy=80), page={"width": 500.0, "height": 650.0})
    tree = section_anything.section(plain_pdf, docling=doc)
    assert [t for _, t in headings(tree)] == ["Getting started", "Installing"]


def test_two_docling_headers_on_adjacent_lines_stay_two(tmp_path):
    pdf = write_pdf(tmp_path / "act.pdf", [[
        ("CHAPTER 1", 10, True), ("Definitions", 10, True), *body(3),
        ("Purpose of this Act", 10, True), ("Application", 10, True), *body(3),
    ]])
    lines = extract(pdf).lines
    one = section_anything.section(pdf)
    assert "Purpose of this Act Application" in [t for _, t in headings(one)]  # same style, adjacent: one heading
    labels = dict.fromkeys(["CHAPTER 1", "Definitions", "Purpose of this Act", "Application"], "section_header")
    items = boxed(lines, labels)
    joined = next(k for k, it in enumerate(items) if it["text"] == "CHAPTER 1")  # Docling's own two-line header
    head, title = items[joined], items[joined + 1]
    items[joined:joined + 2] = [{**head, "text": "CHAPTER 1 Definitions",
                                 "box": (head["box"][0], title["box"][1], max(head["box"][2], title["box"][2]), head["box"][3])}]
    tree = section_anything.section(pdf, docling=docling_json(items))
    assert [t for _, t in headings(tree)] == ["CHAPTER 1 Definitions", "Purpose of this Act", "Application"]
