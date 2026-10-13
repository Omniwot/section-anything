"""PDF → lines in reading order, with geometry and typography.

Uses pdfplumber/pdfminer (MIT) rather than PyMuPDF (AGPL), so the app can be
served publicly without source-disclosure obligations. pdfminer's layout
analysis groups characters into text boxes and orders the boxes for reading
(`boxes_flow`), which keeps two-column pages in column order.

Every line gets a character range in one canonical document string. Sections
are expressed as ranges in that string, so a section maps back to exact lines
and, through their boxes, to exact rectangles on the rendered page.
"""

from __future__ import annotations

import json
import re
import statistics
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pdfplumber
from pdfminer.layout import LTChar, LTTextBox, LTTextLine

# Bump when the canonical text or the saved geometry changes. Documents
# extracted with an older version are re-extracted, and runs record the version
# their character offsets refer to.
EXTRACTOR_VERSION = 3
# Oldest version whose canonical text is identical to the current one. Runs
# from that version on still map onto the page; older runs are stale. Raise it
# only when `Extraction.text` changes (2 added word boxes, 3 the PDF outline).
TEXT_COMPATIBLE_SINCE = 1

LAPARAMS = {
    "line_overlap": 0.5,
    "char_margin": 2.0,
    "line_margin": 0.5,
    "word_margin": 0.1,
    "boxes_flow": 0.5,
}
BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demi", re.I)
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass
class Page:
    n: int  # 1-based
    width: float
    height: float
    # pdfminer reports coordinates relative to the mediabox origin; pdf.js wants
    # PDF user space, so keep the origin to shift boxes back.
    origin_x: float
    origin_y: float
    rotation: int
    has_text: bool


@dataclass
class Line:
    i: int
    page: int
    text: str
    # PDF user-space box (origin bottom-left), ready for pdf.js
    # viewport.convertToViewportRectangle.
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    bold: bool
    start: int  # char range in Extraction.text
    end: int
    # Flat [start, end, x0, x1, ...] per word: char offsets within `text` and
    # the word's horizontal extent in PDF user space. Lets a highlight start or
    # stop mid-line.
    words: list[float] = field(default_factory=list)


@dataclass
class OutlineItem:
    """A PDF bookmark: 1-based level and page, and the target's y in PDF user
    space when the bookmark gives one."""

    level: int
    title: str
    page: int
    y: float | None = None


@dataclass
class Extraction:
    pages: list[Page]
    lines: list[Line]
    text: str
    version: int = EXTRACTOR_VERSION
    outline: list[OutlineItem] = field(default_factory=list)

    def body_size(self) -> float:
        """The most common font size weighted by characters: the body text."""
        weights: dict[float, int] = {}
        for ln in self.lines:
            weights[ln.size] = weights.get(ln.size, 0) + len(ln.text)
        return max(weights, key=weights.get) if weights else 10.0

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "version": self.version,
                    "pages": [asdict(p) for p in self.pages],
                    "lines": [asdict(ln) for ln in self.lines],
                    "outline": [asdict(o) for o in self.outline],
                },
                separators=(",", ":"),
            )
        )

    @classmethod
    def load(cls, path: Path) -> Extraction:
        raw = json.loads(path.read_text())
        lines = [Line(**ln) for ln in raw["lines"]]
        return cls(
            [Page(**p) for p in raw["pages"]], lines, "\n".join(ln.text for ln in lines), raw.get("version", 1),
            [OutlineItem(**o) for o in raw.get("outline", [])],
        )


