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
- Contents pages under a contents title whose entries change style (labels
  on lines of their own, titles split from their leaders and page numbers,
  letter-spaced labels): every line after the title is an entry until the
  body begins (`_open_runs`).

Entries keep their number, title, printed page and indent, so the free
strategy can use a TOC as an outline. `outline_backbone` anchors either the
PDF's bookmarks or the TOC entries to the body lines they name, through an
index built once per document (no rescan of the body per entry).

Derived values (TOC, furniture, the name index) are cached on the Extraction
object itself, so they are freed with it and are safe across threads.
"""

from __future__ import annotations

import bisect
import re
import statistics
from dataclasses import dataclass, field

from section_anything.extract import Extraction, Line
from section_anything.markers import canon

TOC_TITLE = re.compile(
    r"^(table of contents|contents|contents at a glance|brief contents|chapter outline|outline|in this chapter"
    r"|chapter contents|summary of contents|short contents"
    # the contents titles of legislation and of other languages
    r"|table of provisions|arrangement of sections|arrangement of provisions|arrangement of regulations"
    r"|inhaltsverzeichnis|inhaltsübersicht|table des matières|sommaire|table analytique"
    r"|índice|indice|contenido|contenidos|sommario|inhoud|inhoudsopgave)\s*:?$",
    re.I,
)
# "Title .... 12", "Title . . . 12", "Title … 12", "Title   12"
PAGE_REF = re.compile(r"^(?P<body>.*?\S)\s*(?P<lead>(?:\.\s?){2,}|…+|·{2,}|_{2,})?\s*(?P<page>\d{1,4}|[ivxlc]{1,7})$", re.I)
NUMBER = re.compile(
    r"^(?P<num>(?:chapter|part|section|appendix|annex|unit|lesson|module)\s+[\dA-Z]+[.:]?"
    r"|\d+(?:\.\d+)*\.?|[IVXLC]+\.|[A-Z]\.)\s+(?=\S)",
    re.I,
)
# A section number alone on its extracted line: "1", "4.2", "1.", "A", "A.1", "IV.".
NUMBER_ALONE = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[A-Z](?:\.\d+)*\.?|[IVXLC]+\.?)$")
# A number run into the next word ("Kapitel 2Rechte"), as bookmark titles joined from two lines are.
GLUED = re.compile(r"(\d)([^\W\d_]{2,})")


def split_number(ext: Extraction, ln: Line) -> bool:
    """`ln` is only a heading's number and its title follows on the same baseline in the same style
    ("1" | "Introduction"). The extractor splits a line where a space is wider than twice the
    characters beside it, which happens after a section number when the title starts with a
    narrow letter such as "I"."""
    if not NUMBER_ALONE.match(ln.text.strip()) or ln.i + 1 >= len(ext.lines):
        return False
    t = ext.lines[ln.i + 1]
    title = t.text.strip()
    return (
        t.page == ln.page and t.size == ln.size and t.bold == ln.bold
        and abs(t.y0 - ln.y0) <= 0.3 * ln.size and 0 <= t.x0 - ln.x1 <= 3 * ln.size
        and title[:1].isalpha() and not NUMBER.match(title) and not NUMBER_ALONE.match(title)
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
        # Spans are sorted and disjoint: find the last one starting at or before pos.
        k = bisect.bisect_right(self.spans, (pos, float("inf"))) - 1
        return k >= 0 and self.spans[k][0] <= pos < self.spans[k][1]


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
    """A TOC title line plus the run of entries after it. A run that fills its page to the bottom
    goes on at the top of the next page (past the running header), as long as the entries keep
    their style: contents pages often span several pages with the title on the first only."""
    out = []
    lines = ext.lines
    furniture = furniture_of(ext)
    for ln in lines:
        if not TOC_TITLE.match(ln.text.strip()):
            continue
        run = [ln.i]
        first: Line | None = None
        prev = ln
        for nxt in lines[ln.i + 1 : ln.i + 2000]:
            if nxt.page != prev.page:
                if first is None or nxt.page != prev.page + 1 or prev.i in furniture:
                    break
                if nxt.i in furniture:
                    continue
                if abs(nxt.size - first.size) >= 0.6 or nxt.bold != first.bold:
                    break
            elif nxt.i in furniture and first is not None:
                continue
            elif (prev.y0 - nxt.y1) > gap:
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


def _despaced(text: str) -> str:
    """A letter-spaced line read as its words ("I n h a l t s ü b e r s i c h t", "K a p i t e l 4")."""
    t = text.strip()
    tokens = t.split()
    if len(tokens) >= 4 and all(len(x) == 1 for x in tokens):
        t = re.sub(r"(?<=[^\W\d_]) (?=[^\W\d_])", "", t)
    return t


# The titles that open a contents list for `_open_runs`: not the weaker "Outline" or "In this chapter", which also
# title sections of running text.
OPEN_TITLE = re.compile(
    r"^(table of contents|contents|short contents|contents at a glance|brief contents|summary of contents"
    r"|table of provisions|arrangement of sections|arrangement of provisions|arrangement of regulations"
    r"|inhaltsverzeichnis|inhaltsübersicht|table des matières|sommaire|table analytique"
    r"|índice|indice|contenido|contenidos|sommario|inhoud|inhoudsopgave)\s*:?$",
    re.I,
)
# The titles of the lists that often follow a contents list on its pages; they are not entries.
LIST_TITLE = re.compile(r"^(list of [a-z ]{3,30}|tables|figures|abbreviations|acronyms|appendices)\s*:?$", re.I)
LEADERS = re.compile(r"(?:[.·…:_]\s?){3,}")
LEADER_ONLY = re.compile(r"^[\s.·…:_\-–]*\d*[\s.·…:_\-–]*$")
OPEN_RUN_MIN_ENTRIES = 4
OPEN_RUN_MIN_LATER = 3  # entries whose text the body prints again after the list
OPEN_RUN_ENTRY_SHARE = 0.8  # of a following page's lines, for the list to go on there


# A structural label or section number that opens an entry ("§ 8", "Artikel 5", "PART 2", "4.1"): the body prints the
# same title with or without it.
ENTRY_LABEL = re.compile(
    r"^\s*(?:(?:part|chapter|section|schedule|annex|annexe|appendix|article|division|subdivision|title|teil|kapitel"
    r"|abschnitt|unterabschnitt|titel|artikel|anlage|anhang|chapitre|titre|partie|art\.)\s*(?:\d+[a-z]{0,2}|[ivxlc]+)\b"
    r"|§+\s*\d+[a-z]?|[a-z](?:\.\d+)+|\d+(?:\.\d+)*)[.:)]?\s*[—–-]?\s*",
    re.I,
)


def _entry_key(text: str) -> str:
    """An entry's words without its label or number, leaders and page number, in canonical form."""
    t = LEADERS.split(_despaced(text))[0]
    t = re.sub(r"\s+\d{1,4}\s*$", "", t)
    m = ENTRY_LABEL.match(t)
    rest = t[m.end():] if m else t
    return canon(rest if rest.strip() else t).replace(" ", "")


