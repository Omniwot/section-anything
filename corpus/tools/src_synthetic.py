"""Generated edge cases with exact gold. Each isolates one thing a sectioner
can get wrong: headings with no size cue, headings with only numbering,
run-in heads, a dot-leader contents list with offset page numbers, two
columns with captions, bold non-heading lines, rotated pages, image-only
pages, six heading levels, a 500-page document, and files that can't be
read at all (encrypted, truncated)."""

from __future__ import annotations

import random

from common import CACHE, Entry, built, rasterise, register
from gen import Style, render
from reportlab.lib.enums import TA_LEFT
from src_gutenberg import _book

ADJ = ["Thermal", "Adaptive", "Regional", "Structural", "Long-term", "Seasonal", "Comparative", "Residual", "Lateral",
       "Primary", "Secondary", "Coastal", "Urban", "Hydraulic", "Acoustic", "Optical", "Statistical", "Field"]
NOUN = ["Drift", "Sampling", "Load Paths", "Calibration", "Water Balance", "Survey Design", "Noise Floor", "Erosion",
        "Fatigue", "Benchmarks", "Interpolation", "Maintenance", "Sensor Placement", "Uncertainty", "Retrofits",
        "Material Selection", "Data Quality", "Validation", "Scheduling", "Coverage"]
TAIL = ["", "", "", " in Practice", " and Its Limits", " for Small Sites", " Revisited", " under Load", " at Scale"]


def _filler() -> list[str]:
    paras = [t for k, t in _book(205) + _book(1228) if k == "p" and 250 < len(t) < 1500]
    return paras


def _title(rnd: random.Random) -> str:
    return f"{rnd.choice(ADJ)} {rnd.choice(NOUN)}{rnd.choice(TAIL)}"


def _outline(rnd: random.Random, fill: list[str], *, levels: int, fan: tuple, paras: tuple, numbering: str,
             runin_from: int = 0) -> list[tuple]:
    """Heading tree with filler paragraphs. numbering: decimal | none | mixed (I., A., 1., a))."""
    out: list[tuple] = []
    counters = [0] * (levels + 1)

    def num(lvl: int) -> str:
        if numbering == "none":
            return ""
        if numbering == "decimal":
            return ".".join(str(counters[i]) for i in range(1, lvl + 1)) + " "
        n = counters[lvl]
        roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
        return [f"{roman[(n - 1) % 12]}. ", f"{chr(64 + n)}. ", f"{n}. ", f"({chr(96 + n)}) "][min(lvl, 4) - 1]

    def walk(lvl: int) -> None:
        for _ in range(rnd.randint(*fan)):
            counters[lvl] += 1
            for deeper in range(lvl + 1, levels + 1):
                counters[deeper] = 0
            title = num(lvl) + _title(rnd)
            if runin_from and lvl >= runin_from:
                out.append(("runin", lvl, title, rnd.choice(fill)))
                for _ in range(rnd.randint(0, paras[1] - 1)):
                    out.append(("p", rnd.choice(fill)))
            else:
                out.append(("h", lvl, title))
                for _ in range(rnd.randint(*paras)):
                    out.append(("p", rnd.choice(fill)))
            if lvl < levels:
                walk(lvl + 1)

    walk(1)
    return out


BODY = {lvl: ("Times-Bold", 11, TA_LEFT, False, 10) for lvl in range(1, 5)}
PLAIN = {lvl: ("Times-Roman", 11, TA_LEFT, False, 8) for lvl in range(1, 5)}
SANS = {1: ("Helvetica-Bold", 16, TA_LEFT, False, 20), 2: ("Helvetica-Bold", 13, TA_LEFT, False, 14),
        3: ("Helvetica-Bold", 11, TA_LEFT, False, 10), 4: ("Helvetica-BoldOblique", 10, TA_LEFT, False, 8)}
SIX = {1: ("Helvetica-Bold", 18, TA_LEFT, False, 20), 2: ("Helvetica-Bold", 15, TA_LEFT, False, 16),
       3: ("Helvetica-Bold", 13, TA_LEFT, False, 12), 4: ("Helvetica-Bold", 11.5, TA_LEFT, False, 10),
       5: ("Helvetica-BoldOblique", 10.5, TA_LEFT, False, 8), 6: ("Helvetica-Oblique", 10, TA_LEFT, False, 6)}


