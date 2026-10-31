"""Untrusted PDFs: caps before parsing, a worker process with a time limit, no secrets in it."""

from __future__ import annotations

import sys
import time

import pytest

import section_anything.isolate as isolate
from section_anything import ExtractionFailed, ExtractionTimeout, PdfError, PdfTooLarge, Settings, extract_pdf
from section_anything.extract import extract


def test_worker_matches_in_process_extraction(paper_pdf):
    pages: list[tuple[int, int]] = []
    ext = extract_pdf(paper_pdf, on_page=lambda n, total: pages.append((n, total)))
    local = extract(paper_pdf)
    assert ext.text == local.text and len(ext.lines) == len(local.lines)
    assert [ln.size for ln in ext.lines] == [ln.size for ln in local.lines]
    assert pages == [(1, 2), (2, 2)]


def test_page_cap_is_checked_before_any_parsing(three_page_pdf, monkeypatch):
    def no_worker(*_a, **_k):
        raise AssertionError("the worker was started")

    monkeypatch.setattr(isolate.subprocess, "Popen", no_worker)
    with pytest.raises(PdfTooLarge, match="3 pages; the limit is 2"):
        extract_pdf(three_page_pdf, settings=Settings(max_pages=2))


def test_a_folder_is_refused(tmp_path):
    with pytest.raises(PdfError, match="not a file"):
        extract_pdf(tmp_path)


def test_size_cap_is_checked_before_opening(three_page_pdf, monkeypatch):
    monkeypatch.setattr(isolate, "count_pages", lambda _p: pytest.fail("the PDF was opened"))
    with pytest.raises(PdfTooLarge, match="SECTIONANY_MAX_MB"):
        extract_pdf(three_page_pdf, settings=Settings(max_mb=0.0001))


def test_character_cap_stops_the_worker(three_page_pdf):
    with pytest.raises(PdfTooLarge, match="more than 50 characters"):
        extract_pdf(three_page_pdf, settings=Settings(max_chars=50))


def test_character_cap_in_process(three_page_pdf):
    with pytest.raises(PdfTooLarge, match="more than 50 characters"):
        extract_pdf(three_page_pdf, settings=Settings(max_chars=50, isolate_extraction=False))


def test_slow_worker_is_killed_at_the_timeout(paper_pdf, monkeypatch):
    monkeypatch.setattr(isolate, "_worker_argv", lambda: [sys.executable, "-c", "import time; time.sleep(60)"])
    t0 = time.monotonic()
    with pytest.raises(ExtractionTimeout, match="longer than 1 s"):
        extract_pdf(paper_pdf, settings=Settings(extract_timeout_seconds=1))
    assert time.monotonic() - t0 < 15


def test_crashed_worker_is_reported(paper_pdf, monkeypatch):
    monkeypatch.setattr(isolate, "_worker_argv", lambda: [sys.executable, "-c", "raise SystemExit(9)"])
    with pytest.raises(ExtractionFailed, match="exit code 9"):
        extract_pdf(paper_pdf)


def test_worker_gets_no_api_keys(paper_pdf, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("SECTIONANY_API_KEY", "sk-should-not-leak")
    script = ("import os, json; print(json.dumps({'error': 'internal', "
              "'message': ' '.join(sorted(k for k in os.environ if 'KEY' in k.upper())) or 'none'}))")
    monkeypatch.setattr(isolate, "_worker_argv", lambda: [sys.executable, "-c", script])
    with pytest.raises(ExtractionFailed, match=r"\(none\)"):
        extract_pdf(paper_pdf)


def test_not_a_pdf(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")
    with pytest.raises(PdfError, match="could not be opened"):
        extract_pdf(bad)
