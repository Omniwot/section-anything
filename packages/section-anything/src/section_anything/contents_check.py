"""Contents check: every entry of the document's own contents should be a heading of the output.

A PDF's bookmarks, its printed table of contents and a contents list without page numbers
(`structure.listing_of`) each list the document's headings. After a mode's own result, each entry is
looked for among the sections. An entry that no section covers is searched for in the body, near the
page it points to: by its text, or by its label and number ("Article 5", "Chapter 3"). When the line
is found it becomes a heading, flagged ``from_contents``, at the level the entry implies (the level
the same outline level got elsewhere in the output, else the level of headings in the same style).
An entry that is not found is never guessed: it is returned as unresolved, for `possible_misses`.

Bookmarks are used when the PDF has them, else the printed table of contents; contents lists without
page numbers are used in both cases.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from section_anything.extract import Extraction, Line
from section_anything.markers import canon
from section_anything.outline_check import MATCH_THRESHOLD, _similarity, _variants
from section_anything.strategies.base import RawSection
from section_anything.strategies.rules import CAPTION, LABEL_ONLY, STRUCTURE_LABEL, _label_text, side_notes
from section_anything.structure import (
    NUMBER,
    TOC_TITLE,
    furniture_of,
    listing_of,
    listing_pairs_of,
    name_index,
    toc_of,
)

MIN_ENTRIES = 3  # fewer bookmarks or contents entries are not an outline
FUZZY = 0.85  # similarity (0..1) of an entry's text and a body line for the line to count as it
MAX_WORDS = 25  # longer entries and lines are sentences, not headings
NEAR_LINES = 2  # a section starting this many lines from an entry's line covers it
SKIP_ENTRY = re.compile(r"^(?:(?:front|back|inside)\s+cover|cover(?:\s+page)?|title\s+page|bookmarks?)$", re.I)
LEADER = re.compile(r"(?:\.\s?){4,}|…|_{3,}")
REFERENCE = re.compile(r"^\[[^\]]+\]$")  # "[RFC3756]": a citation label


@dataclass
class Entry:
    """One entry of the document's contents and, once found, the body line it names."""

    source: str  # "bookmarks", "contents" (a printed table of contents) or "contents list"
    number: str
    title: str
    level: int | None  # None: a contents list gives no levels
    page: int | None  # the physical page it points to, when known
    y: float | None = None  # bookmark target position
    page_label: str | None = None  # printed page number of a contents entry
    line: int | None = None  # the body line it names
    listed_at: int | None = None  # its own line in a printed table of contents

    @property
    def text(self) -> str:
        return f"{self.number} {self.title}".strip()


@dataclass
class ContentsCheck:
    entries: list[Entry] = field(default_factory=list)
    covered: int = 0
    added: list[RawSection] = field(default_factory=list)
    unresolved: list[Entry] = field(default_factory=list)

    def summary(self) -> dict:
        sources = Counter(e.source for e in self.entries)
        return {"entries": len(self.entries), "sources": dict(sources), "covered": self.covered,
                "added": len(self.added), "unresolved": len(self.unresolved)}


def _split(text: str) -> tuple[str, str]:
    text = " ".join(text.split())
    m = NUMBER.match(text)
    return (m.group("num").strip(), text[m.end():].strip()) if m else ("", text)


def _usable(text: str) -> bool:
    """A heading's text: mostly letters, not a sentence, not the contents' own title, a cover, a bare
    label ("PART 1", whose title is another entry), a contents line with its leader, or a citation."""
    t = " ".join(text.split())
    letters = len(re.findall(r"[^\W\d_]", t))
    label = STRUCTURE_LABEL.match(t)
    return (letters >= 3 and letters >= 0.5 * len(t.replace(" ", "")) and len(t.split()) <= MAX_WORDS
            and re.search(r"[^\W\d_]{3}", t) is not None and not t.endswith((",", ";", "=", "-", "\u2212"))
            and "(cid:" not in t and not TOC_TITLE.match(t) and not SKIP_ENTRY.match(t)
            and not LABEL_ONLY.match(_label_text(t)) and not (label and not t[label.end():].strip(" .:-\u2013\u20140123456789"))
            and not LEADER.search(t) and not REFERENCE.match(t))


