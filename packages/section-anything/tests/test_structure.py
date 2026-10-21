"""Anchoring index, TOC spans, per-object caches and the compact locator."""

from __future__ import annotations

import random
import time
from array import array

from section_anything.extract import Extraction, Line, Page
from section_anything.markers import Locator, canon
from section_anything.structure import NameIndex, Toc, _names, anchor_toc, furniture_of, toc_of

WORDS = ["1", "1.2", "Chapter", "17", "Introduction", "intro", "-", "•", "Methods", "and", "Results",
         "ﬁnal", "Scope", "of", "the", "Work", "A", "—", "(cont.)", "II."]


def _ext(texts: list[str], per_page: int = 7) -> Extraction:
    lines, cursor = [], 0
    for i, t in enumerate(texts):
        page = i // per_page + 1
        lines.append(Line(i=i, page=page, text=t, x0=72, y0=700 - (i % per_page) * 14, x1=500,
                          y1=710 - (i % per_page) * 14, size=10, bold=False, start=cursor, end=cursor + len(t)))
        cursor += len(t) + 1
    n_pages = (len(texts) - 1) // per_page + 1 if texts else 0
    pages = [Page(n=k, width=612, height=792, origin_x=0, origin_y=0, rotation=0, has_text=True)
             for k in range(1, n_pages + 1)]
    return Extraction(pages, lines, "\n".join(texts))


def test_name_index_matches_reference():
    rng = random.Random(7)
    texts = [" ".join(rng.choice(WORDS) for _ in range(rng.randint(1, 4))) for _ in range(300)]
    ext = _ext(texts)
    index = NameIndex(ext)
    wants = {canon(" ".join(texts[i:i + k])) for i in range(0, 300, 3) for k in (1, 2, 3)}
    wants |= {w[: max(1, len(w) // 2)] for w in list(wants)} | {"introduction", "1 2 methods", "chapter 17"}
    wants.discard("")
    for want in sorted(wants):
        expected = [i for i in range(len(texts)) if _names(ext, i, want)]
        assert index.lines_naming(want) == expected, want


def test_anchor_toc_is_not_quadratic():
    # A long TOC whose entries are missing from the body used to rescan every line per entry.
    toc = ["Contents"] + [f"{k}.1 Section number {k}" for k in range(1, 400)]
    body = [f"Body text line {k} about something else entirely" for k in range(30_000)]
    ext = _ext(toc + body, per_page=400)
    t0 = time.monotonic()
    anchor_toc(ext)
    assert time.monotonic() - t0 < 10


def test_toc_contains_uses_sorted_spans():
    toc = Toc(spans=[(0, 10), (20, 30), (40, 41)])
    hits = [p for p in range(-2, 50) if toc.contains(p)]
    assert hits == [*range(0, 10), *range(20, 30), 40]
    assert not Toc().contains(5)


def test_derived_values_are_cached_per_object():
    a, b = _ext(["Contents", "1 One 3", "2 Two 5", "3 Three 9"]), _ext(["Contents", "1 One 3", "2 Two 5", "3 Three 9"])
    assert toc_of(a) is toc_of(a) and toc_of(a) is not toc_of(b)
    assert furniture_of(a) is a._derived["furniture"]


def test_locator_offsets_are_compact():
    loc = Locator("Hello, ﬁnal-\nly WORLD")
    assert isinstance(loc.origin, array) and loc.origin.itemsize == 4
    hit = loc.find("finally world")
    assert hit is not None and loc.text[hit.start:hit.end] == "ﬁnal-\nly WORLD"