def _prose_lines(lines: list[Line]) -> int:
    """Lines of running text: more than 12 words, without leaders."""
    return sum(1 for y in lines if len(_despaced(y.text).split()) > 12 and not LEADERS.search(y.text))


def _sentence_like(text: str, nxt: Line | None = None) -> tuple[bool, bool]:
    """(the line reads as running text, the line is a paragraph's line on its own): without leaders, more than 12 words
    ending like a sentence, or more than 16 words; or six words or more that break a word at their end ("discus-") or
    run on into a line that starts in lower case (a narrow column's prose)."""
    t = _despaced(text)
    words = len(t.split())
    if LEADERS.search(t):
        return False, False
    runs_on = words >= 6 and (t.endswith("-") or (nxt is not None and nxt.text.strip()[:1].islower()))
    return words > 16 or runs_on or (words > 12 and t.endswith((".", ";", ",", ":"))), words > 16


def _open_runs(ext: Extraction, taken: set[int]) -> set[int]:
    """Contents pages that the run rules miss because their entries change style: a label on a line of its own above
    its title ("PART 1" / "ENERGY EFFICIENCY"), titles split from their dot leaders and page numbers, letter-spaced
    labels ("K a p i t e l 4"), page numbers in a column of their own. After a contents title (`OPEN_TITLE`) every
    line is an entry until the body begins: a line that repeats an earlier entry on a later page or in a bigger or
    bolder type (the body's first heading), a paragraph (a line of more than 16 words, or two lines in a row of running text), or a page on which fewer than
    four in five lines read as entries or more than two lines are running text. The list counts when it has
    `OPEN_RUN_MIN_ENTRIES` entries and the body prints
    at least `OPEN_RUN_MIN_LATER` of them again after it. The title line itself is left to the other rules (a
    README's "Table of contents" is a heading of its own)."""
    lines = ext.lines
    furniture = furniture_of(ext)
    out: set[int] = set()
    for ln in lines:
        if ln.i in out or ln.i in furniture or not OPEN_TITLE.match(_despaced(ln.text)):
            continue
        run: list[int] = []
        keys: dict[str, tuple[int, float, bool]] = {}  # entry -> (page, size, bold) of its first line in the list
        page, prev_text, k = ln.page, False, ln.i + 1
        while k < len(lines):
            x = lines[k]
            if x.page != page:
                # The list goes on over the next page only while that page reads as entries: most of its lines, and
                # no more than two lines of running text.
                rest = [y for y in lines[k:k + 300] if y.page == x.page and y.i not in furniture]
                entries = sum(1 for y in rest if not _sentence_like(y.text)[0])
                if (x.page != page + 1 or not rest or entries < OPEN_RUN_ENTRY_SHARE * len(rest)
                        or _prose_lines(rest) > 2):
                    break
                page = x.page
            if x.i in furniture:
                k += 1
                continue
            if LIST_TITLE.match(_despaced(x.text)) or OPEN_TITLE.match(_despaced(x.text)):
                k += 1  # "List of figures" after the contents: a title of its own, not an entry
                continue
            key = _entry_key(x.text)
            if len(key) >= 4 and key in keys:
                page0, size0, bold0 = keys[key]
                if x.page != page0 or x.size > size0 + 0.5 or (x.bold and not bold0):
                    break  # the body's first heading repeats an entry, on a later page or in a bigger or bolder type
                # (a schedule's own "PART 1", or "Division 1—Preliminary" under "Part 1—Preliminary", is an entry)
            nxt = lines[k + 1] if k + 1 < len(lines) and lines[k + 1].page == x.page else None
            running, paragraph = _sentence_like(x.text, nxt)
            if paragraph or (running and prev_text):
                if running and prev_text and run:
                    run.pop()
                break
            prev_text = running
            if len(key) >= 4:
                keys.setdefault(key, (x.page, x.size, x.bold))
            run.append(x.i)
            k += 1
        if len(run) < OPEN_RUN_MIN_ENTRIES or set(run) <= taken:
            continue
        later = {_entry_key(y.text) for y in lines[k:] if y.i not in furniture}
        if sum(1 for key in keys if key in later) >= OPEN_RUN_MIN_LATER:
            out.update(run)
    return out


