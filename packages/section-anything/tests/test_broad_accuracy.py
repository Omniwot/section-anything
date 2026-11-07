"""Track B (broad accuracy): the largest remaining causes of false headings in Free, fixed by general rules. Contents
pages whose entries change style; running heads that name the current part or section; entries of definition lists
and reference manuals."""

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


# ── entries of definition lists and reference manuals ──
def test_defined_terms_are_not_headings():
    rows: list[Row] = [(1, "4 Definitions", 12.0, True, 120, 760), *_prose(1, 740, 3),
                       (1, "Australian entity means:", 11.0, True, 177, 690), (1, "(a) a company which is a resident;", 11.0, False, 185, 676),
                       (1, "carries on business in Australia: see section 5.", 11.0, True, 177, 650), *_prose(1, 630, 6)]
    texts = [ln.text for ln, _ in candidates(_ext(rows))]
    assert "4 Definitions" in texts
    assert not any("means" in t or ": see" in t for t in texts)


def test_reference_manual_definition_headers_are_not_headings():
    rows: list[Row] = [(1, "10.2 Rewrite Built-in Functions", 13.0, True, 90, 760), *_prose(1, 740, 3),
                       (1, "integer index (string s, integer c)", 12.0, False, 90, 690), (1, "[Function]", 11.0, False, 474, 690),
                       (1, "Returns the index of the first occurrence of the character c in the string s and more.", 11.0, False, 119, 676),
                       (1, "OM_uint32 gss_wrap (OM uint32 * minor_status, const", 12.0, False, 90, 650), (1, "[Function]", 11.0, False, 474, 650),
                       (1, "gss ctx id t context_handle, int conf_req_flag)", 12.0, False, 140, 636), *_prose(1, 620, 6)]
    texts = [ln.text for ln, _ in candidates(_ext(rows))]
    assert texts == ["10.2 Rewrite Built-in Functions"]


def test_glossary_terms_over_indented_definitions_are_not_headings():
    # The document's paragraphs start at the margin (page 1); its glossary indents each definition (page 2).
    rows: list[Row] = [*_prose(1, 780, 30), (2, "Glossary", 16.0, True, 72, 780), *_prose(2, 760, 4)]
    y = 700
    for term in ("iterable", "decorator", "dictionary view"):
        rows += [(2, term, 11.0, True, 72, y),
                 (2, "An object capable of returning its members one at a time, such as all sequence types and", 11.0, False, 97, y - 13),
                 (2, "some non-sequence types like dict and file objects, and objects of any classes you define.", 11.0, False, 97, y - 26)]
        y -= 45
    texts = [ln.text for ln, _ in candidates(_ext(rows))]
    assert "Glossary" in texts and not {"iterable", "decorator", "dictionary view"} & set(texts)


def test_heading_over_a_first_line_indent_stays():
    # A heading whose paragraph indents its first line only (the second line returns to the margin) is a heading.
    rows: list[Row] = [*_prose(1, 780, 4), (1, "Data collection", 11.0, True, 72, 720),
                       (1, "We collected the records from every site over two years, and kept the", 11.0, False, 87, 707),
                       (1, "originals in the archive for the later checks described in the next section.", 11.0, False, 72, 694),
                       *_prose(1, 680, 6)]
    assert "Data collection" in [ln.text for ln, _ in candidates(_ext(rows))]


def test_contents_list_goes_on_past_a_title_repeated_in_smaller_type():
    # "Division 1—Preliminary" under "Part 3A—Preliminary" in the list: an entry, not the body's first heading.
    rows: list[Row] = [(1, "Contents", 18.0, False, 120, 780)]
    entries = [("Part 1—Preliminary", 12.0), ("Part 2—Statements", 12.0), ("Part 3A—Commissioner", 12.0),
               ("Division 1—Preliminary", 11.0), ("Division 2—Functions of the Commissioner", 11.0), ("Part 4—Miscellaneous", 12.0)]
    rows += [(1, t, size, True, 120, 750 - 20 * k) for k, (t, size) in enumerate(entries)]
    page = 2
    for t, size in entries:
        rows += [(page, t, 16.0 if size == 12.0 else 14.0, True, 120, 760), *_prose(page, 740, 12)]
        page += 1
    ext = _ext(rows)
    toc = toc_of(ext).lines
    assert {ln.i for ln in ext.lines if ln.page == 1 and ln.i > 0} <= toc
    assert not toc & {ln.i for ln in ext.lines if ln.page > 1}


def test_running_head_that_repeats_a_heading_is_furniture():
    rows: list[Row] = [(1, "Part 4—Miscellaneous", 16.0, True, 120, 700), *_prose(1, 680, 20)]
    for page in (2, 3):  # the Part's two pages carry its name at the top, in 10 pt
        rows += [(page, "Part 4 Miscellaneous", 10.0, False, 396, 800), *_prose(page, 760, 20)]
    ext = _ext(rows)
    furn = furniture_of(ext)
    assert all(ln.i in furn for ln in ext.lines if ln.text == "Part 4 Miscellaneous")
    assert not any(ln.i in furn for ln in ext.lines if ln.text == "Part 4—Miscellaneous")
