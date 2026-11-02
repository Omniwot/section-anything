"""Docling's output as input: its layout labels as hints for a PDF's own lines, or its text items as
the lines themselves.

Two ways in, both from a `DoclingDocument` (the object, its JSON form as a dict, or the path of a
JSON file saved with `save_as_json`):

- Hints (`attach_hints`): the PDF is extracted as usual, so font sizes, bold, bookmarks and the
  printed table of contents still count. Each line that sits inside a Docling item takes that
  item's label: lines of a ``section_header`` or ``title`` become heading candidates whatever
  their style, lines of a ``page_header`` or ``page_footer`` become furniture, and, in strict
  (Free) mode, styled lines that Docling reads as body text, list items, captions or code are
  not headings.
- Lines (`extraction_from_docling`): the document's text items become the lines, so no PDF text
  layer is needed. Scanned PDFs go through Docling's OCR, and the same holds for any format
  Docling reads. Docling gives no font sizes, so a heading's size stands in for its level when
  Docling's levels differ (its heading-hierarchy stage, or markup headings), and is read from the
  height of its box otherwise.

docling-core is not needed: everything here reads the JSON form (`export_to_dict()`).
"""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from section_anything.errors import ConfigError
from section_anything.extract import CONTROL, Extraction, Line, OutlineItem, Page
from section_anything.markers import canon

HEADING = frozenset({"section_header", "title"})
FURNITURE = frozenset({"page_header", "page_footer"})
BODY_SIZE = 10.0  # Docling gives no font sizes: body lines get this one, headings a bigger one
# Hints from Docling's output of another PDF would label lines at random. Of the PDF's lines inside
# Docling's text boxes, the share whose text is in the text of a box that holds them was 0.57 to
# 1.00 on 26 matching pairs (slides lowest) and 0.00 to 0.24 with each document's JSON swapped for
# another's (F041's documents, 2 Nov 2026).
MIN_AGREEMENT = 0.4


@dataclass
class DoclingHints:
    """Docling's labels for the lines of an extraction (line indexes)."""

    headers: set[int] = field(default_factory=set)
    furniture: set[int] = field(default_factory=set)
    body: set[int] = field(default_factory=set)  # any other labelled text: text, list items, captions, code
    item: dict[int, int] = field(default_factory=dict)  # heading line -> its Docling item, to keep items apart

    def same_item(self, a: int, b: int) -> bool:
        """Lines `a` and `b` belong to one Docling heading, or Docling does not say otherwise."""
        return a not in self.item or b not in self.item or self.item[a] == self.item[b]


def is_docling_document(obj: Any) -> bool:
    """A `DoclingDocument`, its JSON form as a dict, or the path of a ``.json`` file (checked when read)."""
    if isinstance(obj, Mapping):
        return obj.get("schema_name") == "DoclingDocument"
    if isinstance(obj, str | os.PathLike):
        return Path(obj).suffix.lower() == ".json"
    return type(obj).__name__ == "DoclingDocument" and hasattr(obj, "export_to_dict")


def as_dict(doc: Any) -> dict:
    if isinstance(doc, str | os.PathLike):
        try:
            d = json.loads(Path(doc).read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError(f"cannot read the Docling JSON {os.fspath(doc)!r}: {exc.strerror or exc}") from None
        except ValueError:  # also UnicodeDecodeError
            raise ConfigError(f"{os.fspath(doc)!r} is not JSON: expected a DoclingDocument saved as JSON") from None
        if not isinstance(d, dict):
            raise ConfigError(f"{os.fspath(doc)!r} is not a DoclingDocument's JSON")
    elif isinstance(doc, Mapping):
        d = dict(doc)
    elif hasattr(doc, "export_to_dict"):
        d = doc.export_to_dict()
    else:
        raise TypeError(f"expected a DoclingDocument, its JSON as a dict or a .json path, got {type(doc).__name__}")
    if d.get("schema_name") != "DoclingDocument":
        raise ConfigError("not a DoclingDocument: its JSON has no schema_name 'DoclingDocument'")
    return d


def hints_of(ext: Extraction) -> DoclingHints | None:
    return ext._derived.get("docling")


def _resolve(d: dict, ref: str) -> dict:
    _, kind, idx = ref.split("/")
    return d[kind][int(idx)]


def _items(d: dict) -> Iterator[dict]:
    """Every item of the body tree, then of the furniture tree, depth first in reading order."""
    seen: set[str] = set()
    for root in ("body", "furniture"):
        stack = [c["$ref"] for c in reversed(d.get(root, {}).get("children", []))]
        while stack:
            ref = stack.pop()
            if ref in seen:
                continue
            seen.add(ref)
            item = _resolve(d, ref)
            yield item
            stack.extend(c["$ref"] for c in reversed(item.get("children", [])))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", CONTROL.sub("", text or "")).strip()


def _box(prov: dict, page_height: float) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) with the origin at the page's bottom left."""
    b = prov["bbox"]
    if b.get("coord_origin", "BOTTOMLEFT") == "TOPLEFT":
        return b["l"], page_height - b["b"], b["r"], page_height - b["t"]
    return b["l"], b["b"], b["r"], b["t"]