# The labels a running head names its part or section by ("Part 3A", "Section 16A", "Artikel 4").
HEAD_LABELS = (r"(?:part|chapter|schedule|section|division|subdivision|annex|annexe|appendix|title|book|article|artikel"
               r"|art|rule|regulation|clause|paragraph|teil|kapitel|abschnitt|anlage|anhang|chapitre|titre|partie)")
ZONE_TOP, ZONE_BOTTOM = 0.12, 0.08  # the page's top and bottom margin zones, as shares of its height
ZONE_MIN_PAGES = 3
BARE_HEAD = re.compile(rf"^(?:{HEAD_LABELS}|§+)\.?\s*#$")


def _zone_key(text: str) -> str:
    """A running head's words with its section numbers masked ("Section 16A", "Part III") and a page number at either
    end left out ("12 | Annual report"): `part # preliminary`, `section #`."""
    t = text.strip().lower()
    t = re.sub(rf"\b({HEAD_LABELS})\s+[ivxlc]+\b", r"\1 #", t)
    t = re.sub(r"\d+[a-z]{0,3}\b", "#", t)
    if len(re.sub(r"[#|•·.\-–—\s]+", " ", t).split()) >= 2:
        t = re.sub(r"^#[\s|•·.\-–—]+", "", t)
        t = re.sub(r"[\s|•·.\-–—]+#$", "", t) if len(re.sub(r"[#|•·.\-–—\s]+", " ", t).split()) >= 2 else t
    return t.strip()


