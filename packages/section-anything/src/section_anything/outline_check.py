"""Demote headings that a complete PDF outline does not list.

Many PDFs carry bookmarks generated from their own headings (LaTeX's hyperref, Markdown and
word-processor exports). When that outline looks complete, a detected heading it does not list
is most likely not a heading: a bold label, an author line, the first line of a paragraph. This
step drops such sections after a strategy has run; their text joins the section before them.

The idea comes from Docling's ``demote_unmatched_headings`` option (docling#5002). The step acts
only when the outline looks complete:

- the outline has more than one level (a flat outline usually lists only the top level);
- every dotted-numbered section ("2.1 ...") matches a bookmark;
- at least half of the bookmarks match a section (the outline describes this document).

``strict`` adds Docling's two other checks, used for sections a model chose (Quick check,
Standard), where a missing bookmark is weaker evidence against a heading:

- at least half of the sections match a bookmark;
- no two of the sections to drop share a style (font size within 5%, and weight). A family of
  unlisted headings in one style means the outline leaves out a level. Docling counts only
  heading-like styles; this extraction has no font face, so every style counts.

Free's extra sections come from typography rules and are often body lines, so for Free those two
checks would measure the rules' noise rather than the outline; it runs without them.

A section whose number belongs to a bookmark that matched nothing counts as matched (the bookmark
title can differ from the printed one). Standard unnumbered headings (Abstract, References, ...,
also letter-spaced), the flagged document title and the front matter are always kept.

A section matches a bookmark when its title (with or without its number) or its first line is
similar to the bookmark title (0.8, or one contains the other), on the bookmark's page or the
page after. Each bookmark matches at most one section.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from section_anything.extract import Extraction, Line, OutlineItem
from section_anything.markers import canon

MATCH_THRESHOLD = 0.8  # title similarity (0..1) for a section to match a bookmark
CONTAINED_SCORE = 0.92  # one title contains the other (bookmarks are often truncated)
COMPLETE_SHARE = 0.5  # share that must match for the outline to count as complete
SIZE_TOLERANCE = 0.05  # relative size difference treated as the same size

# Unnumbered headings that documents commonly leave out of their bookmarks. Never demoted.
STANDARD_HEADING = re.compile(
    r"^(abstract|keywords|acknowledge?ments?|references|bibliography|appendix|appendices)\b", re.I
)
# A word set with letter spacing, such as "A B S T R A C T": three or more single letters.
LETTER_SPACED = re.compile(r"^\s*(?:[^\W\d_]\s+){2,}[^\W\d_]\s*$")
# The section number at the start of a heading or bookmark title: 4, 4., 2.1, IV., A.
SECTION_NUMBER = re.compile(r"^\s*\(?(\d+(?:\.\d+)*|[IVXLC]+(?=[.)\s])|[A-Z](?=[.)]))[.)]?(?=\s|$)")
# Dotted decimal numbering (2.1, 2.1.3).
DOTTED = re.compile(r"^\(?\s*\d+(?:\.\d+)+(?:[.)\]\s:\-\u2013\u2014]|$)")
# Leading numbering stripped before comparing titles, so "Definitions" matches "1.1 Definitions".
LEADING_MARKER = re.compile(
    r"^\s*(?:"
    r"(?:part|title|book|division|subdivision|chapter|article|section|clause|schedule|annex|appendix|rule)"
    r"\b[\s.:]*[0-9ivxlcdm]*"
    r"|§+\s*[0-9.]+"
    r"|\(?[0-9]+(?:\.[0-9]+)*[.)\]]?"
    r"|\(?[A-Za-z]{1,2}(?:[.)\]]|(?=\s*[:\-\u2013\u2014]))"
    r")[\s.:)\-\u2013\u2014]*",
    re.I,
)


@dataclass
class OutlineCheck:
    """What the step did: the sections to keep, the ones demoted, and ``reason``: "demoted", or
    why nothing was."""

    sections: list[dict]
    demoted: list[dict] = field(default_factory=list)
    reason: str = "demoted"
    headings: int = 0
    matched: int = 0

    def summary(self) -> dict:
        return {"reason": self.reason, "headings": self.headings, "matched": self.matched,
                "demoted": len(self.demoted)}


def heading_text(sec: dict) -> str:
    return f"{sec.get('number') or ''} {sec.get('title') or ''}".strip()


def _variants(text: str) -> set[str]:
    return {canon(text), canon(LEADING_MARKER.sub("", text, count=1))} - {""}


def _similarity(a: set[str], b: set[str]) -> float:
    best = 0.0
    for x in a:
        for y in b:
            best = max(best, fuzz.ratio(x, y) / 100)
            if len(x) >= 4 and len(y) >= 4 and (x in y or y in x):
                best = max(best, CONTAINED_SCORE)
    return best


def section_number(text: str) -> str | None:
    m = SECTION_NUMBER.match(text or "")
    return m.group(1).upper() if m else None


def is_standard_heading(text: str) -> bool:
    unspaced = re.sub(r"\s+", "", text) if LETTER_SPACED.match(text) else text
    return any(STANDARD_HEADING.match(canon(v)) for v in (text, LEADING_MARKER.sub("", text, count=1), unspaced))


def _always_kept(sec: dict) -> bool:
    return "doc_title" in (sec.get("flags") or []) or is_standard_heading(heading_text(sec))


def _first_line(sec: dict, ext: Extraction) -> Line | None:
    k = sec.get("first_line")
    return ext.lines[k] if isinstance(k, int) and 0 <= k < len(ext.lines) else None


def match_bookmarks(body: list[dict], ext: Extraction) -> dict[int, OutlineItem]:
    """Section index (into ``body``) -> the bookmark it matches. Bookmarks are taken in outline
    order; each claims the most similar unclaimed section on its page (else the next page),
    nearest to the bookmark's position on a tie."""
    variants = []
    for sec in body:
        v = _variants(heading_text(sec)) | _variants(sec.get("title") or "")
        ln = _first_line(sec, ext)
        if ln is not None:
            v |= _variants(ln.text)
        variants.append(v)
    by_page: dict[int, list[int]] = {}
    for k, sec in enumerate(body):
        by_page.setdefault(int(sec.get("page_start") or 0), []).append(k)

    claimed: dict[int, OutlineItem] = {}
    for bm in ext.outline:
        want = _variants(bm.title)
        if not want:
            continue
        for page in (bm.page, bm.page + 1):
            best: tuple[float, float, int] | None = None
            for k in by_page.get(page, []):
                if k in claimed:
                    continue
                score = _similarity(variants[k], want)
                if score < MATCH_THRESHOLD:
                    continue
                ln = _first_line(body[k], ext)
                dist = abs(ln.y1 - bm.y) if (ln is not None and bm.y is not None) else float("inf")
                key = (-score, dist, k)
                if best is None or key < best:
                    best = key
            if best is not None:
                claimed[best[2]] = bm
                break
    return claimed