def _captions(rnd: random.Random, blocks: list[tuple], every: int) -> list[tuple]:
    """Insert figures/tables with bold captions and bold callouts that are not headings."""
    out, n = [], 0
    for b in blocks:
        out.append(b)
        if b[0] != "p":
            continue
        n += 1
        if n % every == 0:
            k = n // every
            if k % 3 == 0:
                out += [("image",), ("label", f"Figure {k}. {_title(rnd)} across all sites")]
            elif k % 3 == 1:
                rows = [["Site", "Mean", "SD", "n"]] + [[f"S{i}", f"{rnd.uniform(1, 9):.2f}", f"{rnd.uniform(0, 2):.2f}",
                                                        str(rnd.randint(10, 300))] for i in range(1, 6)]
                out += [("label", f"Table {k}. {_title(rnd)}"), ("table", rows)]
            else:
                out += [("label", rnd.choice(["NOTE", "WARNING", "Tip", "Important", "Example"])),
                        ("p", rnd.choice(["Check the calibration log before each run.",
                                          "Values below the detection limit are reported as zero.",
                                          "This step is skipped for sites without a baseline survey."]))]
    return out


def _toc_doc(rnd: random.Random, fill: list[str], out_pdf) -> list[dict]:
    """Title page + 2-page contents with printed numbers offset by 3, then body.
    Rendered twice: the first pass finds where headings land."""
    body = _outline(rnd, fill, levels=3, fan=(3, 4), paras=(1, 3), numbering="decimal")

    def doc(toc_entries):
        blocks = [("label", "A Field Manual for Survey Teams"), ("p", "Second edition."), ("page",),
                  ("label", "Contents")] + toc_entries + [("page",)]
        while sum(1 for b in blocks if b[0] == "page") < 3:
            blocks.append(("page",))
        return blocks + body

    dummy = [("tocline", b[1], b[2], 0) for b in body if b[0] == "h"]
    gold = render(doc(dummy), Style(number_offset=3), out_pdf, title="A Field Manual for Survey Teams")
    toc = [("tocline", g["level"], g["title"], g["page"] - 3) for g in gold]
    return render(doc(toc), Style(number_offset=3), out_pdf, title="A Field Manual for Survey Teams")


