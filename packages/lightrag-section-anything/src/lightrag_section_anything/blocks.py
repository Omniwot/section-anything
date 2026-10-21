"""Section Anything sections -> LightRAG sidecar blocks.

One block per section: the heading line (``#`` x level + printed heading), then the section's
body reflowed into paragraphs (LightRAG's heading chunker treats every line as a paragraph, so
PDF lines must be joined). ``parent_headings`` holds ancestors only, from a level-keyed stack.
Text before the first heading is a ``preface`` block. Running headers and footers are dropped.
Positions: one bbox per page, PDF points with the origin at the bottom left.
"""

from __future__ import annotations

from typing import Any

# Paragraph reflow, heading-line detection and heading text are shared with the library's
# Markdown export.
from section_anything.export import heading_lines as _heading_lines
from section_anything.export import heading_text
from section_anything.export import reflow as _reflow

__all__ = ["build_blocks", "heading_text"]


def _positions(lines: list[Any]) -> list[dict]:
    pages: dict[int, list[float]] = {}
    for ln in lines:
        b = pages.setdefault(ln.page, [ln.x0, ln.y1, ln.x1, ln.y0])
        b[0], b[1], b[2], b[3] = min(b[0], ln.x0), max(b[1], ln.y1), max(b[2], ln.x1), min(b[3], ln.y0)
    return [{"type": "bbox", "anchor": str(p), "range": [round(v, 2) for v in r]} for p, r in sorted(pages.items())]


def build_blocks(ext: Any, sections: list[dict], furniture: set[int] | None = None,
                 synthetic_titles: bool = False) -> tuple[list[dict], str]:
    """Returns (blocks, document title). Each block: content, heading, level, parent_headings,
    session_type, is_title_block, positions."""
    from lightrag.parser._markdown import render_heading_line

    furniture = furniture or set()
    lines = ext.lines
    body = [s for s in sections if "front_matter" not in s.get("flags", [])]
    if not synthetic_titles:  # headings the model invented for headingless text: fold into the previous block
        body = [s for s in body if s.get("title_from_text", True) is not False]
    body.sort(key=lambda s: s["first_line"])
    doc_title = next((heading_text(s) for s in body if "doc_title" in s.get("flags", [])), "")

    starts = [s["first_line"] for s in body]
    blocks: list[dict] = []

    def span(a: int, b: int) -> list[Any]:
        return [ln for ln in lines[a:b] if ln.i not in furniture]

    first = starts[0] if starts else len(lines)
    pre = span(0, first)
    if any(ln.text.strip() for ln in pre):
        blocks.append({"content": "\n".join(_reflow(pre)), "heading": "", "level": 0, "parent_headings": [],
                       "session_type": "preface", "is_title_block": False, "positions": _positions(pre)})

    stack: list[tuple[int, str]] = []
    for k, sec in enumerate(body):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        seg = span(sec["first_line"], end)
        head = heading_text(sec)
        is_title = "doc_title" in sec.get("flags", [])
        level = 0 if is_title else max(1, int(sec["level"]))
        n_head = _heading_lines(seg, head)
        if not is_title:
            stack = [(lv, h) for lv, h in stack if lv < level]
        parents = [h for _lv, h in stack]
        heading_line = render_heading_line(max(level, 1), head)
        paras = _reflow(seg[n_head:])
        blocks.append({"content": "\n".join([heading_line, *paras]), "heading": head, "level": level,
                       "parent_headings": parents, "session_type": "body", "is_title_block": is_title,
                       "positions": _positions(seg)})
        if not is_title:
            stack.append((level, head))
    return blocks, doc_title
