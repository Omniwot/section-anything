"""Document structure every strategy shares: tables of contents and furniture.

A table of contents repeats the headings it lists, so without this module the
rules strategy counts TOC lines as headings and a model-quoted marker can land
on the TOC copy instead of the body. Two kinds of TOC are found:

- Page-number lists: runs of short lines ending in a page number, usually
  with dot leaders ("2.3 Mitosis ........ 41").
- Titled lists: a "Contents" / "Chapter outline" / "In this chapter" line
  followed by a run of entry lines in one style ("10.1 Cell Division",
  "10.2 The Cell Cycle"). The run stops at the first line that breaks the
  entries' pattern, a large vertical gap, or a page break.

Entries keep their number, title, printed page and indent, so the free
strategy can use a TOC as an outline. `outline_backbone` anchors either the
PDF's bookmarks or the TOC entries to the body lines they name.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from app.sectioning.extract import Extraction, Line
from app.sectioning.markers import canon

TOC_TITLE = re.compile(
    r"^(table of contents|contents|contents at a glance|brief contents|chapter outline|outline|in this chapter"
    r"|chapter contents|summary of contents)\s*:?$",
    re.I,
)
# "Title .... 12", "Title . . . 12", "Title … 12", "Title   12"
PAGE_REF = re.compile(r"^(?P<body>.*?\S)\s*(?P<lead>(?:\.\s?){2,}|…+|·{2,}|_{2,})?\s*(?P<page>\d{1,4}|[ivxlc]{1,7})$", re.I)
NUMBER = re.compile(
    r"^(?P<num>(?:chapter|part|section|appendix|annex|unit|lesson|module)\s+[\dA-Z]+[.:]?"
    r"|\d+(?:\.\d+)*\.?|[IVXLC]+\.|[A-Z]\.)\s+(?=\S)",
    re.I,
)


@dataclass
class TocEntry:
    line: int
    number: str
    title: str
    page_label: str | None
    x0: float
    level: int = 1


@dataclass
class Toc:
    lines: set[int] = field(default_factory=set)
    entries: list[TocEntry] = field(default_factory=list)
    spans: list[tuple[int, int]] = field(default_factory=list)  # char ranges in Extraction.text

    def contains(self, pos: int) -> bool:
        return any(a <= pos < b for a, b in self.spans)


def _depth(num: str) -> int:
    n = num.rstrip(".:").strip()
    if re.fullmatch(r"\d+(?:\.\d+)*", n):
        return n.count(".") + 1
    return 1


def _entry(ln: Line, page_ref: bool) -> TocEntry:
    text = ln.text
    page = None
    if page_ref:
        m = PAGE_REF.match(text)
        if m:
            text, page = m.group("body").rstrip(" .…·_"), m.group("page")
    m = NUMBER.match(text)
    num = m.group("num").strip() if m else ""
    title = text[m.end():].strip() if m else text.strip()
    return TocEntry(line=ln.i, number=num, title=title, page_label=page, x0=ln.x0)


def _gap_limit(lines: list[Line]) -> float:
    """Twice the typical spacing between consecutive lines on one page."""
    gaps = [
        a.y0 - b.y1 if a.y0 > b.y1 else abs(a.y0 - b.y0)
        for a, b in zip(lines, lines[1:], strict=False)
        if a.page == b.page and a.y0 > b.y0
    ]
    return 2.5 * (statistics.median(gaps) if gaps else 6.0) + 4.0


def _page_number_runs(ext: Extraction) -> list[list[int]]:
    """Runs of lines that end in a page number; a run counts when at least
    three lines have dot leaders, or six lines end in increasing numbers."""
    runs: list[list[int]] = []
    cur: list[int] = []
    for ln in ext.lines:
        m = PAGE_REF.match(ln.text)
        entry_like = m and len(ln.text.split()) <= 18 and re.search(r"[A-Za-z]", m.group("body"))
        if entry_like:
            cur.append(ln.i)
            continue
        if cur:
            runs.append(cur)
        cur = []
    if cur:
        runs.append(cur)
    out = []
    for run in runs:
        ms = [PAGE_REF.match(ext.lines[i].text) for i in run]
        leaders = sum(bool(m.group("lead")) for m in ms)
        nums = [int(m.group("page")) for m in ms if m.group("page").isdigit()]
        rising = sum(b >= a for a, b in zip(nums, nums[1:], strict=False))
        if leaders >= 3 or (len(run) >= 6 and rising >= 0.8 * (len(nums) - 1)):
            out.append(run)
    return out


def _titled_runs(ext: Extraction, gap: float) -> list[list[int]]:
    """A TOC title line plus the run of entries after it."""
    out = []
    lines = ext.lines
    for ln in lines:
        if not TOC_TITLE.match(ln.text.strip()):
            continue
        run = [ln.i]
        first: Line | None = None
        prev = ln
        for nxt in lines[ln.i + 1 : ln.i + 400]:
            if nxt.page != prev.page or (prev.y0 - nxt.y1) > gap:
                break
            words = len(nxt.text.split())
            numbered = bool(NUMBER.match(nxt.text))
            if first is None:
                if words > 16 or nxt.text.rstrip().endswith((".", ":", ";", ",")):
                    break
                first = nxt
            else:
                # Entries share the first entry's pattern: numbered entries
                # stay numbered (a wrapped title is indented past the number),
                # styled entries keep the same size and weight.
                same_style = abs(nxt.size - first.size) < 0.6 and nxt.bold == first.bold
                wrapped = not numbered and nxt.x0 > first.x0 + 4 and same_style
                if NUMBER.match(first.text) and not (numbered or wrapped):
                    break
                if not NUMBER.match(first.text) and not same_style:
                    break
                if words > 16:
                    break
            run.append(nxt.i)
            prev = nxt
        if len(run) >= 3:
            out.append(run)
    return out


def _furniture(ext: Extraction) -> set[int]:
    """Running headers/footers and page numbers: text that repeats (digits
    masked) at about the same height on many pages."""
    seen: dict[tuple[str, int], set[int]] = {}
    for ln in ext.lines:
        key = (re.sub(r"\d+", "#", ln.text.lower()), round(ln.y0 / 12))
        seen.setdefault(key, set()).add(ln.page)
    threshold = max(3, int(len(ext.pages) * 0.3))
    repeated = {k for k, pages in seen.items() if len(pages) >= threshold}
    body = ext.body_size()
    heights = {p.n: (p.origin_y, p.height) for p in ext.pages}
    out = set()
    for ln in ext.lines:
        masked = re.sub(r"\d+", "#", ln.text.lower())
        oy, h = heights[ln.page]
        # Running headers whose wording changes per section ("10.1 • Cell
        # Division") don't repeat, but they sit in the margin in small type.
        in_margin = (ln.y1 - oy) > h * 0.94 or (ln.y0 - oy) < h * 0.06
        if (
            (masked, round(ln.y0 / 12)) in repeated
            or re.fullmatch(r"[#\s\-–—|.]*(page\s*#)?[#\s]*", masked)
            or (in_margin and ln.size <= body)
        ):
            out.add(ln.i)
    return out


@dataclass
class Anchored:
    """An outline entry (bookmark or TOC entry) tied to the body line it names."""

    line: int
    level: int
    number: str
    title: str


def _joined(ext: Extraction, i: int, k: int) -> str:
    return canon(" ".join(ln.text for ln in ext.lines[i : i + k + 1]))


def _names(ext: Extraction, i: int, want: str) -> bool:
    """Line i (alone or joined with the next one or two, for titles that wrap
    or print "CHAPTER 17" above the title) is the heading `want`."""
    for k in range(3):
        if i + k >= len(ext.lines) or (k and ext.lines[i + k].page != ext.lines[i].page):
            break
        j = _joined(ext, i, k)
        if j == want or (j.startswith(want) and len(want) >= 0.6 * len(j)):
            return True
        if not want.startswith(j):
            break
    return False


def anchor_bookmarks(ext: Extraction) -> list[Anchored]:
    """Bookmarks matched to a line on their target page (or the next one),
    preferring the line nearest the bookmark's y position."""
    toc = toc_of(ext).lines | furniture_of(ext)
    by_page: dict[int, list[Line]] = {}
    for ln in ext.lines:
        by_page.setdefault(ln.page, []).append(ln)
    out: list[Anchored] = []
    used: set[int] = set()
    for it in ext.outline:
        want = canon(it.title)
        if not want:
            continue
        best = None
        for p in (it.page, it.page + 1):
            hits = [ln for ln in by_page.get(p, []) if ln.i not in toc and ln.i not in used and _names(ext, ln.i, want)]
            if hits:
                best = min(hits, key=lambda ln: abs(ln.y1 - it.y) if it.y is not None else ln.i)
                break
        if best is None:
            continue
        used.add(best.i)
        m = NUMBER.match(it.title)
        num = m.group("num").strip() if m else ""
        out.append(Anchored(best.i, it.level, num, it.title[m.end():].strip() if m else it.title))
    return out