def build(force: bool = False) -> None:
    fill = _filler()
    d = CACHE / "synthetic"
    d.mkdir(parents=True, exist_ok=True)

    def make(eid: str, title: str, why: str, blocks: list[tuple], style: Style, *, post=None, notes: str = "",
             extra: dict | None = None) -> None:
        if built(eid) and not force:
            return
        out = d / f"{eid}.pdf"
        gold = render(blocks, style, out, title=title)
        if post:
            post(out, gold)
        register(Entry(id=eid, category="synthetic", title=title, source_url="generated",
                       license="Generated; filler text from public-domain Project Gutenberg books",
                       gold_source="generator", variant=why, notes=notes, extra=extra or {}), out, gold)

    r = random.Random
    make("synth-bold-body-size", "Bold headings at body size", "no size cue: headings are bold body-size text",
         _outline(r(1), fill, levels=3, fan=(3, 5), paras=(1, 3), numbering="none"), Style(heading=BODY))
    make("synth-numbering-only", "Numbered headings in body font", "only cue is 1.2.3 numbering; same font as body",
         _outline(r(2), fill, levels=3, fan=(3, 5), paras=(1, 3), numbering="decimal"), Style(heading=PLAIN))
    make("synth-run-in", "Run-in headings", "levels 2-3 run into their paragraph",
         _outline(r(3), fill, levels=3, fan=(3, 5), paras=(1, 3), numbering="mixed", runin_from=2), Style())
    if force or not built("synth-dot-leader-toc"):
        out = d / "synth-dot-leader-toc.pdf"
        gold = _toc_doc(r(4), fill, out)
        register(Entry(id="synth-dot-leader-toc", category="synthetic", title="Dot-leader contents, offset numbers",
                       source_url="generated", license="Generated; filler text from public-domain Project Gutenberg books",
                       gold_source="generator", variant="contents list with dot leaders; printed page = physical - 3",
                       extra={"page_offset": 3}), out, gold)
    make("synth-two-column", "Two-column paper with figures and tables",
         "two columns; bold figure/table captions are not headings",
         _captions(r(5), _outline(r(5), fill, levels=2, fan=(4, 6), paras=(2, 4), numbering="decimal"), 3),
         Style(columns=2, body_size=9.5, leading=11.5, margin=50, heading=SANS))
    make("synth-false-positives", "Many bold lines that are not headings",
         "callouts (NOTE, WARNING), captions and tables between real headings",
         _captions(r(6), _outline(r(6), fill, levels=3, fan=(3, 4), paras=(2, 3), numbering="none"), 1),
         Style(heading=SANS, body_font="Helvetica", body_size=10, leading=13))
    make("synth-running-headers", "Running headers repeat the chapter title",
         "every page header repeats the current chapter title; chapter per page",
         _outline(r(7), fill, levels=2, fan=(5, 7), paras=(3, 6), numbering="none"),
         Style(header="{h1}", new_page_level=1, heading=SANS))

    def rotate(out, gold) -> None:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(out))
        for i in range(1, len(pdf), 4):
            pdf[i].set_rotation(90)
        pdf.save(str(out) + ".tmp")
        pdf.close()
        (out.parent / (out.name + ".tmp")).replace(out)

    make("synth-rotated-pages", "Every fourth page rotated", "pages 2, 6, 10, ... have /Rotate 90",
         _outline(r(8), fill, levels=3, fan=(3, 4), paras=(1, 3), numbering="decimal"), Style(heading=SANS),
         post=rotate)

    image_pages: set[int] = set()

    def images(out, gold) -> None:
        import pypdfium2 as pdfium
        n = len(pdfium.PdfDocument(str(out)))
        image_pages.update(range(3, n + 1, 3))
        tmp = out.parent / (out.name + ".tmp")
        rasterise(out, tmp, image_pages, dpi=150)
        tmp.replace(out)
        for g in gold:
            if g["page"] in image_pages:
                g["image_only"] = True

    make("synth-image-pages", "Every third page is an image", "pages 3, 6, 9, ... have no text layer (need OCR)",
         _outline(r(9), fill, levels=2, fan=(5, 7), paras=(2, 4), numbering="decimal"), Style(heading=SANS),
         post=images, notes="headings marked image_only are recoverable only with OCR")
    make("synth-six-levels", "Six heading levels", "1 to 1.1.1.1.1.1, shrinking sizes",
         _outline(r(10), fill, levels=6, fan=(2, 2), paras=(1, 1), numbering="decimal"), Style(heading=SIX))
    make("synth-stress-500", "500-page stress test", "about 500 pages, four levels, ~700 headings",
         _outline(r(11), fill, levels=4, fan=(5, 5), paras=(2, 4), numbering="decimal"),
         Style(heading=SANS, body_size=10.5, leading=13.5))

    if force or not built("synth-encrypted"):
        out = d / "synth-encrypted.pdf"
        render(_outline(r(12), fill, levels=2, fan=(3, 3), paras=(1, 2), numbering="decimal"),
               Style(encrypt="corpus"), out, title="Encrypted")
        register(Entry(id="synth-encrypted", category="synthetic", title="Password-protected PDF", source_url="generated",
                       license="Generated", gold_source="generator", variant="upload-check",
                       notes="user password 'corpus'; the app should reject it with a clear message"), out, [])
    if force or not built("synth-truncated"):
        src = d / "synth-bold-body-size.pdf"
        out = d / "synth-truncated.pdf"
        raw = src.read_bytes()
        out.write_bytes(raw[: len(raw) // 2])
        register(Entry(id="synth-truncated", category="synthetic", title="Truncated PDF", source_url="generated",
                       license="Generated", gold_source="generator", variant="upload-check",
                       notes="first half of a valid PDF; the app should reject or partially read it without crashing"),
                 out, [])
