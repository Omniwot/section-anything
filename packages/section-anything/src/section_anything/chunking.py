"""Section-aware chunks with a size cap.

`chunk_sections` turns sections into chunks for retrieval: a section longer than `max_chars` is
split on paragraph breaks, then on sentence ends, then cut, packing greedily up to the cap; short
sibling sections are merged up to `min_chars`; a heading with no body still gives one chunk (its
heading), so a headings-only document yields chunks rather than nothing. Every chunk knows its
heading path, its section and its pages. Pure Python, deterministic, no model.

    >>> for chunk in tree.chunks(max_chars=1500):
    ...     print(chunk.heading_path, len(chunk.text))

Lengths are measured by `length`, `len` by default; pass a token counter to cap by tokens.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from section_anything.export import heading_text

PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n+")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=\S)")
Length = Callable[[str], int]


@dataclass
class Chunk:
    """One chunk of a section (or of a few short sibling sections merged).

    `text` is the chunk's own text, without the heading path; `heading_path` lists the headings
    from the outermost enclosing section down to the chunk's section (for merged sections, down
    to their shared parent; the sections' own headings are then in `text`). `section_index` is the
    chunk's section in the input list (the first one when merged) and `chunk_index` its position
    among that section's chunks. `page_start` / `page_end` are the pages the chunk's sections
    cover, or None when the sections carry no pages."""

    text: str
    heading_path: list[str] = field(default_factory=list)
    section_index: int = 0
    chunk_index: int = 0
    page_start: int | None = None
    page_end: int | None = None

    @property
    def prefixed_text(self) -> str:
        """`text` with the heading path on top: "3 Safety > 3.2 Storage\\n\\n..."; the text alone
        when the path is empty, and the path alone for a heading with no body (its text is the
        heading, which is not repeated)."""
        if not self.heading_path:
            return self.text
        path = " > ".join(self.heading_path)
        return path if self.text == self.heading_path[-1] else f"{path}\n\n{self.text}"


def chunk_sections(sections: list[dict[str, Any]], *, max_chars: int = 2000, min_chars: int = 200,
                   overlap_chars: int = 0, length: Length = len, prefix: bool = False) -> list[Chunk]:
    """Section-aware chunks with a size cap, in reading order.

    `sections` are section dicts (as in `SectionTree.sections` or `to_dict(text=True)`) with
    `text`: the section's own text, from its heading (a leading heading line is left out of the
    chunks and kept in `heading_path`) up to the next heading. `level` and `flags` give the
    hierarchy when `parent` and `heading_path` are missing.

    A section longer than `max_chars` is split on paragraph breaks (blank lines), a paragraph
    longer than that on sentence ends, and a sentence longer than that cut at a space (or
    anywhere, as a last resort), packing greedily up to `max_chars`. Consecutive sections shorter
    than `min_chars` are merged with the following sections under the same parent until the merged
    text reaches `min_chars` (never across a different parent; the document title and front
    matter stay on their own). A section with no text of its own gives one chunk whose text is its
    heading. `overlap_chars` > 0 repeats that much of the previous chunk's tail (from a word
    boundary) at the start of the next chunk of the same section; chunks stay within `max_chars`.

    `max_chars`, `min_chars` and `overlap_chars` are in units of `length`, `len` by default. Pass a
    token counter to cap by tokens, for example tiktoken's:
    ``length=lambda s: len(encoding.encode(s))``. With `prefix`, each chunk's `text` starts with
    its heading path (what `Chunk.prefixed_text` gives), so the embedded text names its place.

    The result is the same for the same input and options."""
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    if min_chars < 0 or overlap_chars < 0:
        raise ValueError("min_chars and overlap_chars must be 0 or more")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")
    secs = [dict(s) for s in sections]
    if any("parent" not in s or "heading_path" not in s for s in secs):
        from section_anything.api import link_sections

        link_sections(secs)
    bodies = [_body(s) for s in secs]
    return _chunk(secs, bodies, max_chars=max_chars, min_chars=min_chars, overlap_chars=overlap_chars,
                  length=length, prefix=prefix)


def _body(sec: dict[str, Any]) -> str:
    """The section's text without its heading line(s): a leading line (or two, for a wrapped
    heading) that prints the heading is dropped."""
    text = str(sec.get("text") or "").strip()
    head = _key(heading_text(sec))
    if not head or "front_matter" in (sec.get("flags") or []):
        return text
    lines = text.split("\n")
    acc = ""
    for n, line in enumerate(lines[:3], start=1):
        acc += _key(line)
        if acc.startswith(head):
            return "\n".join(lines[n:]).strip() if len(acc) - len(head) <= 3 else "\n".join(lines[n - 1:]).strip()
        if not head.startswith(acc):
            break
    return text


def _key(text: str) -> str:
    return re.sub(r"\W+", "", text.lower())


def _chunk(secs: list[dict[str, Any]], bodies: list[str], *, max_chars: int, min_chars: int,
           overlap_chars: int, length: Length, prefix: bool) -> list[Chunk]:
    """Merge, then split: see `chunk_sections`."""
    out: list[Chunk] = []
    for group in _groups(secs, bodies, max_chars, min_chars, length):
        k = group[0]
        if len(group) == 1:
            path = list(secs[k].get("heading_path") or [])
            text = bodies[k] or _heading(secs[k])
        else:
            parent = secs[k].get("parent")
            path = list(secs[parent].get("heading_path") or []) if parent is not None else []
            text = _merged_text(secs, bodies, group)
        pages = [p for i in group for p in (secs[i].get("page_start"), secs[i].get("page_end")) if p is not None]
        page_start, page_end = (min(pages), max(pages)) if pages else (None, None)
        for n, piece in enumerate(_split(text, max_chars, overlap_chars, length)):
            chunk = Chunk(piece, path, k, n, page_start, page_end)
            if prefix:
                chunk.text = chunk.prefixed_text
            out.append(chunk)
    return out


def _heading(sec: dict[str, Any]) -> str:
    return "" if "front_matter" in (sec.get("flags") or []) else heading_text(sec)


def _groups(secs: list[dict[str, Any]], bodies: list[str], max_chars: int, min_chars: int, length: Length) -> list[list[int]]:
    """Runs of section indexes that chunk together: a section on its own, or a short section with
    the following siblings (same parent) until `min_chars` is reached. A short section with no
    following sibling joins the previous run of the same parent when the result is within
    `max_chars`. The document title and front matter stay on their own; empty front matter is left
    out."""
    groups: list[list[int]] = []
    k = 0
    while k < len(secs):
        own = {"front_matter", "doc_title"} & set(secs[k].get("flags") or [])  # outside the hierarchy
        if own:
            if bodies[k] or _heading(secs[k]):
                groups.append([k])
            k += 1
            continue
        group = [k]
        j = k + 1
        while length(_merged_text(secs, bodies, group)) < min_chars and j < len(secs) and _sibling(secs, k, j):
            group.append(j)
            j += 1
        prev = groups[-1] if groups else None
        if (len(group) == 1 and length(bodies[k]) < min_chars and prev is not None and _sibling(secs, prev[0], k)
                and length(_merged_text(secs, bodies, [*prev, k])) <= max_chars):
            prev.append(k)
        else:
            groups.append(group)
        k = group[-1] + 1
    return groups


def _sibling(secs: list[dict[str, Any]], a: int, b: int) -> bool:
    flags = set(secs[b].get("flags") or [])
    return secs[a].get("parent") == secs[b].get("parent") and not ({"front_matter", "doc_title"} & flags)


def _merged_text(secs: list[dict[str, Any]], bodies: list[str], group: list[int]) -> str:
    parts = []
    for i in group:
        head = heading_text(secs[i])
        parts.extend(p for p in (head, bodies[i]) if p)
    return "\n\n".join(parts)


def _split(text: str, max_chars: int, overlap: int, length: Length) -> list[str]:
    """Pack `text` into pieces of at most `max_chars`: paragraphs, then sentences, then cuts, in
    order, each piece taking as many units as fit. With `overlap`, each piece after the first
    starts with the previous piece's tail."""
    if length(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    cur = ""
    for unit, sep in _units(text, max_chars - overlap, length):
        if not cur:
            cur = unit
        elif length(f"{cur}{sep}{unit}") <= max_chars:
            cur = f"{cur}{sep}{unit}"
        else:
            pieces.append(cur)
            tail = _tail(cur, overlap - length(sep), length) if overlap else ""
            cur = f"{tail}{sep}{unit}" if tail else unit
    if cur:
        pieces.append(cur)
    return pieces


def _units(text: str, budget: int, length: Length) -> list[tuple[str, str]]:
    """The text as (unit, separator before it) pairs, each unit within `budget`: paragraphs
    (joined by a blank line); a paragraph over the budget as sentences, a sentence over the
    budget cut (joined by a space)."""
    units: list[tuple[str, str]] = []
    for para in PARAGRAPH_BREAK.split(text):
        para = para.strip()
        if not para:
            continue
        if length(para) <= budget:
            units.append((para, "\n\n"))
            continue
        sep = "\n\n"
        for sent in SENTENCE_BREAK.split(para):
            for part in _cut(sent, budget, length):
                units.append((part, sep))
                sep = " "
    return units


def _cut(text: str, budget: int, length: Length) -> list[str]:
    """Cut `text` into parts within `budget`, at the last space before the limit when one lies in
    the second half of the part, else at the limit."""
    out: list[str] = []
    rest = text
    while length(rest) > budget:
        n = _fit(rest, budget, length)
        space = rest.rfind(" ", 0, n + 1)
        if space > n // 2:
            n = space
        out.append(rest[:n].strip())
        rest = rest[n:].strip()
    if rest:
        out.append(rest)
    return out


def _fit(text: str, budget: int, length: Length) -> int:
    """The most leading characters of `text` whose `length` is within `budget` (binary search:
    `length` is taken to grow with the text)."""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if length(text[:mid]) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return max(lo, 1)


def _tail(text: str, overlap: int, length: Length) -> str:
    """The last `overlap` units of `text`, from the first word boundary inside them."""
    lo, hi = 0, len(text)
    while lo < hi:  # the shortest suffix start whose suffix is within `overlap`
        mid = (lo + hi) // 2
        if length(text[mid:]) <= overlap:
            hi = mid
        else:
            lo = mid + 1
    tail = text[lo:]
    if lo > 0 and tail and not text[lo - 1].isspace():
        cut = re.search(r"\s", tail)
        tail = tail[cut.end():] if cut else ""
    return tail.strip()
