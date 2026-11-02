"""The 0.1.7 features together: mode "auto" with Docling's output (as hints or as the input), and
the Standard coverage check, which an auto run never reaches. Fake model, no network."""

from __future__ import annotations

import asyncio
import json

from test_docling_input import SCANNED, boxed, docling_json, headings
from test_modes import _fake

import section_anything
from section_anything import Settings, pipeline
from section_anything.cli import main
from section_anything.docling_input import attach_hints, hints_of
from section_anything.extract import OutlineItem, extract

LABELS = {"Getting started": "section_header", "Installing": "section_header"}


def test_auto_runs_free_with_the_hints_first(plain_pdf, monkeypatch):
    """The hints are attached before Free runs, so auto judges Free-with-hints: two headings (the
    Docling headers) instead of the one bold line. Quick check then reviews the hint candidates too;
    the body-text veto is Free's only, so the bold line is also offered and the model decides."""
    fake = _fake(monkeypatch)
    doc = docling_json(boxed(extract(plain_pdf).lines, LABELS))
    plain = section_anything.section(plain_pdf, "auto", api_key="sk-test")
    assert plain.auto["reason"] == "Free found 1 heading (under 3)"
    fake.requests.clear()

    tree = section_anything.section(plain_pdf, "auto", api_key="sk-test", docling=doc)
    assert tree.auto["path"] == "quick" and tree.auto["reason"] == "Free found 2 headings (under 3)"
    prompt = fake.requests[0]["messages"][1]["content"]
    assert "Getting started" in prompt and "Installing" in prompt
    assert [t for _, t in headings(tree)] == ["Getting started", "Note well", "Installing"]  # the fake accepts all


def test_auto_with_hints_keeps_free_when_sure(plain_pdf, monkeypatch):
    """When it stays Free, an auto run returns exactly Free-with-hints, confidence included."""
    fake = _fake(monkeypatch)
    monkeypatch.setenv("SECTIONANY_AUTO_THRESHOLD", "0.0")
    monkeypatch.setattr("section_anything.confidence.MIN_HEADINGS", 2)
    doc = docling_json(boxed(extract(plain_pdf).lines, LABELS))
    tree = section_anything.section(plain_pdf, "auto", api_key="sk-test", docling=doc)
    assert tree.mode == "free" and tree.auto["path"] == "free" and fake.requests == []
    assert tree.sections == section_anything.section(plain_pdf, docling=doc).sections
    assert all(isinstance(s["confidence"], float) for s in tree.sections if "front_matter" not in s["flags"])


def test_auto_never_runs_the_coverage_check(paper_pdf, monkeypatch):
    """The coverage check is Standard's (llm_text); auto escalates to Quick check (llm_review), one
    call, with no re-read even though the check is on."""
    fake = _fake(monkeypatch)
    monkeypatch.setenv("SECTIONANY_AUTO_THRESHOLD", "0.99")
    tree = section_anything.section(paper_pdf, "auto", api_key="sk-test")
    assert tree.mode == "quick" and len(fake.requests) == 1
    assert "coverage_retries" not in tree.usage
    assert fake.requests[0]["response_format"].__name__ == "ReviewResult"


def test_auto_on_a_docling_document(monkeypatch):
    """`section(doc, "auto")`: Free runs on Docling's lines and escalates to Quick check on those same
    lines when unsure. Docling's levels are the document's outline, but they are Docling's own
    heading list, so they are no evidence for those headings: without that rule every heading of
    this document scored 0.92 and auto kept Docling's headings unchecked."""
    fake = _fake(monkeypatch)
    free = section_anything.section(SCANNED)
    assert free.extraction.outline  # Docling's levels, used for the heading levels
    assert {s["confidence"] for s in free.sections if "doc_title" not in s["flags"]} == {0.522}

    tree = section_anything.section(SCANNED, "auto", api_key="sk-test")
    assert tree.auto["path"] == "quick" and tree.auto["confidence"] == 0.522
    assert tree.mode == "quick" and len(fake.requests) == 1
    assert "Highlights" in fake.requests[0]["messages"][1]["content"]
    assert tree.pages == 1 and tree.extraction.lines == free.extraction.lines

    fake.requests.clear()
    monkeypatch.setenv("SECTIONANY_AUTO_THRESHOLD", "0.5")
    sure = section_anything.section(SCANNED, "auto", api_key="sk-test")
    assert sure.mode == "free" and sure.sections == free.sections and fake.requests == []


def test_pdf_bookmarks_still_count_with_hints(paper_pdf):
    """Docling hints on a PDF leave the PDF's own bookmarks as evidence; only the outline of a
    Docling document (lines from Docling) is discounted."""
    from section_anything.confidence import evidence

    labels = dict.fromkeys(["1 Introduction", "2 Methods", "3 Results", "1.1 Scope"], "section_header")

    def free(from_docling: bool) -> list[dict]:
        ext = extract(paper_pdf)
        ext.outline = [OutlineItem(1, "1 Introduction", 1), OutlineItem(1, "2 Methods", 2), OutlineItem(1, "3 Results", 2)]
        attach_hints(ext, docling_json(boxed(ext.lines, labels)))
        hints_of(ext).lines_from_docling = from_docling
        _raw, resolved, _m = asyncio.run(pipeline.run(ext, "rules", "", 0.0, settings=Settings()))
        return [ev and ev["bookmark"] for ev in evidence(resolved, ext)]

    assert free(False) == [1.0, 0.0, 1.0, 1.0]  # 1, 1.1, 2, 3: the bookmarked ones count
    assert free(True) == [0.0] * 4


def test_cli_docling_with_mode_auto(plain_pdf, tmp_path, monkeypatch, capsys):
    _fake(monkeypatch)
    monkeypatch.setenv("SECTIONANY_API_KEY", "sk-test")
    hints = tmp_path / "plain.json"
    hints.write_text(json.dumps(docling_json(boxed(extract(plain_pdf).lines, LABELS))), encoding="utf-8")
    assert main([str(plain_pdf), "--docling", str(hints), "--mode", "auto", "--format", "json", "-q"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["auto"]["reason"] == "Free found 2 headings (under 3)" and out["mode"] == "quick"

    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps(SCANNED), encoding="utf-8")
    assert main([str(scan), "--mode", "auto", "--format", "json", "-q"]) == 0
    assert "auto" in json.loads(capsys.readouterr().out)