def _zone_heads(ext: Extraction, body: float, heights: dict[int, tuple[float, float]]) -> set[int]:
    """Running heads that name the current part or section, whose wording changes through the document ("Part 1
    Preliminary", "Section 16A", "CHAPTER 4. OPTIMIZATION OF ..."): the same words, section numbers masked, in the top
    or bottom margin zone of three or more pages, in a line no more than 1 pt over the body size and not bold at body
    size or larger (a heading's style). A bare label ("Section 16A") must come back on three in ten pages: an article
    that happens to open a few pages ("Artikel 4") is a heading. A line in the zone that repeats a heading of the
    document in a plainer style is a running head on as few as two pages; in italics, only when the heading is set
    1 pt larger (a heading set in italics at the top of a page is the heading itself)."""
    zone: dict[str, set[int]] = {}
    found: list[tuple[int, str]] = []
    for ln in ext.lines:
        oy, h = heights[ln.page]
        if h <= 0 or ln.size > body + 1.0 or (ln.bold and ln.size >= body - 0.3) or sum(c.isalpha() for c in ln.text) < 3:
            continue
        if (oy + h - ln.y1) / h < ZONE_TOP or (ln.y0 - oy) / h < ZONE_BOTTOM:
            k = _zone_key(ln.text)
            zone.setdefault(k, set()).add(ln.page)
            found.append((ln.i, k))
    bare_min = max(ZONE_MIN_PAGES, 0.3 * len(ext.pages))
    ok = {k for k, pages in zone.items() if len(pages) >= (bare_min if BARE_HEAD.match(k) else ZONE_MIN_PAGES)}
    # A running head that repeats a heading of the document in its own words ("Part 4 Miscellaneous" over the pages of
    # "Part 4—Miscellaneous"), however few pages it heads: a heading-styled line (bold or 1 pt larger) outside the zones
    # with the same words.
    zoned = {i for i, _ in found}
    headings: dict[str, float] = {}  # a heading's words -> its largest size
    for ln in ext.lines:
        if ln.i not in zoned and (ln.bold or ln.size >= body + 1.0) and len(canon(ln.text)) >= 6:
            headings[canon(ln.text)] = max(ln.size, headings.get(canon(ln.text), 0.0))

    def copy(i: int) -> bool:
        ln = ext.lines[i]
        size = headings.get(canon(ln.text))
        return (size is not None and (not ln.italic or size >= ln.size + 1.0)
                and len(zone[_zone_key(ln.text)]) >= 2)  # a running head comes back; a list's first entry does not

    return {i for i, k in found if k in ok or (not BARE_HEAD.match(k) and copy(i))}


