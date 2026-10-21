"""The public API on real PDFs, in free mode (no model, no network)."""

from __future__ import annotations

import json
import os

import pytest

import section_anything
from section_anything.api import SECTION_KEYS, SectionTree


def test_free_mode_on_generated_paper(paper_pdf):
    tree = section_anything.section(paper_pdf, mode="free")
    assert isinstance(tree, SectionTree)
    assert [(s["number"], s["title"], s["level"]) for s in tree.sections] == [
        ("", "A Study of Sectioning", 1), ("1", "Introduction", 1), ("1.1", "Scope", 2),
        ("2", "Methods", 1), ("3", "Results", 1),
    ]
    assert "doc_title" in tree.sections[0]["flags"]
    assert [s["page_start"] for s in tree.sections] == [1, 1, 1, 2, 2]
    for s in tree.sections:
        assert tuple(s) == SECTION_KEYS
        assert 0 <= s["start"] < s["end"] <= len(tree.text)
    assert tree.text[tree.sections[3]["start"]:].startswith("2 Methods")
    assert tree.mode == "free" and tree.model is None and tree.pages == 2
    assert tree.cost_usd == 0.0 and tree.usage["calls"] == 0
    assert tree.to_markdown() == (
        "# A Study of Sectioning\n## 1 Introduction\n### 1.1 Scope\n## 2 Methods\n## 3 Results\n"
    )


def test_markdown_with_body(paper_pdf):
    md = section_anything.section(paper_pdf).to_markdown(body=True)
    blocks = md.split("\n\n")
    assert blocks[0] == "# A Study of Sectioning"
    k = blocks.index("## 1 Introduction")
    assert blocks[k + 1].startswith("Sectioning splits a long document")
    assert md.count("1 Introduction") == 1  # the heading line is not repeated in the body


def test_json_export_and_summary(paper_pdf):
    tree = section_anything.section(paper_pdf)
    data = json.loads(tree.to_json())
    assert data["section_anything"] == section_anything.__version__
    assert data["mode"] == "free" and data["cost_usd"] == 0.0 and data["calls"] == 0
    assert data["sections"] == tree.sections
    assert tree.summary()["sections"] == 5 and tree.summary()["flagged"] == 1  # doc_title


def test_free_mode_on_real_paper(readoc_pdf):
    tree = section_anything.section(readoc_pdf, mode="free")
    assert len(tree.sections) >= 5
    assert tree.usage["calls"] == 0 and tree.cost_usd == 0.0
    assert all(1 <= s["page_start"] <= s["page_end"] <= tree.pages for s in tree.sections)
    starts = [s["start"] for s in tree.sections]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)
    md = tree.to_markdown()
    assert md.startswith("#") and len(md.splitlines()) >= 5
    json.loads(tree.to_json())


def test_section_inside_running_event_loop(paper_pdf):
    import asyncio

    async def inside():
        return section_anything.section(paper_pdf)  # runs on a helper thread

    assert len(asyncio.run(inside()).sections) == 5


def test_markdown_levels_and_front_matter():
    def sec(number, title, level, flags=()):
        return {"number": number, "title": title, "level": level, "page_start": 1, "page_end": 1,
                "start": 0, "end": 1, "flags": list(flags)}

    tree = SectionTree(
        sections=[sec("", "Front matter", 1, ["front_matter"]), sec("", "My Paper", 1, ["doc_title"]),
                  sec("1", "Intro", 1), sec("1.1", "Scope", 2), sec("", "Very  deep", 7)],
        mode="free", model=None, pages=1, usage={"calls": 0, "cost_usd": 0.0}, seconds=0.0,
    )
    assert tree.to_markdown() == "# My Paper\n## 1 Intro\n### 1.1 Scope\n###### Very deep\n"


def test_package_import_is_cheap():
    import subprocess
    import sys

    code = "import sys, section_anything; print(int(any(m in sys.modules for m in ('pdfplumber', 'openai'))))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
    assert out.stdout.strip() == "0"


def test_unknown_mode_is_rejected(paper_pdf):
    with pytest.raises(section_anything.ConfigError, match="unknown mode"):
        section_anything.section(paper_pdf, mode="turbo")
    with pytest.raises(section_anything.ConfigError, match="local mode needs a model"):
        section_anything.section(paper_pdf, mode="local")