def _size_clusters(sizes: set[float]) -> dict[float, int]:
    out: dict[float, int] = {}
    index, prev = 0, None
    for size in sorted(sizes, reverse=True):
        if prev is not None and (prev - size) > SIZE_TOLERANCE * prev:
            index += 1
        out[size] = index
        prev = size
    return out


def share_a_style(secs: list[dict], ext: Extraction) -> bool:
    """Whether two or more of ``secs`` start on lines of the same style: font size (within
    ``SIZE_TOLERANCE``) and weight."""
    keys = [(ln.size, ln.bold) for ln in (_first_line(s, ext) for s in secs) if ln is not None]
    clusters = _size_clusters({size for size, _ in keys})
    styles = [(clusters[size], bold) for size, bold in keys]
    return len(set(styles)) < len(styles)


def rebound(sections: list[dict], ext: Extraction) -> list[dict]:
    """Recompute ids, ends and spans after sections were removed: a section's own text runs to
    the next section, its span to the next section at the same or a higher level. A model's end
    marker is checked again against the new boundaries."""
    text, lines, n = ext.text, ext.lines, len(ext.text)
    starts = [ln.start for ln in lines]
    out = []
    for k, sec in enumerate(sections):
        s = dict(sec, flags=list(sec.get("flags") or []))
        start = s["start"]
        seg_end = sections[k + 1]["start"] if k + 1 < len(sections) else n
        span_end = next((t["start"] for t in sections[k + 1:] if t["level"] <= s["level"]), n)
        seg_end_trim = seg_end - 1 if seg_end > start and text[seg_end - 1:seg_end] == "\n" else seg_end
        s.update(id=k, end=seg_end_trim, span_end=span_end)
        if lines:
            last = max(0, bisect.bisect_right(starts, max(start, seg_end_trim - 1)) - 1)
            s.update(last_line=last, page_end=lines[last].page)
        if s.get("model_end") is not None:
            target = min((seg_end_trim, span_end), key=lambda t: abs(t - s["model_end"]))
            gap = target - s["model_end"]
            s["end_agrees"] = -50 <= gap <= max(1500, int(0.1 * (span_end - start)))
            s["flags"] = [f for f in s["flags"] if f != "end_mismatch"] + ([] if s["end_agrees"] else ["end_mismatch"])
        out.append(s)
    return out


