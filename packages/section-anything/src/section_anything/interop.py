"""Section trees in Unstructured's and Docling's document formats, so their section-aware chunkers
(Unstructured's `chunk_by_title`, Docling's `HybridChunker`) can run on Section Anything's headings.

Both exports hold, in reading order, one heading item per section ("number title", its level, page
and box) followed by the section's body paragraphs as `to_markdown(body=True)` prints them (running
headers and footers removed, lines reflowed), each paragraph with the page and box of its lines.
Front matter (text before the first heading) gets no heading item. A tree with no extraction (built
by hand) exports its headings only.

Boxes are in PDF points from the page's corner, as each format expects: Unstructured's
``PixelSpace`` (origin top-left, the system its own fast PDF strategy uses), Docling's
``CoordOrigin.BOTTOMLEFT`` (as Docling's PDF pipeline stores them).
"""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING, Any

from section_anything.errors import ConfigError
from section_anything.export import Paragraph, heading_text, section_parts

if TYPE_CHECKING:
    from docling_core.types.doc import DoclingDocument

    from section_anything.api import SectionTree

DOCLING_EXTRA = "to_docling_document() needs the docling extra: pip install 'section-anything[docling]'"
PDF_MIME = "application/pdf"
PathLike = str | os.PathLike[str]


def _parts(tree: SectionTree) -> list[tuple[list[Any], list[Paragraph]]]:
    """Heading lines and body paragraphs per section, or none when the tree has no extraction."""
    ext = tree.extraction
    if ext is None or len(tree.resolved) != len(tree.sections):
        return [([], []) for _ in tree.sections]
    from section_anything.structure import furniture_of

    return section_parts(ext, tree.resolved, furniture_of(ext))


def _box(lines: list[Any], pages: dict[int, Any]) -> tuple[float, float, float, float] | None:
    """(left, bottom, right, top) around `lines` on the first one's page, in PDF points from the
    page's bottom-left corner."""
    if not lines or lines[0].page not in pages:
        return None
    pg = pages[lines[0].page]
    on = [ln for ln in lines if ln.page == pg.n]
    return (round(min(ln.x0 for ln in on) - pg.origin_x, 2), round(min(ln.y0 for ln in on) - pg.origin_y, 2),
            round(max(ln.x1 for ln in on) - pg.origin_x, 2), round(max(ln.y1 for ln in on) - pg.origin_y, 2))


def _depth(sec: dict) -> int:
    """Unstructured's `category_depth`: 0 for the document title, level - 1 for other headings
    (h1 -> 0, h2 -> 1, as its HTML partitioner counts)."""
    return 0 if "doc_title" in sec["flags"] else max(0, int(sec["level"] or 1) - 1)


def unstructured_elements(tree: SectionTree, filename: PathLike | None = None) -> list[dict[str, Any]]:
    """See `SectionTree.to_unstructured_elements`."""
    ext = tree.extraction
    pages = {p.n: p for p in ext.pages} if ext is not None else {}
    directory, name = os.path.split(os.fspath(filename)) if filename is not None else ("", "")
    elements: list[dict[str, Any]] = []
    on_page: Counter[int] = Counter()

    def add(kind: str, text: str, page: int, lines: list[Any], parent_id: str | None,
            depth: int | None = None) -> str:
        meta: dict[str, Any] = {}
        if depth is not None:
            meta["category_depth"] = depth
        box = _box(lines, pages)
        if box is not None:
            left, bottom, right, top = box
            height = pages[lines[0].page].height
            y0, y1 = round(height - top, 2), round(height - bottom, 2)  # top-left origin, y down
            meta["coordinates"] = {"points": [[left, y0], [left, y1], [right, y1], [right, y0]], "system": "PixelSpace",
                                   "layout_width": pages[lines[0].page].width, "layout_height": height}
        if directory:
            meta["file_directory"] = directory
        if name:
            meta["filename"] = name
        meta["filetype"] = PDF_MIME
        meta["page_number"] = page
        if parent_id is not None:
            meta["parent_id"] = parent_id
        # Unstructured's own deterministic id (`Element.id_to_hash`): filename, text, page and the
        # element's position on its page.
        seq = on_page[page]
        on_page[page] += 1
        element_id = hashlib.sha256(f"{name or None}{text}{page}{seq}".encode()).hexdigest()[:32]
        elements.append({"type": kind, "element_id": element_id, "text": text, "metadata": meta})
        return element_id

    title_ids: dict[int, str] = {}
    for k, (sec, (head, paras)) in enumerate(zip(tree.sections, _parts(tree), strict=True)):
        own: str | None = None  # this section's Title
        if "front_matter" not in sec["flags"]:
            parent = sec.get("parent")
            own = title_ids[k] = add("Title", heading_text(sec), head[0].page if head else int(sec["page_start"]), head,
                                     title_ids.get(parent) if parent is not None else None, _depth(sec))
        for para in paras:
            add("NarrativeText", para.text, para.lines[0].page, para.lines, own)
    return elements


