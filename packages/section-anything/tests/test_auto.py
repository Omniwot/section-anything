"""Free's per-heading confidence, and mode "auto" (Free, then Quick check only when Free is unsure),
with a fake model (no network)."""

from __future__ import annotations

import pytest
from conftest import body, write_pdf
from test_modes import _fake

import section_anything
from section_anything.api import resolve_mode
from section_anything.confidence import _in_sequence, document_confidence
from section_anything.config import Settings
from section_anything.errors import ConfigError, CostCapExceeded


def test_free_sections_carry_confidence(paper_pdf, front_matter_pdf):
    tree = section_anything.section(paper_pdf)
    scores = [s["confidence"] for s in tree.sections]
    assert all(isinstance(c, float) and 0 <= c <= 1 for c in scores)
    by_title = {s["title"]: s["confidence"] for s in tree.sections}
    # Numbered in sequence, in a style used on both pages: more evidence than the lone subsection.
    assert by_title["Introduction"] > by_title["Scope"]
    front = section_anything.section(front_matter_pdf)
    assert front.sections[0]["flags"] == ["front_matter"] and front.sections[0]["confidence"] is None
    assert "confidence" in tree.to_dict()["sections"][0]
    assert "auto" not in tree.to_dict()  # only mode "auto" reports a choice


def test_model_modes_have_no_confidence(paper_pdf, monkeypatch):
    _fake(monkeypatch)
    for mode in ("quick", "standard"):
        tree = section_anything.section(paper_pdf, mode, api_key="sk-test")
        assert {s["confidence"] for s in tree.sections} == {None}
        assert "auto" not in tree.to_dict()


def test_long_heading_scores_lower(tmp_path):
    pdf = write_pdf(tmp_path / "long.pdf", [
        [("1 Introduction", 14, True), *body(4),
         ("2 A heading that runs on for far more than ten words in all", 14, True), *body(4)],
        [("3 Methods", 14, True), *body(4)],
    ])
    conf = {s["number"]: s["confidence"] for s in section_anything.section(pdf).sections}
    assert conf["2"] < conf["1"] and conf["2"] < conf["3"]


@pytest.mark.parametrize("prev, cur, ok", [
    (None, (1,), True), (None, (1, 1), True), (None, (7,), False),
    ((1,), (1, 1), True), ((1, 1), (1, 2), True), ((1, 2), (2,), True), ((2, 3, 1), (3,), True),
    ((1,), (3,), False), ((2, 1), (2, 3), False), ((2,), (1,), False),
])
def test_numbering_sequence(prev, cur, ok):
    assert _in_sequence(prev, cur) is ok


def test_document_confidence_needs_three_headings():
    def sec(c, flags=()):
        return {"confidence": c, "flags": list(flags)}

    assert document_confidence([sec(0.9), sec(0.9)]) == 0.0
    assert document_confidence([sec(None, ["front_matter"]), sec(0.1, ["doc_title"]), sec(0.9), sec(0.6), sec(0.6)]) == 0.7


def test_auto_keeps_free_when_sure(paper_pdf, monkeypatch):
    fake = _fake(monkeypatch)
    tree = section_anything.section(paper_pdf, "auto", api_key="sk-test")
    assert tree.mode == "free" and tree.model is None and tree.cost_usd == 0
    assert fake.requests == []
    assert tree.auto["path"] == "free" and tree.auto["threshold"] == 0.72
    assert tree.auto["confidence"] >= 0.72 and "sure" in tree.auto["reason"]
    assert tree.to_dict()["auto"] == tree.auto
    assert tree.sections == section_anything.section(paper_pdf).sections  # exactly Free's result


def test_auto_escalates_when_unsure(paper_pdf, monkeypatch):
    fake = _fake(monkeypatch)
    monkeypatch.setenv("SECTIONANY_AUTO_THRESHOLD", "0.99")
    tree = section_anything.section(paper_pdf, "auto", api_key="sk-test")
    assert tree.mode == "quick" and tree.model == "gpt-6-luna" and len(fake.requests) == 1
    assert tree.auto["path"] == "quick" and tree.auto["threshold"] == 0.99 and "unsure" in tree.auto["reason"]
    assert {s["confidence"] for s in tree.sections} == {None}  # the model chose these sections
    assert tree.usage["calls"] == 1


def test_auto_escalates_with_too_few_headings(front_matter_pdf, monkeypatch):
    _fake(monkeypatch)
    tree = section_anything.section(front_matter_pdf, "auto", api_key="sk-test")
    assert tree.mode == "quick"
    assert tree.auto == {"path": "quick", "reason": "Free found 2 headings (under 3)", "confidence": 0.0,
                         "threshold": 0.72}


def test_auto_over_the_cap_stays_free(front_matter_pdf, monkeypatch):
    fake = _fake(monkeypatch)
    tree = section_anything.section(front_matter_pdf, "auto", api_key="sk-test", max_usd=0.0)
    assert tree.mode == "free" and tree.auto["path"] == "free" and fake.requests == []
    assert tree.downgraded and tree.downgraded[0].startswith("quick: estimated")
    with pytest.raises(CostCapExceeded):
        section_anything.section(front_matter_pdf, "auto", api_key="sk-test", max_usd=0.0, over_budget="fail")


def test_auto_needs_a_key_and_takes_the_quick_model(paper_pdf):
    with pytest.raises(ConfigError, match="auto mode needs an API key"):
        section_anything.section(paper_pdf, "auto")
    assert resolve_mode("auto", Settings()) == ("auto", "gpt-6-luna")
    assert resolve_mode("auto", Settings(), "claude-haiku-5-5") == ("auto", "claude-haiku-5-5")
