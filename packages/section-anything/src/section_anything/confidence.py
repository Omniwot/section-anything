"""How sure Free mode is of each heading it found, from evidence it already has. No model.

Each Free section gets ``confidence``, from 0 to 1: a logistic score over

- the PDF's own outline: the heading is an entry Free took from the bookmarks or printed contents,
  or a bookmark names it;
- its style: used on two or more pages, and used for little else (the share of the document's lines
  in that font size and weight that are headings);
- numbering that follows the previous numbered heading ("2.3" after "2.2" or "2");
- a standard heading name (Abstract, References, Appendix, ...);
- against it: more than ten words, or a start the pipeline could not anchor exactly.

The weights were fitted on development documents only (200 READoc arXiv papers and READMEs and 21
public corpus documents of other genres, research finding F044), so the score ranks headings well
on papers and READMEs and less well elsewhere. Read it as relative evidence, not as a probability.

Mode "auto" escalates a document to Quick check when Free found fewer than three headings or their
mean confidence is below `Settings.auto_threshold`.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from section_anything.extract import Extraction
from section_anything.outline_check import heading_text, is_standard_heading, match_bookmarks
from section_anything.structure import furniture_of, outline_backbone

INTERCEPT = -1.81
WEIGHTS = {"outline": 0.82, "bookmark": 1.59, "in_sequence": 0.52, "multi_page_style": 1.70, "style_share": 1.38,
           "long": -1.80, "standard": 2.84, "anchor_flag": 0.12}
ANCHOR_FLAGS = ("start_marker_fuzzy", "start_marker_not_found", "title_not_in_text")
MIN_HEADINGS = 3  # fewer, and Free has found too little to be sure of
DOTTED = re.compile(r"^\d+(?:\.\d+)*\.?$")


def _numbers(num: str) -> tuple[int, ...] | None:
    num = num.strip()
    return tuple(int(x) for x in num.rstrip(".").split(".")) if DOTTED.match(num) else None


def _in_sequence(prev: tuple[int, ...] | None, cur: tuple[int, ...]) -> bool:
    """`cur` can follow `prev`: a first subsection, the next sibling, or the next one higher up.
    The first numbered heading must start low ("1", "1.1", "2")."""
    if prev is None:
        return cur[0] <= 2 and all(x in (0, 1) for x in cur[1:])
    if cur in (prev + (1,), prev + (0,)):
        return True
    return any(cur == prev[:d - 1] + (prev[d - 1] + 1,) for d in range(1, len(prev) + 1))


def _outline_lines(ext: Extraction) -> set[int]:
    derived = getattr(ext, "derived", None)
    items, _source = derived("outline_backbone", outline_backbone) if derived is not None else outline_backbone(ext)
    return {a.line for a in items} | {a.line - 1 for a in items}  # the number may sit on the line before


def evidence(sections: list[dict], ext: Extraction) -> list[dict[str, float] | None]:
    """Per section, the evidence `WEIGHTS` scores (None for front matter)."""
    lines = ext.lines
    outline = _outline_lines(ext)
    body = [s for s in sections if "front_matter" not in s["flags"]]
    bookmarked = {id(body[k]) for k in match_bookmarks(body, ext)} if ext.outline else set()
    furniture = furniture_of(ext)
    style_lines = Counter((ln.size, ln.bold) for ln in lines if ln.i not in furniture)
    style_of = {id(s): (lines[s["first_line"]].size, lines[s["first_line"]].bold) for s in body}
    style_heads = Counter(style_of.values())
    style_pages: dict[tuple[float, bool], set[int]] = {}
    for s in body:
        style_pages.setdefault(style_of[id(s)], set()).add(s["page_start"])

    out: list[dict[str, float] | None] = []
    prev: tuple[int, ...] | None = None
    for s in sections:
        if "front_matter" in s["flags"]:
            out.append(None)
            continue
        style, text = style_of[id(s)], heading_text(s)
        nums = _numbers(s.get("number") or "")
        in_sequence = nums is not None and _in_sequence(prev, nums)
        prev = nums if nums is not None else prev
        out.append({
            "outline": float(s["first_line"] in outline),
            "bookmark": float(id(s) in bookmarked),
            "in_sequence": float(in_sequence),
            "multi_page_style": float(len(style_pages[style]) >= 2),
            "style_share": min(1.0, style_heads[style] / max(1, style_lines[style])),
            "long": float(len(text.split()) > 10),
            "standard": float(is_standard_heading(text)),
            "anchor_flag": float(any(f in s["flags"] for f in ANCHOR_FLAGS)),
        })
    return out


def annotate(sections: list[dict], ext: Extraction) -> None:
    """Set each section's ``confidence`` (None for front matter)."""
    for s, ev in zip(sections, evidence(sections, ext), strict=True):
        z = INTERCEPT + sum(WEIGHTS[k] * v for k, v in ev.items()) if ev is not None else None
        s["confidence"] = round(1 / (1 + math.exp(-z)), 3) if z is not None else None


def document_confidence(sections: list[dict]) -> float:
    """Mean confidence of the headings, leaving out the document title and front matter; 0 when
    there are fewer than `MIN_HEADINGS`."""
    scores = [s["confidence"] for s in sections
              if s.get("confidence") is not None and "doc_title" not in s["flags"]]
    return round(sum(scores) / len(scores), 3) if len(scores) >= MIN_HEADINGS else 0.0