def _table_rows(item: dict) -> list[str]:
    cells: dict[int, list[tuple[int, str]]] = {}
    for c in (item.get("data") or {}).get("table_cells", []):
        cells.setdefault(c.get("start_row_offset_idx", 0), []).append((c.get("start_col_offset_idx", 0), c.get("text", "")))
    return [_clean(" ".join(t for _, t in sorted(row))) for _, row in sorted(cells.items())]


def _pieces(d: dict) -> Iterator[tuple[dict, int, str, tuple[float, float, float, float]]]:
    """(item, page, text, box) for each text item and table row, one per page an item is on."""
    heights = {int(n): p["size"]["height"] for n, p in d.get("pages", {}).items()}
    for item in _items(d):
        provs = [p for p in item.get("prov") or [] if p.get("page_no") in heights]
        if not provs:
            continue
        if "data" in item and "table_cells" in (item.get("data") or {}):
            box = _box(provs[0], heights[provs[0]["page_no"]])
            for row in _table_rows(item):
                if row:
                    yield item, provs[0]["page_no"], row, box
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        for p in provs:
            span = p.get("charspan") or [0, len(text)]
            piece = _clean(text[span[0]:span[1]] if len(provs) > 1 else text)
            if piece:
                yield item, p["page_no"], piece, _box(p, heights[p["page_no"]])


def _read(d: dict) -> list[tuple[dict, int, str, tuple[float, float, float, float]]]:
    try:
        return list(_pieces(d))
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:  # a hand-edited or truncated JSON
        raise ConfigError(f"malformed DoclingDocument JSON ({type(exc).__name__}: {exc})") from None


