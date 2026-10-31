"""PDF -> lines in reading order, with geometry and typography.

Uses pdfplumber/pdfminer.six (MIT) for layout and pypdfium2 (Apache-2.0 / BSD-3-Clause) for
page counts and bookmarks, not PyMuPDF (AGPL). pdfminer's layout analysis groups characters into
text boxes and orders the boxes for reading (`boxes_flow`), which keeps two-column pages in
column order.

Every line gets a character range in one canonical document string. Sections are expressed as
ranges in that string, so a section maps back to exact lines and, through their boxes, to exact
rectangles on the rendered page.

`extract` runs in the calling process. Untrusted PDFs should go through
`section_anything.isolate.extract_pdf`, which checks the caps first and runs `extract` in a
separate process with a time limit.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from section_anything.errors import PdfError, too_many_pages, too_much_text

T = TypeVar("T")

# Bump when the canonical text or the saved geometry changes. Extractions saved by an older
# version should be redone; runs record the version their character offsets refer to.
EXTRACTOR_VERSION = 5  # 5: deterministic reading order for equidistant boxes; 4: LaTeX bold fonts count as bold
# Oldest version whose canonical text is identical to the current one: offsets from that version
# on still map onto the page. Raise it only when `Extraction.text` changes. 5: lines of tied boxes
# (table cells) can come in another order (25 of 200 READoc development documents).
TEXT_COMPATIBLE_SINCE = 5

LAPARAMS = {
    "line_overlap": 0.5,
    "char_margin": 2.0,
    "line_margin": 0.5,
    "word_margin": 0.1,
    "boxes_flow": 0.5,
}
# Bold by name. TeX fonts say so in a code: CMBX/CMSSBX/CMBSY (Computer Modern bold),
# SFBX/SFSX/ECBX/EUBX (EC/European Modern bold), and Times bold is often NimbusRomNo9L-Medi.
BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demi|(?:^|\+)(?:CMBX|CMSSBX|CMBSY|SFBX|SFSX|ECBX|EUBX)|-Medi\b", re.I)
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass
class Page:
    n: int  # 1-based
    width: float
    height: float
    # pdfminer reports coordinates relative to the mediabox origin; PDF viewers (pdf.js) want
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
    # Flat [start, end, x0, x1, ...] per word: char offsets within `text` and the word's
    # horizontal extent in PDF user space. Lets a highlight start or stop mid-line.
    words: list[float] = field(default_factory=list)


@dataclass
class OutlineItem:
    """A PDF bookmark: 1-based level and page, and the target's y in PDF user space when the
    bookmark gives one."""

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
    # Values derived from this extraction (TOC, furniture, indexes), computed once and kept
    # with the object, so they are freed with it and never mixed up with another document's.
    _derived: dict[str, Any] = field(default_factory=dict, init=False, repr=False, compare=False)

    def derived(self, key: str, make: Callable[[Extraction], T]) -> T:
        """Compute `make(self)` once per extraction. Concurrent first calls may both compute; the
        first stored value wins, so every caller sees the same object."""
        try:
            return self._derived[key]
        except KeyError:
            return self._derived.setdefault(key, make(self))

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


# pypdfium2 (PDFium) is not thread-safe: every use in a process must hold this lock. Without it,
# extractions running in parallel threads silently lost their bookmarks.
PDFIUM_LOCK = threading.Lock()


def _open_pdfium(path: Path):
    """Open with PDFium (caller holds PDFIUM_LOCK). Raises PdfError with a message of our own."""
    import pypdfium2 as pdfium

    try:
        return pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        if "password" in str(exc).lower():
            raise PdfError("PDF is password-protected") from None
        raise PdfError("PDF could not be opened") from None


def count_pages(path: Path) -> int:
    """Page count from the PDF's page tree, without parsing any page content."""
    with PDFIUM_LOCK:
        pdf = _open_pdfium(path)
        try:
            return len(pdf)
        finally:
            pdf.close()


def chars_needed(seen: int, pages_read: int, pages: int) -> int:
    """A `max_chars` that should fit the whole text: the characters per page so far times the
    page count, with a 10% margin, rounded up to a million."""
    return math.ceil(seen / max(pages_read, 1) * pages * 1.1 / 1e6) * 1_000_000


def count_chars(path: Path, max_pages: int, max_chars: int) -> int:
    """Characters in the text layer, counted page by page with PDFium (much cheaper than layout
    analysis). Raises PdfTooLarge as soon as a cap is passed."""
    with PDFIUM_LOCK:
        pdf = _open_pdfium(path)
        try:
            n_pages = len(pdf)
            if n_pages > max_pages:
                raise too_many_pages(n_pages, max_pages)
            total = 0
            for k in range(n_pages):
                page = pdf[k]
                try:
                    textpage = page.get_textpage()
                    try:
                        total += max(0, textpage.count_chars())
                    finally:
                        textpage.close()
                finally:
                    page.close()
                if total > max_chars:
                    raise too_much_text(max_chars, chars_needed(total, k + 1, n_pages))
            return total
        finally:
            pdf.close()