def anchor_toc(ext: Extraction) -> list[Anchored]:
    """TOC entries matched, in order, to the first body line after the TOC
    that prints the same number and title."""
    toc = toc_of(ext)
    if not toc.entries:
        return []
    out: list[Anchored] = []
    skip = toc.lines | furniture_of(ext)
    cursor = max(toc.lines) + 1
    for e in toc.entries:
        want = canon(f"{e.number} {e.title}")
        if len(want) < 3:
            continue
        hit = next(
            (i for i in range(cursor, len(ext.lines)) if i not in skip and _names(ext, i, want)),
            None,
        )
        if hit is None:
            continue
        out.append(Anchored(hit, e.level, e.number, e.title))
        cursor = hit + 1
    return out


def outline_backbone(ext: Extraction) -> tuple[list[Anchored], str]:
    """The document's own outline, when it has a usable one: bookmarks first,
    then a table of contents. Usable means at least three entries and most of
    them found in the body."""
    for source, items, total in (
        ("bookmarks", anchor_bookmarks(ext) if ext.outline else [], len(ext.outline)),
        ("toc", anchor_toc(ext), len(toc_of(ext).entries)),
    ):
        if total and len(items) >= 3 and len(items) >= 0.6 * total:
            return items, source
    return [], ""


_CACHE: dict[tuple[str, int], tuple[Extraction, object]] = {}


