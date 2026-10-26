"""Test fixtures: a small PDF written by hand at test time (standard Type 1 fonts, no
dependencies, nothing downloaded), and a guard that fails any test that would reach a model."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

BODY = (
    "Sectioning splits a long document into parts that a reader or a retrieval system can use.",
    "Each part starts at a heading and runs until the next heading of the same or a higher level.",
    "Headings are found from the outline, the table of contents, typography and numbering.",
    "This paragraph is ordinary body text set in a regular face at the body size of the page.",
)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path: Path, pages: list[list[tuple[str, float, bool]]]) -> Path:
    """Write a PDF whose pages hold the given (text, size, bold) lines, top to bottom."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # filled below
    pages_obj = add(b"")
    regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    kids = []
    for lines in pages:
        y = 700.0
        ops = []
        for text, size, is_bold in lines:
            y -= size * 1.6
            font = "F2" if is_bold else "F1"
            ops.append(f"BT /{font} {size:g} Tf 72 {y:.1f} Td ({_escape(text)}) Tj ET")
            y -= size * 0.6 if size > 11 else 0
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >>"
            b" /Contents %d 0 R >>" % (pages_obj, regular, bold, content)
        ))
    objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_obj
    objects[pages_obj - 1] = (b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids)
                              + b"] /Count %d >>" % len(kids))

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    path.write_bytes(bytes(out))
    return path


def body(n: int = 4) -> list[tuple[str, float, bool]]:
    return [(BODY[k % len(BODY)], 10, False) for k in range(n)]


@pytest.fixture
def paper_pdf(tmp_path: Path) -> Path:
    """Two pages: a title, numbered sections, a subsection, and a section whose only content is
    its subsection (no text of its own)."""
    return write_pdf(tmp_path / "paper.pdf", [
        [("A Study of Sectioning", 20, True), ("1 Introduction", 14, True), *body(5),
         ("1.1 Scope", 12, True), *body(4)],
        [("2 Methods", 14, True), ("2.1 Data", 12, True), *body(5), ("3 Results", 14, True), *body(4)],
    ])


@pytest.fixture
def real_pdf() -> Path:
    """A real paper, when SECTIONANY_TEST_PDF points to one (for example a READoc arXiv PDF)."""
    path = os.environ.get("SECTIONANY_TEST_PDF")
    if not path or not Path(path).is_file():
        pytest.skip("set SECTIONANY_TEST_PDF to a PDF for the end-to-end test")
    return Path(path)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test may create a model client; tests start from the library defaults."""
    import openai

    class Refuse:
        def __init__(self, *_a, **_k):
            raise AssertionError("a test tried to create a model client")

    monkeypatch.setattr(openai, "AsyncOpenAI", Refuse)
    for key in list(os.environ):
        if key.upper().startswith("SECTIONANY_") and key.upper() != "SECTIONANY_TEST_PDF":
            monkeypatch.delenv(key)
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