def read_outline(path: Path, max_items: int = 5000) -> list[OutlineItem]:
    """The PDF's bookmarks via pypdfium2. Empty when there are none or the outline can't be
    read."""
    with PDFIUM_LOCK:
        return _read_outline(path, max_items)


def _read_outline(path: Path, max_items: int) -> list[OutlineItem]:
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


def _line_text_and_words(tl, dx: float) -> tuple[str, list[float]]:
    """The line's cleaned text (whitespace collapsed, control chars dropped) and its words' char
    ranges and x-extents. Built from the line's own glyphs so each output character keeps the box
    of the glyph it came from."""
    from pdfminer.layout import LTChar

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


def _stable_group_textboxes(self, laparams, boxes):
    """pdfminer's `LTLayoutContainer.group_textboxes` with ties broken by creation order.

    pdfminer merges the closest pair of boxes first and breaks equal distances by `id()`, a memory
    address that differs from process to process, so a page with equidistant boxes (table cells)
    could come out in a different reading order on every run. Here each box is numbered by its
    position in `boxes` and each group by when it was made; everything else is unchanged.

    Adapted from pdfminer.six 20260107, pdfminer/layout.py (MIT licence, Copyright (c) 2004-2016
    Yusuke Shinyama)."""
    import heapq

    from pdfminer.layout import LTTextBoxVertical, LTTextGroupLRTB, LTTextGroupTBRL
    from pdfminer.utils import Plane

    plane = Plane(self.bbox)
    seq: dict[int, int] = {id(b): k for k, b in enumerate(boxes)}

    def dist(obj1, obj2) -> float:
        x0, y0 = min(obj1.x0, obj2.x0), min(obj1.y0, obj2.y0)
        x1, y1 = max(obj1.x1, obj2.x1), max(obj1.y1, obj2.y1)
        return (x1 - x0) * (y1 - y0) - obj1.width * obj1.height - obj2.width * obj2.height

    def isany(obj1, obj2) -> set:
        x0, y0 = min(obj1.x0, obj2.x0), min(obj1.y0, obj2.y0)
        x1, y1 = max(obj1.x1, obj2.x1), max(obj1.y1, obj2.y1)
        return set(plane.find((x0, y0, x1, y1))).difference((obj1, obj2))

    dists = [(False, dist(b1, b2), i, j, b1, b2)
             for i, b1 in enumerate(boxes) for j, b2 in enumerate(boxes) if j > i]
    heapq.heapify(dists)
    plane.extend(boxes)
    done: set[int] = set()
    while dists:
        skip_isany, d, s1, s2, obj1, obj2 = heapq.heappop(dists)
        if s1 in done or s2 in done:
            continue
        if not skip_isany and isany(obj1, obj2):
            heapq.heappush(dists, (True, d, s1, s2, obj1, obj2))
            continue
        vertical = (LTTextBoxVertical, LTTextGroupTBRL)
        group = (LTTextGroupTBRL if isinstance(obj1, vertical) or isinstance(obj2, vertical)
                 else LTTextGroupLRTB)([obj1, obj2])
        plane.remove(obj1)
        plane.remove(obj2)
        done.update((s1, s2))
        sg = seq[id(group)] = len(seq)
        for other in plane:
            heapq.heappush(dists, (False, dist(group, other), sg, seq[id(other)], group, other))
        plane.add(group)
    return list(plane)


def _analyze(layout, laparams) -> None:
    """pdfminer's layout analysis of one page, with `_stable_group_textboxes` for this page only
    (pdfminer itself is not patched)."""
    layout.group_textboxes = _stable_group_textboxes.__get__(layout)
    layout.analyze(laparams)


def extract(
    path: Path,
    on_page: Callable[[int, int], None] | None = None,
    *,
    max_pages: int | None = None,
    max_chars: int | None = None,
) -> Extraction:
    """Extract lines from `path` in this process. With caps, the page count and the text size are
    checked with PDFium before layout analysis starts, and the character cap again while lines
    are collected."""
    import pdfplumber
    from pdfminer.layout import LAParams, LTChar, LTTextBox, LTTextLine

    path = Path(path)
    if max_pages is not None or max_chars is not None:
        count_chars(path, max_pages or 10**9, max_chars or 10**12)
    pages: list[Page] = []
    lines: list[Line] = []
    cursor = 0
    laparams = LAParams(**LAPARAMS)
    # pdfplumber gets no LAParams, so its pages come back unanalysed and `_analyze` runs the layout
    # analysis with a deterministic tie-break.
    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
        if max_pages is not None and total > max_pages:
            raise too_many_pages(total, max_pages)
        for n, page in enumerate(pdf.pages, 1):
            mb = page.mediabox
            before = len(lines)
            layout = page.layout
            _analyze(layout, laparams)
            for box in layout:
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
            if max_chars is not None and cursor > max_chars:
                raise too_much_text(max_chars, chars_needed(cursor, n, total))
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
