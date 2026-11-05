"""Text that pdfminer's layout analysis used to drop (research finding F045): page text drawn inside a
form XObject that covers the page (printed UK Acts 2011-2016), and CID fonts whose encoding is a CMap
embedded in the PDF (Official Journal of the EU). Also which lines are set in italics (F061). The PDFs
are written by hand here."""

from __future__ import annotations

from pathlib import Path

from section_anything.extract import ITALIC_FONT, extract


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


def _fonts_pdf(path: Path) -> Path:
    """One page, a line per font: regular Helvetica, Times-Italic (italic by name), a font whose name says
    nothing but whose descriptor flags it italic and nonsymbolic, and a maths italic font (slanted, but
    flagged symbolic)."""
    widths = b" /FirstChar 32 /LastChar 126 /Widths [" + b" ".join([b"500"] * 95) + b"]"

    def described(name: bytes, flags: int, angle: int, descriptor: int) -> bytes:
        return (b"<< /Type /Font /Subtype /Type1 /BaseFont /" + name + b" /FontDescriptor %d 0 R" % descriptor + widths
                + b" /Encoding /WinAnsiEncoding >>")

    def descriptor(name: bytes, flags: int, angle: int) -> bytes:
        return (b"<< /Type /FontDescriptor /FontName /" + name + b" /Flags %d /ItalicAngle %d" % (flags, angle)
                + b" /FontBBox [0 -200 1000 900] /Ascent 900 /Descent -200 /CapHeight 700 /StemV 80 >>")

    content = (b"BT /F1 10 Tf 72 700 Td (Ordinary body text in a regular face.) Tj ET\n"
               b"BT /F2 10 Tf 72 680 Td (Appointment and tenure) Tj ET\n"
               b"BT /F3 10 Tf 72 660 Td (Term of office) Tj ET\n"
               b"BT /F4 10 Tf 72 640 Td (fxyz) Tj ET")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R /F2 5 0 R"
        b" /F3 6 0 R /F4 7 0 R >> >> /Contents 10 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Italic /Encoding /WinAnsiEncoding >>",
        described(b"ABCDEF+AdvTT21fb76a9", 96, -10, 8),
        described(b"GHIJKL+CMMI10", 4, -14, 9),
        descriptor(b"ABCDEF+AdvTT21fb76a9", 96, -10),
        descriptor(b"GHIJKL+CMMI10", 4, -14),
        _stream(content),
    ]
    return _write(path, objects, 1)


def test_lines_record_italics_by_font_name_or_descriptor(tmp_path):
    ext = extract(_fonts_pdf(tmp_path / "fonts.pdf"))
    assert [(ln.text, ln.italic) for ln in ext.lines] == [
        ("Ordinary body text in a regular face.", False), ("Appointment and tenure", True),
        ("Term of office", True), ("fxyz", False)]


def test_italic_font_names():
    italic = ["Times-Italic", "Arial-BoldItalicMT", "Arial,Italic", "Helvetica-Oblique", "MinionPro-It",
              "MyriadPro-SemiboldIt", "HelveticaNeueLTStd-LtIt", "NimbusRomNo9L-ReguItal", "EUAlbertina-ReguItal",
              "URWPalladioL-Ital", "CMTI10", "CMBXTI10", "CMSL10", "SFTI1000", "NimbusRomNo9L-Regu-Slant_167",
              "BookAntiquaParliamentary,Italic", "LMRoman10-Italic"]
    upright = ["Helvetica", "Times-Roman", "CMMI10", "CMSY10", "CMR10", "FreeSerif-Identity-H",
               "LucidaSans-Typewriter", "NunitoExtraLight-Medium", "ITCFranklinGothicStd-Book", "NimbusRomNo9L-Medi"]
    assert [n for n in italic if not ITALIC_FONT.search(n)] == []
    assert [n for n in upright if ITALIC_FONT.search(n)] == []
