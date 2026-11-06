"""Possible missed headings: lines with heading evidence that the result does not have as headings.

`SectionTree.possible_misses` lists them, best first, so that a reader can check the few lines most
likely to be headings the result left out instead of the whole document. Two kinds:

- contents entries the contents check could not find in the body (`contents_check`), and
- heading-like lines (Free's loose candidates: set larger or bold, numbered, a structural label, or
  a heading in Docling's hints) that no section starts at, scored from their evidence: the number
  fits a gap in the result's own numbering, the style is the style of the result's headings, a
  structural label, and so on.

Each entry has the page, the text, the evidence in words and a score from 0 to 1. The weights were
fitted on development documents only (research finding F057); read the score as a ranking, not as
a probability. The list keeps entries scoring at least `MIN_SCORE`, at most one per `PAGES_PER_ENTRY`
pages (and at least `MIN_ENTRIES`). On the development documents that list held about 5% of the
headings Free missed, or 22% with Docling's hints, at fewer than one wrong entry per 10 pages: most
missed headings are set like body text and carry no evidence this list can use.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from section_anything.confidence import _in_sequence, _numbers
from section_anything.contents_check import Entry, _label_key
from section_anything.docling_input import hints_of
from section_anything.extract import Extraction
from section_anything.strategies.rules import CAPTION, NUMBERING, _merge_wrapped, candidates, side_notes
from section_anything.structure import furniture_of, toc_of

# Fitted on the F042 development split (47 documents, with and without bookmarks, Free and Free with
# Docling hints; research finding F057). Several features overlap, so read single weights with care.
INTERCEPT = -4.64
WEIGHTS = {
    "candidate": -0.43,  # one of Free's loose candidates (else a short line set apart from the text above)
    "strict": 1.63,  # a candidate in Free's strict sense too
    "label": 0.73,  # a structural label with a number ("Article 5", "PART 2")
    "numbered": 0.46,
    "fills_gap": 0.85,  # its number fits between the result's neighbouring numbered headings, which skip it
    "in_sequence": 0.81,  # its number can follow the previous numbered heading
    "heading_style": 0.46,  # set like two or more of the result's headings
    "style_share": 2.65,  # share of the lines in its style that are headings of the result
    "larger": 1.33,  # set larger than body text
    "bold": 1.11,
    "docling": 0.67,  # Docling's hints label it a heading
    "long": -1.92,  # more than ten words
    "bookmarked": -0.95,  # the PDF has bookmarks, and they do not list it
    "space_above": 0.84,  # set apart from the line above (or first on its page)
    "caps": -0.45,  # all capitals
    "short": -0.43,  # five words or fewer
    "sentence": -1.16,  # ends with a full stop, a comma, a colon or a semicolon
    "long_gap": 0.28,  # two or more pages since the previous heading
}
STANDALONE_WORDS = 12
ENTRY_SCORE = 0.1  # unresolved contents entries: on development documents they were rarely real misses
MIN_SCORE = 0.1
# After a model mode, the lines the model chose not to list are often bold or numbered on purpose (a
# list, a defined term), so only stronger evidence is listed (set on development Quick runs).
MIN_SCORE_MODEL = 0.4
PAGES_PER_ENTRY = 5
MIN_ENTRIES = 3

EVIDENCE = {
    "strict": "taken by Free's heading rules",
    "label": "a structural label with a number",
    "fills_gap": "its number fills a gap in the headings' numbering",
    "in_sequence": "its number follows the previous heading's",
    "heading_style": "set like other headings",
    "larger": "larger than body text",
    "bold": "bold",
    "docling": "Docling labels it a heading",
    "space_above": "set apart from the text above",
    "long_gap": "two or more pages after the previous heading",
}
ENTRY_EVIDENCE = {
    "bookmarks": "listed in the PDF's bookmarks, not found in the text",
    "contents": "listed in the table of contents, not found in the text",
    "contents list": "listed in a contents list, not found in the text",
}


def features(sections: list[dict], ext: Extraction) -> list[dict[str, Any]]:
    """Heading-like lines no section starts at, each with its line, page, text and the evidence
    `WEIGHTS` scores."""
    if not ext.lines:
        return []
    lines = ext.lines
    body = [s for s in sections if "front_matter" not in s["flags"] and 0 <= s.get("first_line", -1) < len(lines)]
    starts = sorted(s["first_line"] for s in body)
    hints = hints_of(ext)
    side = side_notes(ext)
    strict = {ln.i for ln, _ in candidates(ext)}
    loose = _merge_wrapped(candidates(ext, loose=True), hints, side, ext)
    size = ext.body_size()
    furniture = furniture_of(ext)
    style_lines = Counter((ln.size, ln.bold) for ln in lines if ln.i not in furniture)
    style_heads = Counter((lines[s["first_line"]].size, lines[s["first_line"]].bold) for s in body)
    above = _space_above(ext)
    numbered = [(s["first_line"], _numbers(s.get("number") or "")) for s in body]
    numbered = [(i, n) for i, n in numbered if n is not None]
    # Short lines set apart from the text above them, which no candidate rule took, join the pool.
    taken = {x.i for ln, _, text in loose for x in lines[ln.i:ln.i + text.count("\n") + 1]}
    skip = furniture | toc_of(ext).lines | side | taken
    pool = list(loose) + [
        (ln, (m.group("num").strip() if (m := NUMBERING.match(ln.text)) else ""), ln.text) for ln in lines
        if ln.i in above and ln.i not in skip and len(ln.text.split()) <= STANDALONE_WORDS
        and len(re.findall(r"[^\W\d_]", ln.text)) >= 3 and not CAPTION.match(ln.text)
    ]
    loose_lines = {ln.i for ln, _, _ in loose}
    out = []
    for ln, num, text in pool:
        last = ln.i + text.count("\n")
        if any(ln.i - 1 <= i <= last + 1 for i in starts[_lo(starts, ln.i - 1):_lo(starts, last + 2)]):
            continue
        cur = _numbers(num)
        prev = next((n for i, n in reversed(numbered) if i < ln.i), None)
        nxt = next((n for i, n in numbered if i > last), None)
        in_seq = cur is not None and _in_sequence(prev, cur)
        fills = (cur is not None and prev is not None and nxt is not None and in_seq and _in_sequence(cur, nxt)
                 and not _in_sequence(prev, nxt))
        style = (ln.size, ln.bold)
        flat = " ".join(text.split())
        k = _lo(starts, ln.i) - 1
        since = ln.page - lines[starts[k]].page if k >= 0 else ln.page - 1
        letters = [c for c in flat if c.isalpha()]
        out.append({
            "line": ln.i, "page": ln.page, "text": flat,
            "f": {
                "candidate": float(ln.i in loose_lines),
                "strict": float(ln.i in strict),
                "label": float(_label_key(flat) is not None),
                "numbered": float(bool(num)),
                "fills_gap": float(fills),
                "in_sequence": float(in_seq),
                "heading_style": float(style_heads[style] >= 2),
                "style_share": min(1.0, style_heads[style] / max(1, style_lines[style])),
                "larger": float(ln.size >= size + 0.8),
                "bold": float(ln.bold),
                "docling": float(hints is not None and ln.i in hints.headers),
                "long": float(len(flat.split()) > 10),
                "bookmarked": float(len(ext.outline) >= 3),
                "space_above": float(ln.i in above),
                "caps": float(bool(letters) and all(c.isupper() for c in letters)),
                "short": float(len(flat.split()) <= 5),
                "sentence": float(flat.endswith((".", ",", ":", ";")) and not (num and flat == num)),
                "long_gap": float(since >= 2),
            },
        })
    return out


def _space_above(ext: Extraction) -> set[int]:
    """Lines set apart from the line above them on their page by at least their own height, and the
    first line of each page."""
    out, prev = set(), None
    for ln in ext.lines:
        if prev is None or prev.page != ln.page or prev.y0 - ln.y1 >= ln.size:
            out.add(ln.i)
        prev = ln
    return out


def _lo(xs: list[int], v: int) -> int:
    import bisect

    return bisect.bisect_left(xs, v)


def _score(f: dict[str, float]) -> float:
    z = INTERCEPT + sum(WEIGHTS[k] * v for k, v in f.items())
    return 1 / (1 + math.exp(-z))


def possible_misses(sections: list[dict], ext: Extraction, unresolved: list[Entry] | None = None,
                    model: bool = False) -> list[dict]:
    """The lines most likely to be headings the result left out, best first, then the contents
    entries not found: page (None when such an entry gives none), text, evidence and score. `model`:
    the result came from a model mode (`MIN_SCORE_MODEL`)."""
    floor = MIN_SCORE_MODEL if model else MIN_SCORE
    out = []
    for c in features(sections, ext):
        sc = _score(c["f"])
        if sc >= floor:
            out.append({"page": c["page"], "text": c["text"], "evidence": [EVIDENCE[k] for k in EVIDENCE if c["f"][k]],
                        "score": round(sc, 3)})
    out.sort(key=lambda x: -x["score"])
    out += [{"page": e.page, "text": e.text, "evidence": [ENTRY_EVIDENCE[e.source]], "score": ENTRY_SCORE}
            for e in unresolved or []]
    keep = max(MIN_ENTRIES, len(ext.pages) // PAGES_PER_ENTRY)
    return out[:keep]
