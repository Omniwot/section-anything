"""Output for agents and tools: parent links and heading paths in the core result, section text in
the JSON export, and a JSON Schema for it."""

from __future__ import annotations

import json

from pydantic import TypeAdapter

import section_anything
from section_anything.api import SectionTree, TreeDict
from section_anything.cli import main


def _sec(number, title, level, flags=(), start=0, end=1):
    return {"number": number, "title": title, "level": level, "page_start": 1, "page_end": 1,
            "start": start, "end": end, "flags": list(flags)}


def test_parents_and_heading_paths(paper_pdf):
    tree = section_anything.section(paper_pdf)
    got = [(s["title"], s["parent"], s["heading_path"]) for s in tree.sections]
    assert got == [
        ("A Study of Sectioning", None, ["A Study of Sectioning"]),  # the document title stands alone
        ("Introduction", None, ["1 Introduction"]),
        ("Scope", 1, ["1 Introduction", "1.1 Scope"]),
        ("Methods", None, ["2 Methods"]),
        ("Results", None, ["3 Results"]),
    ]


def test_links_skip_levels_and_leave_front_matter_out():
    given = [_sec("", "Front matter", 1, ["front_matter"]), _sec("", "Title", 1, ["doc_title"]),
             _sec("I", "Part", 1), _sec("", "Deep", 3), _sec("1", "Chapter", 2), _sec("II", "Next", 1)]
    tree = SectionTree(sections=given, mode="free", model=None, pages=1, usage={}, seconds=0.0)
    assert [s["parent"] for s in tree.sections] == [None, None, None, 2, 2, None]
    assert [s["heading_path"] for s in tree.sections] == [
        [], ["Title"], ["I Part"], ["I Part", "Deep"], ["I Part", "1 Chapter"], ["II Next"]]
    assert "parent" not in given[2]  # the caller's dicts are not changed


def test_json_text_is_the_exact_slice(paper_pdf):
    tree = section_anything.section(paper_pdf)
    assert all("text" not in s for s in tree.to_dict()["sections"])
    data = json.loads(tree.to_json(text=True))
    for s in data["sections"]:
        assert s["text"] == tree.text[s["start"]:s["end"]]
    assert data["sections"][3]["text"].startswith("2 Methods\nSectioning splits")
    assert all("text" not in s for s in tree.sections)  # the tree itself is unchanged


def test_json_schema_matches_the_output(paper_pdf):
    schema = SectionTree.json_schema()
    section = schema["$defs"]["Section"]
    assert {"parent", "heading_path", "start", "end"} <= set(section["required"])
    assert "text" in section["properties"] and "text" not in section["required"]
    tree = section_anything.section(paper_pdf)
    adapter = TypeAdapter(TreeDict)
    adapter.validate_python(tree.to_dict())
    adapter.validate_python(json.loads(tree.to_json(text=True)))


def test_cli_json_with_text(paper_pdf, capsys):
    assert main([str(paper_pdf), "--format", "json", "--body", "-q"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["sections"][2]["heading_path"] == ["1 Introduction", "1.1 Scope"]
    assert data["sections"][2]["text"].startswith("1.1 Scope")