def _furniture(ext: Extraction) -> set[int]:
    """Running headers/footers and page numbers: text that repeats (digits
    masked) at about the same height on many pages, or the same text at the
    same height on three pages in a row (a header that changes with each part,
    a table's repeated header row), or a running head in the margin zone that
    names the current part or section (`_zone_heads`)."""
    seen: dict[tuple[str, int], set[int]] = {}
    exact: dict[tuple[str, int], set[int]] = {}
    for ln in ext.lines:
        band = round(ln.y0 / 12)
        seen.setdefault((re.sub(r"\d+", "#", ln.text.lower()), band), set()).add(ln.page)
        exact.setdefault((ln.text.strip().lower(), band), set()).add(ln.page)
    threshold = max(3, int(len(ext.pages) * 0.3))
    repeated = {k for k, pages in seen.items() if len(pages) >= threshold}
    in_a_row = {k for k, pages in exact.items() if len(pages) >= 3 and any(p + 1 in pages and p + 2 in pages for p in pages)}
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
            or (ln.text.strip().lower(), round(ln.y0 / 12)) in in_a_row
            or re.fullmatch(r"[#\s\-–—|.]*(page\s*#)?[#\s]*", masked)
            or (in_margin and ln.size <= body)
        ):
            out.add(ln.i)
    out |= _zone_heads(ext, body, heights)
    # A heading's number split off its title looks like a page number; it is furniture only
    # when its title line is.
    out = {i for i in out if i + 1 in out or not split_number(ext, ext.lines[i])}
    hints = ext._derived.get("docling")  # Docling's page headers and footers (docling_input)
    return out | hints.furniture if hints is not None else out


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
    or print "CHAPTER 17" above the title) is the heading `want`.

    Reference implementation; the anchoring functions use `NameIndex`, which
    gives the same answers without rescanning lines."""
    for k in range(3):
        if i + k >= len(ext.lines) or (k and ext.lines[i + k].page != ext.lines[i].page):
            break
        j = _joined(ext, i, k)
        if j == want or (j.startswith(want) and len(want) >= 0.6 * len(j)):
            return True
        if not want.startswith(j):
            break
    return False


class NameIndex:
    """Every line's joined canonical text (the line plus up to two following
    lines on its page), sorted, so the lines naming a heading are found by
    binary search.

    `_names(i, want)` holds exactly when line i's longest join starts with
    `want` and, for the shortest join at least as long as `want`, `want` covers
    at least 60% of it. (Canonical text of joined lines is the lines' canonical
    texts joined by single spaces, so the joins are prefixes of each other.)"""

    WORK_LIMIT = 5_000_000  # candidate checks per document; bounds adversarial PDFs

    def __init__(self, ext: Extraction) -> None:
        lines = ext.lines
        canons = [canon(ln.text) for ln in lines]
        n = len(lines)
        full: list[str] = []
        self.lens: list[tuple[int, ...]] = []
        for i in range(n):
            j = canons[i]
            lens = [len(j)]
            for k in (1, 2):
                if i + k >= n or lines[i + k].page != lines[i].page:
                    break
                c = canons[i + k]
                if c:
                    j = f"{j} {c}" if j else c
                lens.append(len(j))
            full.append(j)
            self.lens.append(tuple(lens))
        self.order = sorted(range(n), key=full.__getitem__)
        self.keys = [full[i] for i in self.order]
        self.pages = [ln.page for ln in lines]
        self._memo: dict[str, list[int]] = {}
        self._work = 0

    def lines_naming(self, want: str) -> list[int]:
        """Indices of the lines that name `want`, ascending."""
        hit = self._memo.get(want)
        if hit is not None:
            return hit
        out: list[int] = []
        if want and self._work < self.WORK_LIMIT:
            lo = bisect.bisect_left(self.keys, want)
            last = ord(want[-1])
            hi = (bisect.bisect_left(self.keys, want[:-1] + chr(last + 1), lo) if last < 0x10FFFF
                  else len(self.keys))
            self._work += hi - lo
            size = len(want)
            for idx in range(lo, hi):
                i = self.order[idx]
                k = next((n for n in self.lens[i] if n >= size), None)
                if k is not None and size >= 0.6 * k:
                    out.append(i)
            out.sort()
        self._memo[want] = out
        return out

    def page_range(self, page: int) -> tuple[int, int]:
        """Line indices [a, b) on `page` (lines are in page order)."""
        return bisect.bisect_left(self.pages, page), bisect.bisect_left(self.pages, page + 1)


def name_index(ext: Extraction) -> NameIndex:
    return _cached("names", ext, NameIndex)


def anchor_bookmarks(ext: Extraction) -> list[Anchored]:
    """Bookmarks matched to a line on their target page (or the next one),
    preferring the line nearest the bookmark's y position."""
    toc = toc_of(ext).lines | furniture_of(ext)
    index = name_index(ext)
    out: list[Anchored] = []
    used: set[int] = set()
    for it in ext.outline:
        title = it.title
        want = canon(title)
        if not want:
            continue
        found = index.lines_naming(want)
        if not found and GLUED.search(title):
            # "Teil 1Gemeinsame Bestimmungen": the label and title lines were joined without a space.
            title = GLUED.sub(r"\1 \2", title)
            found = index.lines_naming(canon(title))
        best = None
        for p in (it.page, it.page + 1):
            a, b = index.page_range(p)
            ka, kb = bisect.bisect_left(found, a), bisect.bisect_left(found, b)
            hits = [ext.lines[i] for i in found[ka:kb] if i not in toc and i not in used]
            if hits:
                best = min(hits, key=lambda ln: abs(ln.y1 - it.y) if it.y is not None else ln.i)
                break
        if best is None:
            continue
        used.add(best.i)
        m = NUMBER.match(title)
        num = m.group("num").strip() if m else ""
        out.append(Anchored(best.i, it.level, num, title[m.end():].strip() if m else title))
    return out