def read_outline(path: Path, max_items: int = 5000) -> list[OutlineItem]:
    """The PDF's bookmarks via pypdfium2 (Apache/BSD). Empty when there are
    none or the outline can't be read."""
    import pypdfium2 as pdfium

    out: list[OutlineItem] = []
    try:
        pdf = pdfium.PdfDocument(str(path))
        try:
            for b in pdf.get_toc(max_depth=8):
                dest = b.get_dest()
                if dest is None or dest.get_index() is None:
                    continue
                y = None
                try:
                    _mode, pos = dest.get_view()
                    y = float(pos[1]) if len(pos) > 1 and pos[1] is not None else None
                except Exception:  # noqa: BLE001 — position is optional
                    y = None
                title = re.sub(r"\s+", " ", b.get_title() or "").strip()
                if title:
                    out.append(OutlineItem(level=b.level + 1, title=title, page=dest.get_index() + 1, y=y))
                if len(out) >= max_items:
                    break
        finally:
            pdf.close()
    except Exception:  # noqa: BLE001 — a broken outline must not fail extraction
        return []
    return out


def _line_text_and_words(tl: LTTextLine, dx: float) -> tuple[str, list[float]]:
    """The line's cleaned text (whitespace collapsed, control chars dropped) and
    its words' char ranges and x-extents. Built from the line's own glyphs so
    each output character keeps the box of the glyph it came from."""
    raw: list[tuple[str, tuple[float, float] | None]] = []
    for obj in tl:
        box = (obj.x0 + dx, obj.x1 + dx) if isinstance(obj, LTChar) else None
        for ch in obj.get_text():
            raw.append((ch, box))
    chars: list[tuple[str, tuple[float, float] | None]] = []
    for ch, box in raw:
        if CONTROL.match(ch):
            continue
        if ch.isspace():
            if chars and chars[-1][0] != " ":
                chars.append((" ", None))
            continue
        chars.append((ch, box))
    while chars and chars[-1][0] == " ":
        chars.pop()
    text = "".join(ch for ch, _ in chars)

    words: list[float] = []
    i = 0
    while i < len(chars):
        if chars[i][0] == " ":
            i += 1
            continue
        j = i
        while j < len(chars) and chars[j][0] != " ":
            j += 1
        xs = [b for _, b in chars[i:j] if b]
        if xs:
            words += [i, j, round(min(b[0] for b in xs), 2), round(max(b[1] for b in xs), 2)]
        i = j
    return text, words


def extract(path: Path, on_page: Callable[[int, int], None] | None = None) -> Extraction:
    pages: list[Page] = []
    lines: list[Line] = []
    cursor = 0
    with pdfplumber.open(path, laparams=LAPARAMS) as pdf:
        total = len(pdf.pages)
        for n, page in enumerate(pdf.pages, 1):
            mb = page.mediabox
            before = len(lines)
            for box in page.layout:
                if not isinstance(box, LTTextBox):
                    continue
                for tl in box:
                    if not isinstance(tl, LTTextLine):
                        continue
                    text, words = _line_text_and_words(tl, mb[0])
                    if not text:
                        continue
                    chars = [c for c in tl if isinstance(c, LTChar)]
                    size = round(statistics.median(c.size for c in chars), 1) if chars else 0.0
                    bold = bool(chars) and sum(bool(BOLD_FONT.search(c.fontname)) for c in chars) * 2 > len(chars)
                    lines.append(
                        Line(
                            i=len(lines), page=n, text=text,
                            x0=round(tl.x0 + mb[0], 2), y0=round(tl.y0 + mb[1], 2),
                            x1=round(tl.x1 + mb[0], 2), y1=round(tl.y1 + mb[1], 2),
                            size=size, bold=bold, start=cursor, end=cursor + len(text), words=words,
                        )
                    )
                    cursor += len(text) + 1  # lines are joined with "\n"
            pages.append(
                Page(
                    n=n, width=float(page.width), height=float(page.height),
                    origin_x=float(mb[0]), origin_y=float(mb[1]),
                    rotation=int(page.rotation or 0), has_text=len(lines) > before,
                )
            )
            page.close()  # drop pdfplumber's per-page caches; matters at 500 pages
            if on_page:
                on_page(n, total)
    return Extraction(pages, lines, "\n".join(ln.text for ln in lines), outline=read_outline(path))
