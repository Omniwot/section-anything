"""Text helpers for exports: heading text, heading lines and paragraph reflow.

PDF text arrives as lines. `reflow` joins them into paragraphs (breaking on vertical gaps, page
changes and short sentence-ending lines, and undoing end-of-line hyphenation). `heading_lines`
tells how many leading lines of a section print its heading, so a body export does not repeat it.
"""

from __future__ import annotations

import re
import statistics
from typing import Any

SENTENCE_END = re.compile(r"[.!?:;)\]\"”']$")


def heading_text(sec: dict) -> str:
    """Number and title as one line ("2.3 Cell Cycle")."""
    return " ".join(f"{sec.get('number') or ''} {sec.get('title') or ''}".split())


def markdown_hashes(sec: dict) -> str:
    """'#' for the document title, '#' x (level + 1) for other headings, at most six."""
    if "doc_title" in (sec.get("flags") or []):
        return "#"
    return "#" * max(1, min(6, int(sec.get("level") or 1) + 1))


def reflow(lines: list[Any]) -> list[str]:
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


def _key(text: str) -> str:
    return re.sub(r"\W+", "", text.lower())


def heading_lines(seg: list[Any], head: str) -> int:
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


def section_bodies(ext: Any, sections: list[dict], furniture: set[int] | None = None) -> list[list[str]]:
    """Body paragraphs per section (heading lines and running headers/footers removed). Sections
    must be the resolved dicts (with `first_line`), in document order."""
    furniture = furniture or set()
    lines = ext.lines
    starts = [s["first_line"] for s in sections]
    out: list[list[str]] = []
    for k, sec in enumerate(sections):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        seg = [ln for ln in lines[sec["first_line"]:end] if ln.i not in furniture]
        skip = 0 if "front_matter" in (sec.get("flags") or []) else heading_lines(seg, heading_text(sec))
        out.append(reflow(seg[skip:]))
    return out