def anchor_toc(ext: Extraction) -> list[Anchored]:
    """TOC entries matched, in order, to the first body line after the TOC
    that prints the same number and title."""
    toc = toc_of(ext)
    if not toc.entries:
        return []
    out: list[Anchored] = []
    skip = toc.lines | furniture_of(ext)
    index = name_index(ext)
    cursor = max(toc.lines) + 1
    for e in toc.entries:
        want = canon(f"{e.number} {e.title}")
        if len(want) < 3:
            continue
        found = index.lines_naming(want)
        k = bisect.bisect_left(found, cursor)
        hit = next((i for i in found[k:] if i not in skip), None)
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


def _cached(kind: str, ext: Extraction, make):
    """Compute once per extraction, cached on the object itself (objects without
    a cache, such as test doubles, just compute)."""
    derived = getattr(ext, "derived", None)
    return derived(kind, make) if derived is not None else make(ext)


def toc_of(ext: Extraction) -> Toc:
    return _cached("toc", ext, detect_toc)


def listing_of(ext: Extraction) -> set[int]:
    """Lines of contents lists that `toc_of` misses (see `detect_listings`)."""
    return _cached("listings", ext, _listings)[0]


def listing_pairs_of(ext: Extraction) -> list[tuple[int, int]]:
    """(entry line, the later heading line it names) for the entries of `listing_of`'s lists."""
    return _cached("listings", ext, _listings)[1]


# A contents list without page numbers or a known title ("CONTENTS OF ACT", "Arrangement of
# sections", a chapter's list of its sections, a contents page whose dot leaders were split off) is
# recognised by its entries: they come back later, in the same order, as heading-like lines spread
# over the document. Repeated material (the same table header row, the same clause list) also comes
# back in order, but as one block of adjacent lines, so most of the later lines must be apart.
LISTING_MIN_ENTRIES = 8
LISTING_MAX_GAP = 4  # unmatched lines with letters allowed between two entries
LISTING_MIN_SHARE = 0.5  # of the lines with letters from the first entry to the last
LISTING_MIN_AHEAD = 30  # lines between an entry and its later copy
LISTING_MIN_SPREAD = 0.15  # of the document's lines, from the first later copy to the last
LISTING_MIN_APART = 0.5  # share of consecutive later copies more than 3 lines apart


def detect_listings(ext: Extraction) -> set[int]:
    return _listings(ext)[0]


