"""Track B (broad accuracy): the largest remaining causes of false headings in Free, fixed by general rules. Contents
pages whose entries change style; running heads that name the current part or section."""

from __future__ import annotations

from section_anything.extract import Extraction, Line, Page
from section_anything.strategies.rules import RulesStrategy, candidates
from section_anything.structure import _open_runs, _zone_heads, furniture_of, toc_of

PROSE = "The provisions of this part apply to every person who carries on the activity described in the"
def _words():
    """Distinct made-up words, so no line repeats (text repeated on many pages reads as a running head)."""
    n = 0
    while True:
        k, w = n, ""
        for _ in range(3):
            k, r = divmod(k, 18)
            w += "bcdfghjklmnprstvwz"[r] + "aeiou"[(n + len(w)) % 5]
        yield w
        n += 1


WORDS = _words()
# (page, text, size, bold, x0, y0): y0 is the bottom of the line, top of the page first.
Row = tuple[int, str, float, bool, float, float]


def _ext(rows: list[Row], height: float = 842) -> Extraction:
    lines, pos = [], 0
    for i, (page, text, size, bold, x0, y0) in enumerate(rows):
        lines.append(Line(i=i, page=page, text=text, x0=x0, y0=y0, x1=min(520.0, x0 + 0.45 * size * len(text)),
                          y1=y0 + size, size=size, bold=bold, start=pos, end=pos + len(text)))
        pos += len(text) + 1
    pages = [Page(n=n, width=595, height=height, origin_x=0, origin_y=0, rotation=0, has_text=True)
             for n in range(1, max(r[0] for r in rows) + 1)]
    return Extraction(pages, lines, "\n".join(r[1] for r in rows))


def _prose(page: int, y0: float, n: int) -> list[Row]:
    return [(page, f"{PROSE} {next(WORDS)} {next(WORDS)}", 11.0, False, 72, y0 - 13 * k) for k in range(n)]


def _heads(ext: Extraction) -> list[str]:
    return [r.title for r in RulesStrategy()._rules(ext)]


# ── contents pages whose entries change style ──
def _act_with_contents() -> Extraction:
    titles = ["Preliminary", "Registration of statements", "Access to statements", "Miscellaneous"]
    rows: list[Row] = [(1, "Example Act 2024", 20.0, True, 72, 760), (1, "CONTENTS", 14.0, False, 250, 720)]
    y = 690
    for n, t in enumerate(titles, 1):
        # A label on a line of its own above its title, a title split from its page number, a section entry.
        rows += [(1, f"PART {n}", 10.0, True, 260, y), (1, t.upper(), 9.0, False, 230, y - 12),
                 (1, f"{n} {t} of persons", 10.0, False, 90, y - 26), (1, str(3 + 2 * n), 10.0, False, 500, y - 26)]
        y -= 50
    page = 2
    for n, t in enumerate(titles, 1):
        rows += [(page, f"PART {n}", 12.0, True, 260, 760), (page, t.upper(), 11.0, False, 230, 744),
                 (page, f"{n} {t} of persons", 11.0, True, 72, 720), *_prose(page, 700, 12)]
        page += 1
    return _ext(rows)


def test_contents_page_with_changing_styles_is_a_contents_list():
    ext = _act_with_contents()
    toc = toc_of(ext).lines
    first_body = next(ln.i for ln in ext.lines if ln.page == 2)
    entries = [ln.i for ln in ext.lines if ln.page == 1 and ln.i > 1 and ln.i not in furniture_of(ext)]
    assert set(entries) <= toc  # labels and titles alike (page numbers alone are furniture already)
    assert 1 not in toc  # the "CONTENTS" title is left to the other rules
    assert not any(i >= first_body for i in toc)  # the body's first heading repeats an entry: the list ends there
    heads = _heads(ext)
    assert heads.count("1 Preliminary of persons") <= 1 and not any(h.startswith("PART 1 PRELIMINARY") and "PART 2" in h
                                                                   for h in heads)


def test_contents_title_needs_entries_named_again_later():
    # A "Contents" line over a short list nothing in the body names again is not opened as a contents list.
    rows: list[Row] = [(1, "Contents", 14.0, True, 72, 760), *[(1, f"Item {k} kept on file", 11.0, False, 72, 740 - 14 * k)
                                                                for k in range(6)], *_prose(1, 640, 10)]
    ext = _ext(rows)
    assert not ({ln.i for ln in ext.lines if ln.text.startswith("Item")} & _open_runs(ext, set()))


def test_a_section_titled_outline_is_not_a_contents_list():
    # "Outline" over a narrow column of prose (lines broken mid-word, running on in lower case).
    rows: list[Row] = [(1, "Outline", 14.0, False, 199, 760)]
    for k in range(8):
        rows.append((1, "How law can aid development has been the focus of much discus-" if k % 2 == 0
                     else "sion among development workers and policymakers in recent", 11.0, False, 69, 740 - 13 * k))
    rows += [(2, "How law can aid development", 14.0, True, 69, 760), *_prose(2, 740, 5)]
    ext = _ext(rows)
    assert not ({ln.i for ln in ext.lines if ln.page == 1} & _open_runs(ext, set()))


# ── running heads in the margin zone ──
def _paged(heads: list[tuple[str, str]], extra: list[Row] = ()) -> Extraction:
    """Pages with a running head pair at the top margin (part and section, 10 and 12 pt) over body text."""
    rows: list[Row] = []
    for page, (part, sect) in enumerate(heads, 1):
        rows += [(page, part, 10.0, False, 396, 790), (page, sect, 12.0, False, 430, 770), *_prose(page, 700, 10)]
    rows += list(extra)
    return _ext(sorted(rows, key=lambda r: (r[0], -r[5])))


def test_running_heads_that_name_the_section_are_furniture():
    heads = [("Preliminary Part 1", f"Section {s}") for s in ("1", "3", "4", "5", "6A", "7")]
    heads += [("Modern slavery statements Part 2", f"Section {s}") for s in ("11", "13", "16A")]
    ext = _paged(heads)
    furn = furniture_of(ext)
    assert all(ln.i in furn for ln in ext.lines if ln.text.startswith(("Section ", "Preliminary", "Modern")))
    assert not any(ln.text.startswith("Section ") for ln, _ in candidates(ext))


def test_a_label_opening_a_few_pages_is_a_heading():
    # "Article 4" opens 3 of 12 pages at the top: a heading with its title under it, not a running head.
    rows: list[Row] = []
    for page in range(1, 13):
        if page in (3, 7, 10):
            rows += [(page, f"Article {page}", 11.0, False, 280, 770), (page, "Scope of application", 11.0, True, 250, 756)]
        rows += _prose(page, 700, 10)
    ext = _ext(rows)
    zone = _zone_heads(ext, ext.body_size(), {p.n: (p.origin_y, p.height) for p in ext.pages})
    assert not any(ln.i in zone for ln in ext.lines if ln.text.startswith("Article"))


def test_bold_heading_repeated_at_page_tops_is_not_furniture():
    # A real subheading that opens several pages ("Effect on consumers") is bold at body size: not a running head.
    rows: list[Row] = []
    for page in range(1, 8):
        if page % 2:
            rows.append((page, "Effect on consumers and businesses", 11.0, True, 72, 790))
        rows += _prose(page, 760, 10)
    ext = _ext(rows)
    zone = _zone_heads(ext, ext.body_size(), {p.n: (p.origin_y, p.height) for p in ext.pages})
    assert not any(ln.i in zone for ln in ext.lines if ln.text.startswith("Effect"))
