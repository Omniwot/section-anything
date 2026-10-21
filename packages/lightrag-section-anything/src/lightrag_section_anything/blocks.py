"""Section Anything sections -> LightRAG sidecar blocks.

One block per section: the heading line (``#`` x level + printed heading), then the section's
body reflowed into paragraphs (LightRAG's heading chunker treats every line as a paragraph, so
PDF lines must be joined). ``parent_headings`` holds ancestors only, from a level-keyed stack.
Text before the first heading is a ``preface`` block. Running headers and footers are dropped.
Positions: one bbox per page, PDF points with the origin at the bottom left.
"""

from __future__ import annotations

import re
import statistics
from typing import Any

SENTENCE_END = re.compile(r"[.!?:;)\]\"”']$")


def _reflow(lines: list[Any]) -> list[str]:
    """Join PDF lines into paragraphs: break on a vertical gap, a page change, or a short line that
    ends a sentence; undo end-of-line hyphenation."""
    if not lines:
        return []
    widths = [ln.x1 - ln.x0 for ln in lines if ln.text.strip()]
    full = statistics.median(widths) if widths else 0.0
    paras: list[str] = []
    cur = ""
    prev = None
    for ln in lines:
        text = ln.text.strip()
        if not text:
            continue
        if prev is not None:
            gap = prev.y0 - ln.y1  # PDF space: y grows upwards
            new_par = (
                ln.page != prev.page and SENTENCE_END.search(cur or "")
                or (ln.page == prev.page and gap > 0.9 * max(prev.size, 1.0))
                or (SENTENCE_END.search(cur) and (prev.x1 - prev.x0) < 0.8 * full)
            )
            if new_par:
                paras.append(cur)
                cur = text
            elif cur.endswith("-") and text[:1].islower():
                cur = cur[:-1] + text
            else:
                cur = f"{cur} {text}"
        else:
            cur = text
        prev = ln
    if cur:
        paras.append(cur)
    return paras


def _positions(lines: list[Any]) -> list[dict]:
    pages: dict[int, list[float]] = {}
    for ln in lines:
        b = pages.setdefault(ln.page, [ln.x0, ln.y1, ln.x1, ln.y0])
        b[0], b[1], b[2], b[3] = min(b[0], ln.x0), max(b[1], ln.y1), max(b[2], ln.x1), min(b[3], ln.y0)
    return [{"type": "bbox", "anchor": str(p), "range": [round(v, 2) for v in r]} for p, r in sorted(pages.items())]


def _key(text: str) -> str:
    return re.sub(r"\W+", "", text.lower())


def _heading_lines(seg: list[Any], head: str) -> int:
    """How many leading lines of a section print its heading (headings may wrap). A run-in heading
    (body text continues on the same line) keeps its line in the body: 0."""
    hk, acc = _key(head), ""
    for n, ln in enumerate(seg[:4], start=1):
        acc += _key(ln.text)
        if acc.startswith(hk):
            return n if len(acc) - len(hk) <= 3 else n - 1
        if not hk.startswith(acc):
            return 1 if n == 1 else n - 1  # heading text differs (cleaned by the model): drop its first line
    return 1


def heading_text(sec: dict) -> str:
    return " ".join(f"{sec.get('number') or ''} {sec.get('title') or ''}".split())


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