def entries_of(ext: Extraction) -> list[Entry]:
    """The document's contents entries, in order: its bookmarks if it has at least `MIN_ENTRIES`,
    else its printed table of contents, then the entries of contents lists without page numbers."""
    out: list[Entry] = []
    if len(ext.outline) >= MIN_ENTRIES:
        for it in ext.outline:
            if _usable(it.title):
                num, title = _split(it.title)
                out.append(Entry("bookmarks", num, title, it.level, it.page, y=it.y))
    else:
        toc = toc_of(ext)
        if len(toc.entries) >= MIN_ENTRIES:
            for e in toc.entries:
                if _usable(f"{e.number} {e.title}"):
                    out.append(Entry("contents", e.number, e.title, e.level, None, page_label=e.page_label,
                                     listed_at=e.line))
    # The same text listed three or more times is a table of references ("Section 7.2"), not contents.
    counts = Counter(canon(e.text) for e in out)
    out = [e for e in out if counts[canon(e.text)] < 3]
    listed = {e.listed_at: e for e in out if e.listed_at is not None}
    seen: set[int] = set()
    for i, j in listing_pairs_of(ext):
        if i in listed:
            listed[i].line = j  # the same entry, already found later in the document
        elif j not in seen and _usable(ext.lines[i].text):
            num, title = _split(ext.lines[i].text)
            out.append(Entry("contents list", num, title, None, ext.lines[j].page, line=j))
        seen.add(j)
    return out


def _joins(ext: Extraction, i: int) -> list[str]:
    """Line i alone and joined with the next one or two lines on its page."""
    lines, out, text = ext.lines, [], ""
    for k in range(3):
        if i + k >= len(lines) or lines[i + k].page != lines[i].page:
            break
        text = f"{text} {lines[i + k].text}" if text else lines[i + k].text
        out.append(text)
    return out


def _label_key(text: str) -> tuple[str, str] | None:
    m = STRUCTURE_LABEL.match(_label_text(text).strip())
    return (m.group("kind").lower().rstrip("."), m.group("n").upper()) if m else None


def _names(ext: Extraction, i: int, entry: Entry) -> bool:
    """Body line i (alone or joined with the next lines) is the entry: same label and number, or
    text at least `FUZZY` similar."""
    ln = ext.lines[i]
    if len(ln.text.split()) > MAX_WORDS or CAPTION.match(ln.text):
        return False
    key = _label_key(entry.text)
    if key is not None and _label_key(ln.text) == key:
        return True
    want = canon(entry.text).replace(" ", "")
    if len(want) < 3:
        return False
    for j in _joins(ext, i):
        got = canon(j).replace(" ", "")
        if got and fuzz.ratio(want, got) >= 100 * FUZZY:
            return True
    return False


def _find(ext: Extraction, entry: Entry, pages: list[int], lo: int, hi: int, skip: set[int], used: set[int]) -> int | None:
    """The body line naming `entry` on `pages` (in that order) between lines lo and hi: exact text
    first (`structure.NameIndex`), then `_names`; nearest the bookmark's position on a tie."""
    index = name_index(ext)
    exact = set(index.lines_naming(canon(entry.text))) | (set(index.lines_naming(canon(entry.title))) if entry.number else set())
    for p in pages:
        a, b = index.page_range(p)
        a, b = max(a, lo), min(b, hi)
        if a >= b:
            continue
        free = [i for i in range(a, b) if i not in skip and i not in used]
        for hits in ([i for i in free if i in exact], [i for i in free if i not in exact and _names(ext, i, entry)]):
            if hits:
                if entry.y is not None:
                    return min(hits, key=lambda i: abs(ext.lines[i].y1 - entry.y))
                return hits[0]
    return None


def _page_offset(ext: Extraction, found: list[Entry]) -> int | None:
    """Physical page minus printed page, from the contents entries already found."""
    diffs = [ext.lines[e.line].page - int(e.page_label) for e in found
             if e.line is not None and e.page_label and e.page_label.isdigit()]
    return round(statistics.median(diffs)) if len(diffs) >= 2 else None


def locate(ext: Extraction, entries: list[Entry]) -> None:
    """Set each entry's body line, where one is found."""
    if not ext.lines:
        return
    side = side_notes(ext)
    skip = toc_of(ext).lines | listing_of(ext) | furniture_of(ext) | side
    used = {e.line for e in entries if e.line is not None and e.source != "contents list"}
    n_pages = max(ln.page for ln in ext.lines)
    for e in entries:
        if e.line is None and e.source == "bookmarks" and e.page:
            e.line = _find(ext, e, [e.page, e.page + 1], 0, len(ext.lines), skip, used)
            if e.line is not None:
                used.add(e.line)
    _drop_duplicates(entries)
    used |= {e.line for e in entries if e.line is not None}
    toc = [e for e in entries if e.source == "contents"]
    if not toc:
        return
    start = min(e.listed_at for e in toc if e.listed_at is not None) + 1
    # In order, after the contents: first exact matches, then the rest between their neighbours.
    cursor = start
    for e in toc:
        if e.line is not None:
            cursor = max(cursor, e.line + 1)
            continue
        found = [i for i in name_index(ext).lines_naming(canon(e.text)) if i >= cursor and i not in skip and i not in used]
        if found:
            e.line = found[0]
            used.add(e.line)
            cursor = e.line + 1
    offset = _page_offset(ext, toc)
    if offset is not None:
        # An exact copy far from the printed page is another mention (a figure, an overview).
        for e in toc:
            if e.line is not None and e.page_label and e.page_label.isdigit() \
                    and abs(ext.lines[e.line].page - (int(e.page_label) + offset)) > 1:
                used.discard(e.line)
                e.line = None
    for k, e in enumerate(toc):
        if e.line is not None:
            continue
        lo = max((x.line for x in toc[:k] if x.line is not None), default=start - 1) + 1
        hi = min((x.line for x in toc[k + 1:] if x.line is not None), default=len(ext.lines))
        if offset is not None and e.page_label and e.page_label.isdigit():
            p = int(e.page_label) + offset
            pages = [p, p + 1, p - 1]
        elif lo < hi:
            first, last = ext.lines[lo].page, ext.lines[hi - 1].page
            pages = list(range(first, min(last, first + 3) + 1))
        else:
            pages = []
        e.line = _find(ext, e, [p for p in pages if 1 <= p <= n_pages], lo, hi, skip, used) if pages else None
        if e.line is not None:
            used.add(e.line)
    for e in toc:
        if e.line is not None:
            e.page = ext.lines[e.line].page
        elif offset is not None and e.page_label and e.page_label.isdigit():
            e.page = min(max(1, int(e.page_label) + offset), n_pages)
    _drop_duplicates(entries)


