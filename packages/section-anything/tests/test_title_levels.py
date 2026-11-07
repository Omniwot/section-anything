"""Quick and Standard number levels as Free does around the document's own title: a model that nests every
heading under the title (title 1, an Act's Parts 2) has them lifted so the top division is level 1 beside the
title (research finding F065). Relative depths, sections and offsets do not change."""

from __future__ import annotations

import section_anything
from section_anything.pipeline import title_beside_top_level
from test_modes import _fake


def sec(level: int, title: str, start: int, flags: tuple[str, ...] = ()) -> dict:
    return {"level": level, "title": title, "number": "", "start": start, "span_end": 0, "flags": list(flags)}


def levels(secs: list[dict]) -> list[int]:
    return [s["level"] for s in secs]


def test_headings_nested_under_the_title_move_up_beside_it():
    secs = [sec(1, "Front matter", 0, ("front_matter",)), sec(1, "Modern Slavery Act 2015", 10, ("doc_title",)),
            sec(2, "PART 1 OFFENCES", 20), sec(3, "1 Slavery", 30), sec(3, "2 Human trafficking", 40),
            sec(2, "PART 2 PREVENTION ORDERS", 50), sec(3, "14 Orders", 60), sec(4, "Schedule note", 70)]
    for s in secs:
        s["span_end"] = 100
    assert title_beside_top_level(secs) == 1
    assert levels(secs) == [1, 1, 1, 2, 2, 1, 2, 3]
    # Spans follow the new levels: the title's no longer covers the Parts.
    assert [s["span_end"] for s in secs] == [10, 20, 50, 40, 50, 100, 100, 100]


def test_levels_stay_when_a_heading_is_already_beside_the_title():
    secs = [sec(1, "A Study", 0, ("doc_title",)), sec(2, "Abstract", 10), sec(1, "1 Introduction", 20),
            sec(2, "1.1 Scope", 30)]
    assert title_beside_top_level(secs) == 0
    assert levels(secs) == [1, 2, 1, 2]


def test_levels_stay_without_a_document_title():
    secs = [sec(1, "Overview", 0), sec(2, "Install", 10), sec(2, "Use", 20)]
    assert title_beside_top_level(secs) == 0 and levels(secs) == [1, 2, 2]
    only = [sec(1, "A Study", 0, ("doc_title",))]
    assert title_beside_top_level(only) == 0 and levels(only) == [1]


def test_a_deeper_gap_is_closed_in_one_step():
    secs = [sec(1, "Title", 0, ("doc_title",)), sec(3, "Chapter 1", 10), sec(4, "1.1", 20), sec(3, "Chapter 2", 30)]
    assert title_beside_top_level(secs) == 2
    assert levels(secs) == [1, 1, 2, 1]


def _nesting(monkeypatch):
    """The fake careful model, answering as a model that nests every heading under the title."""
    fake = _fake(monkeypatch)
    parse = fake._parse

    async def nested(**kwargs):
        res = await parse(**kwargs)
        parsed = res.choices[0].message.parsed
        for item in getattr(parsed, "sections", None) or getattr(parsed, "items", None) or []:
            if item.number:
                item.level += 1
        return res

    fake.chat.completions.parse = nested
    return fake


def test_standard_and_quick_put_the_top_division_beside_the_title(paper_pdf, monkeypatch):
    _nesting(monkeypatch)
    for mode in ("standard", "quick"):
        tree = section_anything.section(paper_pdf, mode, api_key="sk-test")
        assert [s["title"] for s in tree.sections][:3] == ["A Study of Sectioning", "Introduction", "Scope"]
        assert "doc_title" in tree.sections[0]["flags"]
        assert levels(tree.sections) == [1, 1, 2, 1, 1], mode
        assert [s["heading_path"] for s in tree.sections][2] == ["1 Introduction", "1.1 Scope"]
        assert tree.to_markdown().splitlines()[:3] == ["# A Study of Sectioning", "## 1 Introduction", "### 1.1 Scope"]


def test_free_levels_are_its_own(paper_pdf):
    tree = section_anything.section(paper_pdf, "free")
    assert levels(tree.sections) == [1, 1, 2, 1, 1]