def demote_unlisted_headings(sections: list[dict], ext: Extraction, *, strict: bool = True) -> OutlineCheck:
    """Drop sections whose titles match no bookmark, when the PDF outline looks complete.
    ``strict`` adds the section-share and shared-style checks (see the module docstring).
    Returns the sections to keep (re-bounded) and what was dropped; ``sections`` is not changed."""
    body = [s for s in sections if "front_matter" not in (s.get("flags") or [])]
    result = OutlineCheck(sections=sections, headings=len(body))
    bookmarks = [bm for bm in ext.outline if _variants(bm.title)]
    if not bookmarks:
        result.reason = "no outline"
        return result
    matched = match_bookmarks(body, ext)
    result.matched = len(matched)
    matched_numbers = {section_number(heading_text(body[k])) for k in matched}
    free_numbers = {
        num for bm in bookmarks
        if (num := section_number(bm.title)) is not None and num not in matched_numbers
    }
    unmatched = [s for k, s in enumerate(body) if k not in matched and section_number(heading_text(s)) not in free_numbers]
    demotable = [s for s in unmatched if not _always_kept(s)]
    if not demotable:
        result.reason = "nothing to demote"
    elif len({bm.level for bm in bookmarks}) < 2:
        result.reason = "flat outline"
    elif any(DOTTED.match(heading_text(s)) for s in unmatched):
        result.reason = "unmatched numbered heading"
    elif len(matched) < COMPLETE_SHARE * len(bookmarks):
        result.reason = "outline not found"
    elif strict and len(body) - len(unmatched) < COMPLETE_SHARE * len(body):
        result.reason = "under half matched"
    elif strict and share_a_style(demotable, ext):
        result.reason = "shared style"
    else:
        drop = {id(s) for s in demotable}
        kept = [s for s in sections if id(s) not in drop]
        if id(sections[0]) in drop:
            # The first section was dropped: its text before the next heading becomes the front
            # matter, as text before the first heading always does.
            kept.insert(0, dict(sections[0], number="", title="Front matter", title_from_text=False,
                                level=min(s["level"] for s in sections), start_marker="", end_marker="",
                                end_marker_found=None, model_end=None, end_agrees=None,
                                title_verified=None, flags=["front_matter"]))
        result.sections = rebound(kept, ext)
        result.demoted = demotable
    return result
