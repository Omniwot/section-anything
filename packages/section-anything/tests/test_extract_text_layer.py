"""Text that pdfminer's layout analysis used to drop (research finding F045): page text drawn inside a
form XObject that covers the page (printed UK Acts 2011-2016), and CID fonts whose encoding is a CMap
embedded in the PDF (Official Journal of the EU). Both PDFs are written by hand here."""

from __future__ import annotations

from pathlib import Path

from section_anything.extract import extract


def _write(path: Path, objects: list[bytes], root: int) -> Path:
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, root, xref)
    path.write_bytes(bytes(out))
    return path


def _stream(data: bytes, extra: bytes = b"") -> bytes:
    return b"<< /Length %d %s>>\nstream\n" % (len(data), extra) + data + b"\nendstream"


def _form_pdf(path: Path) -> Path:
    """One page whose only content draws two forms: one as large as the page holding the page's
    text, and a small one (a logo) holding a label."""
    page_text = b"BT /F1 16 Tf 72 700 Td (1 Overview) Tj ET\nBT /F1 10 Tf 72 670 Td (The body of the section.) Tj ET"
    logo_text = b"BT /F1 8 Tf 520 760 Td (LOGO) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /P 5 0 R /L 6 0 R >> >>"
        b" /Contents 7 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        _stream(page_text, b"/Type /XObject /Subtype /Form /BBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> "),
        _stream(logo_text, b"/Type /XObject /Subtype /Form /BBox [500 740 600 780] /Resources << /Font << /F1 4 0 R >> >> "),
        _stream(b"q /P Do Q q /L Do Q"),
    ]
    return _write(path, objects, 1)


def _embedded_cmap_pdf(path: Path) -> Path:
    """One page set in a Type0 font whose encoding is a one-byte CMap stream in the PDF."""
    cmap = (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
            b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Test-Regu) /Supplement 0 >> def\n"
            b"/CMapName /Test-Regu def /CMapType 0 def\n"
            b"1 begincodespacerange <00> <FF> endcodespacerange\n"
            b"1 begincidrange <00> <FF> 0 endcidrange\n"
            b"endcmap CMapName currentdict /CMap defineresource pop end end")
    to_unicode = (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
                  b"/CMapName /Test-UCS def /CMapType 2 def\n"
                  b"1 begincodespacerange <00> <FF> endcodespacerange\n"
                  b"1 beginbfrange <20> <7E> <0020> endbfrange\n"
                  b"endcmap CMapName currentdict /CMap defineresource pop end end")
    content = b"BT /T1 16 Tf 72 700 Td (Artikel 1 Gegenstand) Tj ET\nBT /T1 10 Tf 72 670 Td (Diese Verordnung gilt.) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /T1 4 0 R >> >> /Contents 8 0 R >>",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /Test-Regu /Encoding 5 0 R /DescendantFonts [6 0 R]"
        b" /ToUnicode 7 0 R >>",
        _stream(cmap, b"/Type /CMap /CMapName /Test-Regu /CIDSystemInfo << /Registry (Adobe) /Ordering (Test-Regu)"
                      b" /Supplement 0 >> "),
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Test-Regu /CIDSystemInfo << /Registry (Adobe)"
        b" /Ordering (Test-Regu) /Supplement 0 >> /DW 500 >>",
        _stream(to_unicode),
        _stream(content),
    ]
    return _write(path, objects, 1)


def test_text_in_a_page_sized_form_is_read(tmp_path):
    ext = extract(_form_pdf(tmp_path / "form.pdf"))
    assert [ln.text for ln in ext.lines] == ["1 Overview", "The body of the section."]
    assert ext.lines[0].size == 16
    assert ext.pages[0].has_text


def test_text_in_a_small_form_stays_out(tmp_path):
    assert "LOGO" not in extract(_form_pdf(tmp_path / "form.pdf")).text


def test_cid_font_with_an_embedded_cmap_is_decoded(tmp_path):
    ext = extract(_embedded_cmap_pdf(tmp_path / "cmap.pdf"))
    assert [ln.text for ln in ext.lines] == ["Artikel 1 Gegenstand", "Diese Verordnung gilt."]
    assert ext.lines[0].size == 16