def _offsets(ext: Extraction, by_page: dict[int, list]) -> dict[int, tuple[float, float]]:
    """Per page, what to subtract from a line's coordinates to get Docling's. Docling measures from
    the page's crop box, the extraction from the PDF's own origin; the two differ when a PDF is
    cropped. Read from lines whose text is a whole Docling item, alone of its kind on the page;
    pages without such a line take the document's median."""
    found: dict[int, tuple[float, float]] = {}
    for n, items in by_page.items():
        texts = [c[2] for c in items]
        unique = {c[2]: c[3] for c in items if texts.count(c[2]) == 1 and len(c[2]) >= 4}
        lines = [ln for ln in ext.lines if ln.page == n]
        seen = [canon(ln.text) for ln in lines]
        dx = sorted(ln.x0 - (unique[t][0] + 2) for ln, t in zip(lines, seen, strict=True) if t in unique and seen.count(t) == 1)
        dy = sorted(ln.y0 - (unique[t][1] + 2) for ln, t in zip(lines, seen, strict=True) if t in unique and seen.count(t) == 1)
        if dx:
            found[n] = (dx[len(dx) // 2], dy[len(dy) // 2])
    if not found:
        return {}
    xs, ys = sorted(v[0] for v in found.values()), sorted(v[1] for v in found.values())
    median = (xs[len(xs) // 2], ys[len(ys) // 2])
    return {p.n: found.get(p.n, median) for p in ext.pages}


def attach_hints(ext: Extraction, doc: Any, *, veto: bool = True) -> DoclingHints:
    """Label the extraction's lines from the Docling items whose boxes hold them. A line counts as
    a heading only when its text is also in the item's text, so a box that covers more than its
    heading does not pull body lines in. `veto` keeps the body labels, which strict mode uses to
    drop styled lines Docling reads as body text. Lines outside every Docling box get no label.
    Call before the extraction's TOC or furniture is computed.

    Raises `ConfigError` when the document is not Docling's output of this PDF: too few of the
    lines inside its boxes have the item's text (`MIN_AGREEMENT`). A document with no text items
    gives no hints."""
    d = as_dict(doc)
    by_page: dict[int, list[tuple[float, str, str, tuple[float, float, float, float], int]]] = {}
    for k, (item, page, text, (x0, y0, x1, y1)) in enumerate(_read(d)):
        area = max(x1 - x0, 0.0) * max(y1 - y0, 0.0)
        by_page.setdefault(page, []).append((area, item.get("label", ""), canon(text), (x0 - 2, y0 - 2, x1 + 2, y1 + 2), k))
    offset = _offsets(ext, by_page)
    hints = DoclingHints()
    checked = agreed = 0  # lines with text inside a Docling box; those whose text is in such a box's
    for ln in ext.lines:
        ox, oy = offset.get(ln.page, (0.0, 0.0))
        cx, cy = (ln.x0 + ln.x1) / 2 - ox, (ln.y0 + ln.y1) / 2 - oy
        inside = sorted(c for c in by_page.get(ln.page, []) if c[3][0] <= cx <= c[3][2] and c[3][1] <= cy <= c[3][3])
        if not inside:
            continue
        own = canon(ln.text)
        if own:
            checked += 1
            agreed += any(own in c[2] for c in inside)  # table rows share their table's box
        _area, label, text, _box, k = inside[0]  # the smallest box that holds the line
        if label in HEADING:
            if own and own in text:
                hints.headers.add(ln.i)
                hints.item[ln.i] = k
        elif label in FURNITURE:
            hints.furniture.add(ln.i)
        elif veto:
            hints.body.add(ln.i)
    _check_match(ext, d, bool(by_page), checked, agreed)
    ext._derived["docling"] = hints
    return hints


def _check_match(ext: Extraction, d: dict, has_items: bool, checked: int, agreed: int) -> None:
    """Refuse hints from Docling's output of another PDF (see `MIN_AGREEMENT`)."""
    if not has_items or not ext.text.strip():
        return  # no Docling text, or no PDF text: nothing to label
    if checked and agreed / checked >= MIN_AGREEMENT:
        return
    found = (f"only {agreed / checked:.0%} of the PDF's lines inside Docling's text boxes have the same text"
             if checked else "none of the PDF's lines is inside Docling's text boxes")
    raise ConfigError(
        f"docling= does not look like Docling's output of this PDF: {found} (PDF {len(ext.pages)} pages, "
        f"Docling {len(d.get('pages', {}))}). Pass the DoclingDocument that Docling made from this same PDF."
    )


def _height_sizes(heights: list[float]) -> dict[float, float]:
    """A font size for each heading box height: heights within 10% of their neighbour are one
    size (OCR boxes of one heading style vary by a few points), the cluster's most common one."""
    out: dict[float, float] = {}
    cluster: list[float] = []
    for h in sorted(heights) + [math.inf]:
        if cluster and h > cluster[-1] * 1.1:
            size = max(set(cluster), key=lambda v: (cluster.count(v), v))
            out.update(dict.fromkeys(cluster, size))
            cluster = []
        cluster.append(h)
    return out


def _estimate(box: tuple[float, float, float, float]) -> float:
    return round(max(box[3] - box[1], 0.0) / 1.2 * 2) / 2  # a line box is about 1.2 x the font size


def extraction_from_docling(doc: Any, levels: str = "outline") -> Extraction:
    """An extraction whose lines are the document's text items and table rows, in Docling's
    reading order, with page headers first and page footers last on each page.

    Docling gives no font sizes. A heading's size is read from the height of its box. When
    Docling's heading levels differ (its heading-hierarchy stage, or a format with marked-up
    levels), they are used as the document's outline (`levels="outline"`), as bookmarks would
    be, or stand in for the size (`levels="size"`)."""
    d = as_dict(doc)
    pieces = _read(d)
    found = {it.get("level") for it, *_ in pieces if it.get("label") == "section_header"}
    leveled = len(found - {None}) > 1
    top = max((lv for lv in found if lv), default=1)
    sizes = _height_sizes([_estimate(box) for it, _p, _t, box in pieces if it.get("label") == "section_header"])

    def style(item: dict, box: tuple[float, float, float, float]) -> tuple[float, bool]:
        if item.get("label") == "section_header":
            if leveled and levels == "size":
                return BODY_SIZE + 2 * (top + 1 - int(item.get("level") or top)), True
            return sizes[_estimate(box)], True
        return BODY_SIZE, False

    sized = [(it, page, text, box, *style(it, box)) for it, page, text, box in pieces]
    biggest = max((s for it, *_, s, _b in sized if it.get("label") == "section_header"), default=BODY_SIZE)
    order = {"page_header": 0, "page_footer": 2}
    sized.sort(key=lambda r: (r[1], order.get(r[0].get("label"), 1)))  # stable: reading order within a page

    pages_meta = {int(n): p["size"] for n, p in d.get("pages", {}).items()}
    lines: list[Line] = []
    hints = DoclingHints()
    cursor = 0
    for item, page, text, (x0, y0, x1, y1), size, bold in sized:
        label = item.get("label")
        if label == "title":
            size, bold = biggest + 2, True
        i = len(lines)
        lines.append(Line(i=i, page=page, text=text, x0=round(x0, 2), y0=round(y0, 2), x1=round(x1, 2), y1=round(y1, 2),
                          size=size, bold=bold, start=cursor, end=cursor + len(text)))
        cursor += len(text) + 1
        (hints.headers if label in HEADING else hints.furniture if label in FURNITURE else hints.body).add(i)
    with_text = {ln.page for ln in lines}
    pages = [Page(n=n, width=float(s["width"]), height=float(s["height"]), origin_x=0.0, origin_y=0.0, rotation=0,
                  has_text=n in with_text) for n, s in sorted(pages_meta.items())]
    outline = []
    if leveled and levels == "outline":
        # The title is level 0 to Docling; at level 1 it stays a heading, and `mark_doc_title` sets it apart.
        outline = [OutlineItem(level=int(it.get("level") or top) if it.get("label") == "section_header" else 1,
                               title=text, page=page, y=box[3])
                   for it, page, text, box, _s, _b in sized if it.get("label") in HEADING]
    ext = Extraction(pages, lines, "\n".join(ln.text for ln in lines), outline=outline)
    ext._derived["docling"] = hints
    return ext
