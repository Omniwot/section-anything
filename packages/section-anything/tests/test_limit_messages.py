"""Every safety limit's error says it is one and how to raise it, with a value that would fit."""

from __future__ import annotations

import sys

import pytest

import section_anything
import section_anything.isolate as isolate
from section_anything import CostCapExceeded, ExtractionTimeout, PdfTooLarge, Settings, extract_pdf
from section_anything.errors import limit_hint
from section_anything.extract import chars_needed


def test_hint_names_the_flag_the_python_setting_and_the_variable():
    assert limit_hint("SECTIONANY_MAX_PAGES", 900, flag="--max-pages", python="max_pages=900") == (
        "(a safety limit; to allow more, use --max-pages 900, max_pages=900 in Python, or SECTIONANY_MAX_PAGES=900)"
    )
    assert limit_hint("SECTIONANY_MAX_MB", 3) == "(a safety limit; to allow more, use SECTIONANY_MAX_MB=3)"


def test_page_limit_suggests_the_page_count(three_page_pdf):
    with pytest.raises(PdfTooLarge) as err:
        extract_pdf(three_page_pdf, settings=Settings(max_pages=2))
    assert "safety limit" in str(err.value)
    assert "--max-pages 3, max_pages=3 in Python, or SECTIONANY_MAX_PAGES=3" in str(err.value)


def test_size_limit_suggests_the_file_size(three_page_pdf):
    with pytest.raises(PdfTooLarge, match=r"Settings\(max_mb=1\) in Python, or SECTIONANY_MAX_MB=1\)"):
        extract_pdf(three_page_pdf, settings=Settings(max_mb=0.0001))


@pytest.mark.parametrize("isolated", [True, False])
def test_text_limit_suggests_a_cap_for_the_whole_text(three_page_pdf, isolated):
    with pytest.raises(PdfTooLarge, match="SECTIONANY_MAX_CHARS=1000000"):
        extract_pdf(three_page_pdf, settings=Settings(max_chars=50, isolate_extraction=isolated))


def test_text_estimate_scales_with_the_pages_left():
    assert chars_needed(3_000_000, 1000, 5000) == 17_000_000  # 15M with a 10% margin, rounded up
    assert chars_needed(10, 0, 3) == 1_000_000


def test_timeout_suggests_a_longer_limit(paper_pdf, monkeypatch):
    monkeypatch.setattr(isolate, "_worker_argv", lambda: [sys.executable, "-c", "import time; time.sleep(60)"])
    with pytest.raises(ExtractionTimeout, match="--timeout 60, extract_timeout=60 in Python"):
        extract_pdf(paper_pdf, settings=Settings(extract_timeout_seconds=1))
    assert isolate._timeout_needed(120, 100, 5000) == 7500  # the pace so far, with a 25% margin


def test_cost_cap_suggests_the_estimate(paper_pdf):
    with pytest.raises(CostCapExceeded) as err:
        section_anything.section(paper_pdf, "standard", api_key="sk-test", max_usd=0.000001, over_budget="fail")
    assert "per-document cap (a safety limit; to allow more, use --max-usd " in str(err.value)
    assert "SECTIONANY_MAX_USD_PER_DOC=" in str(err.value)


def test_mcp_server_points_to_its_environment():
    pytest.importorskip("mcp")
    from section_anything.mcp_server import _server_hint

    assert "set the SECTIONANY_ variable in its environment" in _server_hint(PdfTooLarge("PDF has 9 pages; the limit is 5 (a safety limit; ...)"))
    assert _server_hint(PdfTooLarge("no pages")) == ""
