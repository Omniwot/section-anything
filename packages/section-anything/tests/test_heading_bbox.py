"""`heading_bbox`: where each section's heading is printed (page and box in PDF points from the
page's bottom-left corner), for section records that cite a position (docling#2147's shape)."""

from __future__ import annotations

import json

from pydantic import TypeAdapter

import section_anything
from section_anything.api import BOX_KEYS, LINK_KEYS, SECTION_KEYS, SectionTree, TreeDict, _public

from conftest import body, write_pdf
from test_docling_input import SCANNED, item


def baseline(size: float, above: list[float]) -> float:
    """Where `write_pdf` sets a line's baseline: 700 down by each earlier line's height."""
    y = 700.0
    for s in above:
        y -= s * 1.6 + (s * 0.6 if s > 11 else 0)
    return y - size * 1.6


def test_boxes_of_known_headings(paper_pdf):
    tree = section_anything.section(paper_pdf)
    boxes = [s["heading_bbox"] for s in tree.sections]
    assert all(set(b) == {"page", "x0", "y0", "x1", "y1"} for b in boxes)
    assert [b["page"] for b in boxes] == [1, 1, 1, 2, 2]
    assert all(b["x0"] == 72.0 and 72.0 < b["x1"] <= 612 and 0 <= b["y0"] < b["y1"] <= 792 for b in boxes)
    title, intro, scope = boxes[:3]
    assert title["y0"] < baseline(20, []) < title["y1"]  # the baseline the PDF was written with
    assert intro["y0"] < baseline(14, [20]) < intro["y1"]
    assert title["y1"] - title["y0"] > intro["y1"] - intro["y0"]  # 20 pt above 14 pt
    assert title["y0"] > intro["y1"] > scope["y1"]  # reading order runs down the page
    assert boxes[3]["y1"] > boxes[4]["y1"]
    for s in tree.sections:
        assert tuple(s) == (*SECTION_KEYS, *LINK_KEYS, *BOX_KEYS)


def test_wrapped_heading_takes_the_union_box(tmp_path):
    pdf = write_pdf(tmp_path / "wrap.pdf", [
        [("A Study of Sectioning", 20, True), ("1 Introduction", 14, True), *body(5),
         ("2 A heading long enough that it wraps", 14, True), ("onto a second line of its own", 14, True), *body(4)],
        [("3 Methods", 14, True), *body(5)],
    ])
    tree = section_anything.section(pdf)
    sec = tree.sections[2]
    assert sec["title"] == "A heading long enough that it wraps onto a second line of its own"
    first, second = tree.extraction.lines[7], tree.extraction.lines[8]
    assert first.text.startswith("2 A heading") and second.text.startswith("onto a")
    box = sec["heading_bbox"]
    assert (box["y1"], box["y0"]) == (first.y1, second.y0)  # top of the first line, bottom of the second
    assert box["x1"] == max(first.x1, second.x1) and box["x0"] == 72.0
    assert box["y1"] - box["y0"] > 2 * (first.y1 - first.y0)  # taller than one line


def test_front_matter_has_no_box(front_matter_pdf):
    tree = section_anything.section(front_matter_pdf)
    assert "front_matter" in tree.sections[0]["flags"] and tree.sections[0]["heading_bbox"] is None
    assert all(s["heading_bbox"] is not None for s in tree.sections[1:])


def test_model_written_title_has_no_box(paper_pdf):
    """A title a model wrote (`title_from_text` False, flag `generated_title`) is printed nowhere."""
    tree = section_anything.section(paper_pdf)
    resolved = [dict(r) for r in tree.resolved]
    resolved[1]["title_from_text"] = False
    again = SectionTree(sections=[_public(r) for r in resolved], mode="standard", model="m", pages=tree.pages,
                        usage=tree.usage, seconds=0.0, extraction=tree.extraction, resolved=resolved)
    assert "generated_title" in again.sections[1]["flags"] and again.sections[1]["heading_bbox"] is None
    assert again.sections[2]["heading_bbox"] == tree.sections[2]["heading_bbox"]


def test_tree_without_extraction_has_no_boxes():
    tree = SectionTree(sections=[{"number": "1", "title": "A", "level": 1, "page_start": 1, "page_end": 1, "start": 0,
                                  "end": 5, "flags": [], "confidence": None}],  # type: ignore[list-item]
                       mode="free", model=None, pages=1, usage={}, seconds=0.0)
    assert tree.sections[0]["heading_bbox"] is None and tree.sections[0]["heading_path"] == ["1 A"]


def test_docling_input_keeps_doclings_boxes():
    """Lines from a Docling document carry its provenance boxes, so the heading's box is Docling's own."""
    tree = section_anything.section(SCANNED)
    overview = next(s for s in tree.sections if s["title"] == "Overview")
    assert overview["heading_bbox"] == {"page": 1, "x0": 72.0, "y0": 668.0, "x1": 400.0, "y1": 680.0}
    assert overview["heading_bbox"] == {"page": 1, **dict(zip(("x0", "y0", "x1", "y1"), item("", "", 680)["box"], strict=True))}


def test_exports_use_the_same_box(paper_pdf):
    tree = section_anything.section(paper_pdf)
    titles = [e for e in tree.to_unstructured_elements() if e["type"] == "Title"]
    for sec, el in zip(tree.sections, titles, strict=True):
        box, c = sec["heading_bbox"], el["metadata"]["coordinates"]
        (left, top), (_, bottom), (right, _), _ = c["points"]
        assert (left, right) == (box["x0"], box["x1"])
        assert (round(792 - top, 2), round(792 - bottom, 2)) == (box["y1"], box["y0"])
        assert el["metadata"]["page_number"] == box["page"]


def test_json_carries_the_box(paper_pdf):
    tree = section_anything.section(paper_pdf)
    schema = SectionTree.json_schema()
    assert "heading_bbox" in schema["$defs"]["Section"]["required"]
    assert set(schema["$defs"]["HeadingBox"]["required"]) == {"page", "x0", "y0", "x1", "y1"}
    out = json.loads(tree.to_json(text=True))
    TypeAdapter(TreeDict).validate_python(out)
    assert out["sections"][1]["heading_bbox"] == tree.sections[1]["heading_bbox"]
    assert out["sections"][1]["heading_bbox"]["page"] == out["sections"][1]["page_start"]