def _listings(ext: Extraction) -> tuple[set[int], list[tuple[int, int]]]:
    furniture = furniture_of(ext)
    body = ext.body_size()
    keys: dict[int, str] = {}
    for ln in ext.lines:
        if ln.i in furniture:
            continue
        t = ln.text.strip()
        m = NUMBER.match(t)
        t = t[m.end():] if m else t
        if re.search(r"[^\W\d_]{2}", t):
            keys[ln.i] = canon(t)
    heading_like = {
        ln.i for ln in ext.lines if ln.bold or ln.size >= body + 0.8 or NUMBER.match(ln.text.strip())
    }
    copies: dict[str, list[int]] = {}
    for i, k in keys.items():
        if i in heading_like:
            copies.setdefault(k, []).append(i)

    lines: set[int] = set()
    pairs: list[tuple[int, int]] = []
    entries: list[int] = []
    later: list[int] = []
    gap = 0

    def close() -> None:
        if len(entries) < LISTING_MIN_ENTRIES:
            return
        span = sum(1 for i in keys if entries[0] <= i <= entries[-1])
        apart = 1 + sum(b - a > 3 for a, b in zip(later, later[1:], strict=False))
        if not (len(entries) >= LISTING_MIN_SHARE * span and later[-1] - later[0] >= LISTING_MIN_SPREAD * len(ext.lines)
                and apart >= LISTING_MIN_APART * len(entries)):
            return
        # The first entries of a short list sit closer than LISTING_MIN_AHEAD to their copies: take the
        # lines before the list whose copies come after it and before the copies already matched.
        first, end, missed = entries[0], later[0], 0
        for i in sorted((x for x in keys if x < entries[0]), reverse=True):
            x = next((c for c in copies.get(keys[i], ()) if entries[-1] < c < end), None)
            if x is None:
                missed += 1
                if missed > LISTING_MAX_GAP:
                    break
                continue
            first, end, missed = i, x, 0
            pairs.append((i, x))
        lines.update(range(first, entries[-1] + 1))
        pairs.extend(zip(entries, later, strict=True))

    for i in sorted(keys):
        k = keys[i]
        j = next((x for x in copies.get(k, ()) if x > i + LISTING_MIN_AHEAD), None) if len(k) >= 4 else None
        if j is not None and (not entries or (j > later[-1] and i < later[0])):
            entries.append(i)
            later.append(j)
            gap = 0
        elif entries:
            gap += 1
            if gap > LISTING_MAX_GAP:
                close()
                entries, later, gap = [], [], 0
    close()
    return lines, sorted(pairs)


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
    # Contents pages whose entries change style: their lines are contents lines, without entries (the outline
    # comes from the lists above).
    toc.lines |= _open_runs(ext, toc.lines)

    # Levels: numbering depth where entries are numbered, otherwise indent rank.
    indents = sorted({round(e.x0 / 6) for e in toc.entries})
    rank = {v: k + 1 for k, v in enumerate(indents)}
    for e in toc.entries:
        e.level = _depth(e.number) if re.match(r"\d", e.number) else rank[round(e.x0 / 6)]

    toc.spans = _spans(ext, toc.lines)
    return toc


def _spans(ext: Extraction, lines: set[int]) -> list[tuple[int, int]]:
    """Char spans of contiguous TOC lines, so marker hits inside them can be rejected."""
    spans: list[tuple[int, int]] = []
    for i in sorted(lines):
        ln = ext.lines[i]
        if spans and spans[-1][1] >= ln.start - 1:
            spans[-1] = (spans[-1][0], ln.end + 1)
        else:
            spans.append((ln.start, ln.end + 1))
    return spans


def toc_with(ext: Extraction, extra: set[int]) -> Toc:
    """`toc_of(ext)` with more contents lines (no entries for them)."""
    toc = toc_of(ext)
    if extra <= toc.lines:
        return toc
    lines = toc.lines | extra
    return Toc(lines=lines, entries=toc.entries, spans=_spans(ext, lines))