def _cached(kind: str, ext: Extraction, make):
    """Compute once per loaded extraction (keyed by identity, checked so a
    recycled id can't return another document's result)."""
    hit = _CACHE.get((kind, id(ext)))
    if hit and hit[0] is ext:
        return hit[1]
    if len(_CACHE) > 32:
        _CACHE.pop(next(iter(_CACHE)))
    val = make(ext)
    _CACHE[(kind, id(ext))] = (ext, val)
    return val


def toc_of(ext: Extraction) -> Toc:
    return _cached("toc", ext, detect_toc)


def furniture_of(ext: Extraction) -> set[int]:
    return _cached("furniture", ext, _furniture)


def detect_toc(ext: Extraction) -> Toc:
    toc = Toc()
    if not ext.lines:
        return toc
    gap = _gap_limit(ext.lines)
    page_runs = _page_number_runs(ext)
    titled = _titled_runs(ext, gap)
    for run, page_ref in [(r, True) for r in page_runs] + [(r, False) for r in titled]:
        fresh = [i for i in run if i not in toc.lines]
        if not fresh:
            continue
        toc.lines.update(fresh)
        for i in fresh:
            ln = ext.lines[i]
            if TOC_TITLE.match(ln.text.strip()):
                continue
            toc.entries.append(_entry(ln, page_ref))
    toc.entries.sort(key=lambda e: e.line)

    # Levels: numbering depth where entries are numbered, otherwise indent rank.
    indents = sorted({round(e.x0 / 6) for e in toc.entries})
    rank = {v: k + 1 for k, v in enumerate(indents)}
    for e in toc.entries:
        e.level = _depth(e.number) if re.match(r"\d", e.number) else rank[round(e.x0 / 6)]

    # Char spans of contiguous TOC lines, so marker hits inside them can be rejected.
    for i in sorted(toc.lines):
        ln = ext.lines[i]
        if toc.spans and toc.spans[-1][1] >= ln.start - 1:
            toc.spans[-1] = (toc.spans[-1][0], ln.end + 1)
        else:
            toc.spans.append((ln.start, ln.end + 1))
    return toc