def _file_hash(path: PathLike) -> str:
    """SHA-256 of the file, as Docling hashes its inputs (`DocumentOrigin.binary_hash`)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def docling_document(tree: SectionTree, filename: PathLike | None = None) -> DoclingDocument:
    """See `SectionTree.to_docling_document`."""
    try:
        from docling_core.types.doc import (
            BoundingBox,
            CoordOrigin,
            DocItemLabel,
            DoclingDocument,
            DocumentOrigin,
            ProvenanceItem,
            Size,
        )
    except ImportError:
        raise ConfigError(DOCLING_EXTRA) from None

    ext = tree.extraction
    pages = {p.n: p for p in ext.pages} if ext is not None else {}
    doc = DoclingDocument(name=Path(os.fspath(filename)).stem if filename is not None else "document")
    if filename is not None and os.path.isfile(filename):
        doc.origin = DocumentOrigin(mimetype=PDF_MIME, filename=Path(os.fspath(filename)).name,
                                    binary_hash=_file_hash(filename))
    for pg in pages.values():
        doc.add_page(page_no=pg.n, size=Size(width=pg.width, height=pg.height))

    def prov(lines: list[Any], span: tuple[int, int]) -> ProvenanceItem | None:
        box = _box(lines, pages)
        if box is None:
            return None
        left, bottom, right, top = box
        return ProvenanceItem(page_no=lines[0].page, charspan=span,
                              bbox=BoundingBox(l=left, t=top, r=right, b=bottom, coord_origin=CoordOrigin.BOTTOMLEFT))

    def para_provs(para: Paragraph) -> list[ProvenanceItem]:
        """One per page the paragraph's lines are on, with the characters of `para.text` there."""
        out = []
        for _page, run in groupby(range(len(para.lines)), key=lambda i: para.lines[i].page):
            idx = list(run)
            a, b = idx[0], idx[-1]
            end = para.offsets[b] + len(para.lines[b].text.strip())
            if b + 1 < len(para.lines):
                end = min(end, para.offsets[b + 1])  # a hyphen removed at the line end
            p = prov([para.lines[i] for i in idx], (para.offsets[a], min(end, len(para.text))))
            if p is not None:
                out.append(p)
        return out

    nodes: dict[int, Any] = {}
    for k, (sec, (head, paras)) in enumerate(zip(tree.sections, _parts(tree), strict=True)):
        own = None  # this section's heading item; front matter stays at the top level
        if "front_matter" not in sec["flags"]:
            text = heading_text(sec)
            p = prov(head, (0, len(text)))
            if "doc_title" in sec["flags"]:
                own = doc.add_text(label=DocItemLabel.TITLE, text=text, prov=p)
            else:
                parent = sec.get("parent")
                own = doc.add_heading(text=text, level=min(100, max(1, int(sec["level"] or 1))), prov=p,
                                      parent=nodes.get(parent) if parent is not None else None)
            nodes[k] = own
        for para in paras:
            provs = para_provs(para)
            item = doc.add_text(label=DocItemLabel.TEXT, text=para.text, prov=provs[0] if provs else None, parent=own)
            item.prov.extend(provs[1:])
    return doc