def _drop_duplicates(entries: list[Entry]) -> None:
    """Contents-list entries that name a line a bookmark or table-of-contents entry names are the
    same entry."""
    lines = {e.line for e in entries if e.source != "contents list" and e.line is not None}
    if lines:
        entries[:] = [e for e in entries if e.source != "contents list"
                      or not any(abs(e.line - i) <= NEAR_LINES for i in lines)]


def _covering(entry: Entry, body: list[dict], ext: Extraction) -> dict | None:
    """The section that already is this entry: one starting within `NEAR_LINES` lines of its body
    line, else one with a similar title on its page or the next."""
    if entry.line is not None:
        page = ext.lines[entry.line].page
        for s in body:
            if abs(s["first_line"] - entry.line) <= NEAR_LINES and s["page_start"] == page:
                return s
    else:
        page = entry.page
    if page is None:
        return None
    want = _variants(entry.text) | _variants(entry.title)
    best, best_score = None, MATCH_THRESHOLD
    for s in body:
        if s["page_start"] in (page - 1, page, page + 1):
            got = _variants(f"{s.get('number') or ''} {s.get('title') or ''}") | _variants(s.get("title") or "")
            score = _similarity(got, want)
            if score >= best_score:
                best, best_score = s, score
    return best


def _style(ext: Extraction, i: int) -> tuple[float, bool]:
    ln: Line = ext.lines[i]
    return ln.size, ln.bold


def _levels(pairs: list[tuple[int, int]]) -> dict[int, int]:
    by_entry: dict[int, Counter] = {}
    for el, sl in pairs:
        by_entry.setdefault(el, Counter())[sl] += 1
    return {el: c.most_common(1)[0][0] for el, c in by_entry.items()}


def _implied_level(e: Entry, mapped: dict[int, int], by_style: dict[tuple[float, bool], int],
                   ext: Extraction, before: dict | None) -> int:
    if e.level is not None and mapped:
        near = min(mapped, key=lambda lv: (abs(lv - e.level), lv))
        return max(1, mapped[near] + e.level - near)
    style = _style(ext, e.line)
    if style in by_style:
        return by_style[style]
    if e.level is not None:
        return max(1, e.level)
    return int(before["level"]) if before is not None else 1


def check_contents(sections: list[dict], ext: Extraction) -> ContentsCheck:
    """The entries no section covers: `added` holds a heading for each one found in the body,
    `unresolved` the ones that were not found."""
    check = ContentsCheck(entries=entries_of(ext))
    if not check.entries:
        return check
    locate(ext, check.entries)
    body = [s for s in sections if "front_matter" not in s["flags"] and 0 <= s.get("first_line", -1) < len(ext.lines)]
    pairs: list[tuple[int, int]] = []
    missing: list[Entry] = []
    for e in check.entries:
        s = _covering(e, body, ext)
        if s is None:
            missing.append(e)
        else:
            check.covered += 1
            if e.level is not None:
                pairs.append((e.level, int(s["level"])))
    mapped = _levels(pairs)
    styles: dict[tuple[float, bool], Counter] = {}
    for s in body:
        styles.setdefault(_style(ext, s["first_line"]), Counter())[int(s["level"])] += 1
    by_style = {st: c.most_common(1)[0][0] for st, c in styles.items() if sum(c.values()) >= 2}
    taken: set[int] = set()
    for e in missing:
        if e.line is None or e.line in taken:
            check.unresolved.append(e)
            continue
        taken.add(e.line)
        before = next((s for s in reversed(body) if s["first_line"] < e.line), None)
        marker = ext.lines[e.line].text.strip()
        check.added.append(RawSection(
            title=e.title or e.number, level=_implied_level(e, mapped, by_style, ext, before), number=e.number if e.title else "",
            start_marker=marker[:160], start_line=e.line, flags=["from_contents"],
        ))
    return check
