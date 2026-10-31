"""A PDF passed as bytes or a stream: same sections as its path, same caps, nothing left on disk."""

from __future__ import annotations

import asyncio
import io
import stat
import sys
import tempfile
from pathlib import Path

import pytest

import section_anything
import section_anything.isolate as isolate
from section_anything import ExtractionTimeout, PdfError, PdfTooLarge, Settings, extract_pdf
from section_anything.extract import extract


def _as(kind: str, data: bytes, path: Path):
    if kind == "bytes":
        return data
    if kind == "bytearray":
        return bytearray(data)
    if kind == "memoryview":
        return memoryview(data)
    if kind == "BytesIO":
        return io.BytesIO(data)
    return open(path, "rb")  # closed by the test


@pytest.fixture
def private_tmp(tmp_path, monkeypatch) -> tuple[Path, list[Path]]:
    """Temporary files go to an empty folder of the test's own; returns it and every file
    `_private_copy` created."""
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    made: list[Path] = []
    mkstemp = tempfile.mkstemp

    def recording_mkstemp(*a, **k):
        fd, name = mkstemp(*a, **k)
        made.append(Path(name))
        return fd, name

    monkeypatch.setattr(tempfile, "mkstemp", recording_mkstemp)
    return root, made


@pytest.fixture
def no_temp_files(monkeypatch):
    """Fails the test if anything creates a temporary file or directory, or opens the PDF."""
    def refuse(*_a, **_k):
        raise AssertionError("a temporary file was created")

    monkeypatch.setattr(tempfile, "mkstemp", refuse)
    monkeypatch.setattr(tempfile, "TemporaryDirectory", refuse)
    monkeypatch.setattr(isolate, "count_pages", lambda _p: pytest.fail("the PDF was opened"))


@pytest.mark.parametrize("kind", ["bytes", "bytearray", "memoryview", "BytesIO", "open file"])
def test_same_sections_as_the_path(paper_pdf, kind):
    want = section_anything.section(paper_pdf)
    pdf = _as(kind, paper_pdf.read_bytes(), paper_pdf)
    try:
        tree = section_anything.section(pdf)
    finally:
        if kind == "open file":
            pdf.close()
    assert tree.sections == want.sections and tree.text == want.text and tree.pages == 2


@pytest.mark.parametrize("kind", ["BytesIO", "open file"])
def test_the_callers_file_stays_open(paper_pdf, kind):
    f = _as(kind, paper_pdf.read_bytes(), paper_pdf)
    try:
        section_anything.section(f)
        assert not f.closed
        assert f.read() == b""  # read to the end, once
    finally:
        f.close()


def test_async_and_in_process(paper_pdf):
    data = paper_pdf.read_bytes()
    tree = asyncio.run(section_anything.asection(data))
    assert tree.text == section_anything.section(paper_pdf).text
    ext = extract_pdf(data, settings=Settings(isolate_extraction=False))
    assert ext.text == extract(paper_pdf).text


def test_a_header_after_a_bom_or_whitespace_is_accepted(paper_pdf):
    ext = extract_pdf(b"\xef\xbb\xbf\r\n " + paper_pdf.read_bytes())
    assert ext.text == extract(paper_pdf).text


@pytest.mark.parametrize("kind", ["bytes", "BytesIO"])
def test_size_cap_is_checked_before_any_temp_file(paper_pdf, no_temp_files, kind):
    pdf = _as(kind, paper_pdf.read_bytes(), paper_pdf)
    with pytest.raises(PdfTooLarge, match=r"^PDF is 0\.0 MB; the limit is 0\.0001 MB .*Settings\(max_mb=1\)"):
        extract_pdf(pdf, settings=Settings(max_mb=0.0001))


def test_a_seekable_stream_over_the_cap_is_measured_not_read():
    f = io.BytesIO(b"x" * (3 * isolate.MB + 5))
    assert isolate._read_stream(f, isolate.MB) == (b"", 3 * isolate.MB + 5, True)
    assert f.tell() == 0  # measured by seeking, position restored
    assert isolate._read_stream(io.BytesIO(b"%PDF-1.4"), isolate.MB) == (b"%PDF-1.4", 8, True)


class _Endless:
    """A stream that never ends and cannot seek, like a hostile upload."""

    reads = 0

    def read(self, size: int = -1) -> bytes:
        self.reads += 1
        return b"%PDF-1.4" + b"x" * (size - 8)


def test_an_endless_stream_is_refused_once_it_passes_the_cap(no_temp_files):
    f = _Endless()
    with pytest.raises(PdfTooLarge, match=r"^PDF is more than 2\.0 MB; the limit is 1 MB .*SECTIONANY_MAX_MB=4\)"):
        extract_pdf(f, settings=Settings(max_mb=1))
    assert f.reads == 2


@pytest.mark.parametrize("data", [b"", b"this is not a pdf", b" " * 1100 + b"%PDF-1.4"])
def test_not_a_pdf_is_refused_before_any_temp_file(no_temp_files, data):
    with pytest.raises(PdfError, match="not a PDF: no %PDF- header in the first 1024 bytes"):
        extract_pdf(data)


def test_temp_file_is_private_and_removed_after_success(paper_pdf, private_tmp, monkeypatch):
    root, made = private_tmp
    seen: list[tuple[int, int]] = []
    inner = isolate._extract

    def checking(src, s, on_page):
        seen.append((stat.S_IMODE(src.stat().st_mode), stat.S_IMODE(src.parent.stat().st_mode)))
        return inner(src, s, on_page)

    monkeypatch.setattr(isolate, "_extract", checking)
    extract_pdf(paper_pdf.read_bytes())
    assert len(made) == 1 and not made[0].exists()
    if sys.platform != "win32":
        assert seen == [(0o600, 0o700)]
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("case", ["page cap", "character cap", "timeout"])
def test_temp_file_is_removed_after_an_error(three_page_pdf, private_tmp, monkeypatch, case):
    root, made = private_tmp
    if case == "page cap":
        settings, error, match = Settings(max_pages=2), PdfTooLarge, "PDF has 3 pages"
    elif case == "character cap":
        settings, error, match = Settings(max_chars=50), PdfTooLarge, "more than 50 characters"
    else:
        monkeypatch.setattr(isolate, "_worker_argv", lambda: [sys.executable, "-c", "import time; time.sleep(60)"])
        settings, error, match = Settings(extract_timeout_seconds=1), ExtractionTimeout, "longer than 1 s"
    with pytest.raises(error, match=match) as err:
        extract_pdf(three_page_pdf.read_bytes(), settings=settings)
    assert len(made) == 1 and not made[0].exists()
    assert list(root.iterdir()) == []
    assert made[0].name not in str(err.value) and "section-anything-" not in str(err.value)


def test_a_text_mode_file_or_another_type_is_a_type_error(paper_pdf):
    with open(paper_pdf, encoding="latin-1") as f, pytest.raises(TypeError, match="open it with 'rb'"):
        extract_pdf(f)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="not int"):
        extract_pdf(42)  # type: ignore[arg-type]


def test_the_callers_bytearray_is_not_held(three_page_pdf):
    data = bytearray(three_page_pdf.read_bytes())
    with pytest.raises(PdfTooLarge) as err:  # the traceback keeps the frames' locals alive
        extract_pdf(data, settings=Settings(max_pages=2))
    data.extend(b"\n")  # BufferError if a view of it were among them
    assert err.value
