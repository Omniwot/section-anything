"""outline_pdf: the compact outline an agent reads first, and its indexes in read_sections."""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("mcp")

from mcp import Client
from section_anything.mcp_server import build_server, compact_outline


def _call(server, tool: str, args: dict):
    async def go():
        async with Client(server) as client:
            return await client.call_tool(tool, args)

    return asyncio.run(go())


def _section(i: int, number: str, title: str, level: int, p1: int, p2: int, flags=()) -> dict:
    return {"number": number, "title": title, "level": level, "page_start": p1, "page_end": p2,
            "start": i * 10, "end": i * 10 + 9, "flags": list(flags), "confidence": None,
            "parent": None, "heading_path": []}


def test_compact_lines_nest_by_hashes_and_give_page_ranges():
    sections = [
        _section(0, "", "A Study", 1, 1, 1, flags=["doc_title"]),
        _section(1, "1", "Introduction", 1, 1, 2),
        _section(2, "1.1", "Scope", 2, 2, 2),
        _section(3, "1.1.1", "Limits", 3, 2, 3),
        _section(4, "2", "Methods", 1, 3, 7),
    ]
    out = compact_outline(sections, "free", 7)
    head, *lines = out.rstrip("\n").split("\n")
    assert head.startswith("mode: free; pages: 7; sections: 5 (indexes 0-4)")
    assert "read_sections" in head and "front matter" not in head
    assert lines == [
        "0: # A Study (p. 1)",
        "1: ## 1 Introduction (p. 1-2)",
        "2: ### 1.1 Scope (p. 2)",
        "3: #### 1.1.1 Limits (p. 2-3)",
        "4: ## 2 Methods (p. 3-7)",
    ]


def test_front_matter_is_left_out_but_indexes_stay_positions():
    sections = [
        _section(0, "", "", 1, 1, 1, flags=["front_matter"]),
        _section(1, "1", "Introduction", 1, 1, 1),
        _section(2, "2", "Methods", 1, 1, 1),
    ]
    out = compact_outline(sections, "free", 1)
    head, *lines = out.rstrip("\n").split("\n")
    assert head.endswith("; front matter left out") and "sections: 3 (indexes 0-2)" in head
    assert lines == ["1: ## 1 Introduction (p. 1)", "2: ## 2 Methods (p. 1)"]
    assert compact_outline([], "free", 0) == "mode: free; pages: 0; sections: 0; read_sections(indexes=[...]) returns a section's text\n"


def test_outline_then_one_section_by_index(paper_pdf):
    server = build_server()
    res = _call(server, "outline_pdf", {"path": str(paper_pdf)})
    assert not res.is_error and res.structured_content is None  # plain text, no JSON wrapper
    text = res.content[0].text
    head, *lines = text.rstrip("\n").split("\n")
    assert head.startswith("mode: free; pages: 2; sections: 6 (indexes 0-5)")
    assert lines == [
        "0: # A Study of Sectioning (p. 1)",
        "1: ## 1 Introduction (p. 1)",
        "2: ### 1.1 Scope (p. 1)",
        "3: ## 2 Methods (p. 2)",
        "4: ### 2.1 Data (p. 2)",
        "5: ## 3 Results (p. 2)",
    ]
    # The index on a line is what read_sections takes for that section.
    index = int(next(ln for ln in lines if "2.1 Data" in ln).split(":")[0])
    res = _call(server, "read_sections", {"path": str(paper_pdf), "indexes": [index], "max_chars": 40})
    got = res.structured_content["sections"]
    assert got[0]["index"] == index and got[0]["heading_path"] == ["2 Methods", "2.1 Data"]
    assert got[0]["page_start"] == 2 and got[0]["text"].startswith("Sectioning splits")
    # Same sections, same order, as the JSON tree.
    tree = _call(server, "section_pdf", {"path": str(paper_pdf)}).structured_content
    assert [s["heading_path"][-1] for s in tree["sections"]][index] == "2.1 Data"
    assert len(text) < len(json.dumps(tree)) / 4


def test_front_matter_pdf_outline_skips_the_untitled_start(front_matter_pdf):
    text = _call(build_server(), "outline_pdf", {"path": str(front_matter_pdf)}).content[0].text
    head, *lines = text.rstrip("\n").split("\n")
    assert head.endswith("front matter left out")
    assert lines == ["1: ## 1 Introduction (p. 1)", "2: ## 2 Methods (p. 1)"]
