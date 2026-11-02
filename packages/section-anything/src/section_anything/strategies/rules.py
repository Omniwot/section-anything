"""Heading detection from typography and numbering alone — no LLM, no cost.

The baseline every LLM strategy has to beat, and the candidate generator for
the "rules + LLM review" strategy.
"""

from __future__ import annotations

import re
from collections import defaultdict

from section_anything.docling_input import DoclingHints, hints_of
from section_anything.extract import Extraction, Line
from section_anything.outline_check import LETTER_SPACED
from section_anything.strategies.base import Context, RawSection, Strategy
from section_anything.structure import NUMBER_ALONE, furniture_of, outline_backbone, split_number, toc_of

NUMBERING = re.compile(
    r"^(?P<num>(?:chapter|part|section|appendix|article|annex|unit|lesson)\s+[\dA-Z]+[.:]?"
    r"|\d+(?:\.\d+)*\.?"
    r"|[IVXLC]+\."
    r"|[A-Z]\.)\s+(?=\S)",
    re.I,
)
CAPTION = re.compile(r"^(fig(ure)?|table|chart|exhibit|source|note)s?\b[\s.:]*\d", re.I)
# Run-in labels of maths environments ("Definition II.1.", "Lemma 3", "Proof."), set in bold
# like headings but never sections.
THEOREM = re.compile(
    r"^(definition|lemma|theorem|proposition|corollary|property|remark|example|conjecture|claim|assumption|proof)\b"
    r"\s*([IVXLC]+(\.\d+)*|\d+(\.\d+)*)?\s*[.:]",
    re.I,
)
# The abstract's heading, alone on its line ("Abstract", "ABSTRACT.") or run into the abstract's
# first line ("Abstract—We study…", "Abstract. Let…"). Journals often set it smaller than body text.
ABSTRACT_ALONE = re.compile(r"^\W{0,2}abstract\W{0,2}$", re.I)
ABSTRACT_RUNIN = re.compile(r"^\W{0,2}abstract\s*[.:—–-]\s*\S", re.I)

def _abstract_heading(ln: Line) -> bool:
    """The abstract's heading on the first two pages, whatever its size or weight."""
    text = ln.text.strip()
    if LETTER_SPACED.match(text):  # "A B S T R A C T"
        text = re.sub(r"\s+", "", text)
    return ln.page <= 2 and bool(ABSTRACT_ALONE.match(text) or ABSTRACT_RUNIN.match(text))


def _abstract_levels(sections: list[RawSection], abstract: set[int]) -> None:
    """The abstract is a sibling of the section that follows it: it takes that section's level
    (sections in reading order; the first one if nothing follows)."""
    for k, s in enumerate(sections):
        if s.start_line in abstract:
            nxt = next((t for t in sections[k + 1:] if t.start_line not in abstract), None)
            s.level = nxt.level if nxt else 1


def _labels(ext: Extraction, body: float) -> set[str]:
    """Short all-caps styled lines repeated three or more times ("LINK TO
    LEARNING", "NOTE", "EXAMPLE"): callout-box labels, not headings."""
    counts: dict[str, int] = defaultdict(int)
    for ln in ext.lines:
        t = ln.text.strip()
        if t.isupper() and len(t.split()) <= 4 and (ln.bold or ln.size > body):
            counts[t.lower()] += 1
    return {t for t, n in counts.items() if n >= 3}


def _runs_on(ext: Extraction, ln: Line) -> bool:
    """The line continues into a lowercase line right below it: a bold term
    opening a paragraph or glossary entry, not a standalone heading."""
    if ln.i + 1 >= len(ext.lines):
        return False
    nxt = ext.lines[ln.i + 1]
    return nxt.page == ln.page and nxt.text[:1].islower() and (ln.y0 - nxt.y1) < ln.size


def _vertical(ext: Extraction, ln: Line) -> bool:
    """A one- or two-character line next to another such line: rotated text read letter by letter
    (the arXiv side stamp), not an index letter, which has entries between."""
    near = [ext.lines[j] for j in (ln.i - 1, ln.i + 1) if 0 <= j < len(ext.lines)]
    return any(x.page == ln.page and len(x.text.strip()) <= 2 for x in near)


def candidates(ext: Extraction, loose: bool = False) -> list[tuple[Line, str]]:
    """Lines that look like headings, with their numbering prefix ("" if none).
    `loose` widens recall for an LLM to filter afterwards; TOC lines are
    excluded either way.

    Strict mode also drops what our test corpus showed to be noise: numbered
    lines in body type ("1. Describe…", "a. E6 activates p53") unless the
    number is multi-level or keyword-led ("2.3", "Chapter 4"); repeated
    callout labels; and bold terms that run on into a paragraph.

    With Docling hints (`docling_input`), lines Docling labels as headings are candidates whatever
    their style, and strict mode drops lines it labels as body text, list items, captions or code.

    Strict mode also drops the cells of table rows and takes a bare structural label ("CHAPITRE I")
    together with the bold, larger or capitalised title line under it."""
    body = ext.body_size()
    furniture = furniture_of(ext)
    toc = toc_of(ext).lines
    labels = set() if loose else _labels(ext, body)
    hints = hints_of(ext)
    bump = 0.4 if loose else 0.8
    out: list[tuple[Line, str]] = []
    split: set[int] = set()
    labelled = set() if loose else _label_lines(ext, furniture | toc, body, bump)
    cells = set() if loose else _table_cells(ext, furniture | toc)
    for ln in ext.lines:
        text = ln.text
        if ln.i in furniture or ln.i in toc or ln.i in cells or CAPTION.match(text):
            continue
        if ln.i in labelled:
            out.append((ln, ""))  # joined with its title line by _merge_wrapped
            continue
        if split_number(ext, ln):
            # Joined with its title line by _merge_wrapped (Free) and LlmReviewStrategy._rows.
            out.append((ln, text.strip()))
            split.add(ln.i)
            continue
        if hints is not None and ln.i in hints.headers:
            if loose or not (THEOREM.match(text) or text.strip().lower() in labels):
                m = NUMBERING.match(text)
                out.append((ln, m.group("num").strip() if m else ""))
            continue
        if hints is not None and not loose and ln.i in hints.body:
            continue
        if not re.search(r"[A-Za-z]", text):
            continue
        if _abstract_heading(ln):
            out.append((ln, ""))
            continue
        words = len(text.split())
        if len(text) > (160 if loose else 120) or words > (20 if loose else 16):
            continue
        # Bold maths ("A, B", "ad∗", "i] A [i] B") is styled like a heading but is not one. A lone
        # bold capital set larger than body text is kept: index letters ("A", "B") are headings.
        letters = sum(c.isalpha() for c in text)
        if len(text.strip()) <= 2 and _vertical(ext, ln):
            continue
        index_letter = bool(re.fullmatch(r"[A-Z]", text.strip())) and ln.bold and ln.size >= body + 1.0
        if not index_letter and (
            letters < (2 if loose else 3) or (not loose and letters < 0.5 * len(text.replace(" ", "")))
        ):
            continue
        m = NUMBERING.match(text)
        styled = ln.size >= body + bump or (ln.bold and ln.size >= body - 0.3) or ln.i - 1 in labelled
        numbered = bool(m) and not text.rstrip().endswith((",", ";")) and words <= 14
        if not loose:
            if text.strip().lower() in labels or THEOREM.match(text):
                continue
            if numbered and not styled:
                num = m.group("num")
                numbered = bool(re.match(r"\d+\.\d+", num) or re.match(r"[A-Za-z]{3,}", num))
                numbered = numbered and not text.rstrip().endswith((".", "?", ":"))
            if styled and not numbered and ln.size < body + bump and ln.i - 1 not in labelled and _runs_on(ext, ln):
                continue
        if styled or numbered:
            out.append((ln, m.group("num").strip() if m else ""))
    # A split-off number or a bare label counts only when its title line is a candidate too.
    kept = {ln.i for ln, _ in out if ln.i not in split}
    return [(ln, num) for ln, num in out if (ln.i not in split and ln.i not in labelled) or ln.i + 1 in kept]


LABEL_ONLY = re.compile(
    r"^(?:(?:chapter|part|section|appendix|unit|lesson|module|book|article|schedule|annex|title|rule|clause|regulation"
    r"|teil|kapitel|abschnitt|unterabschnitt|titel|untertitel|buch|artikel|anlage|anhang"
    r"|chapitre|titre|partie|livre|annexe|sous-section)\s+(?:\d+[A-Za-z]?|[IVXLC]+|[A-Z]|premier|première|unique)"
    r"|§+\s*\d+[a-z]?)[.:]?$",
    re.I,
)


def _table_cells(ext: Extraction, skip: set[int]) -> set[int]:
    """Lines that share their row with two or more other lines on the page: cells of a table row
    ("Total", "£ million", "Males Females Total"), not headings. A heading has its row to itself,
    or shares it with one line of another column. Numbers alone and furniture don't count as
    neighbours (a heading's split-off number, a page number).

    On a two-column page, a numbered heading in one column often shares its row with an equation
    and its number, or a table, in the other ("4. EXPERIMENTS" beside "BatchNorm 4 | (l / 8) × 16
    × 32"): for a numbered line, lines of the other column count only in its own style. The
    abstract's heading is never a cell ("Abstract—We study ..." split by a font change)."""
    rows: dict[int, list[Line]] = defaultdict(list)
    for ln in ext.lines:
        if ln.i not in skip and not NUMBER_ALONE.match(ln.text.strip()):
            rows[ln.page].append(ln)
    out = set()
    for page, lines in rows.items():
        mid = _two_column_middle(ext, page, lines)
        lines.sort(key=lambda ln: ln.y0)
        for k, ln in enumerate(lines):
            row = [o for o in lines[max(0, k - 12): k + 13]
                   if o is not ln and abs(o.y0 - ln.y0) <= 2 and (o.x0 >= ln.x1 or o.x1 <= ln.x0)]
            if len(row) >= 2 and mid is not None and (ln.x1 <= mid or ln.x0 >= mid) and _numbered_title(ln.text):
                row = [o for o in row if (o.x1 <= mid) == (ln.x1 <= mid) and (o.x0 >= mid) == (ln.x0 >= mid)
                       or (o.bold == ln.bold and abs(o.size - ln.size) <= 0.5)]
            if len(row) >= 2 and not _abstract_heading(ln):
                out.add(ln.i)
    return out


def _numbered_title(text: str) -> bool:
    """A section number and a capitalised title ("4. EXPERIMENTS", "2.2. Proposed Problem")."""
    m = NUMBERING.match(text.strip())
    return bool(m) and text.strip()[m.end():][:1].isupper()


def _two_column_middle(ext: Extraction, page: int, lines: list[Line]) -> float | None:
    """The middle of the page if it is set in two columns (five or more text lines, each a quarter
    of the page wide, wholly on either side of the middle), else None."""
    pg = ext.pages[page - 1] if 0 < page <= len(ext.pages) and ext.pages[page - 1].n == page else None
    if pg is None or pg.rotation % 180:
        return None
    mid, wide = pg.origin_x + pg.width / 2, pg.width / 4
    left = sum(1 for ln in lines if ln.x1 <= mid and ln.x1 - ln.x0 >= wide)
    right = sum(1 for ln in lines if ln.x0 >= mid and ln.x1 - ln.x0 >= wide)
    return mid if left >= 5 and right >= 5 else None


def _label_text(text: str) -> str:
    """The line's text with letter spacing removed ("T e i l 1" -> "Teil 1"), for label matching."""
    t = text.strip()
    tokens = t.split()
    if len(tokens) >= 4 and all(len(x) == 1 for x in tokens):
        t = re.sub(r"(?<=[^\W\d_]) (?=[^\W\d_])", "", t)
    return t


def _label_lines(ext: Extraction, skip: set[int], body: float, bump: float) -> set[int]:
    """Bare structural labels ("CHAPITRE I", "Article premier", "T e i l 1") set on their own line
    above a title in bold, a larger size or capitals. The label is often in the body face, so
    typography alone keeps the title and loses the label; both lines become candidates, and
    _merge_wrapped joins them."""
    out = set()
    lines = ext.lines
    for ln in lines[:-1]:
        nxt = lines[ln.i + 1]
        if (ln.i in skip or nxt.i in skip or nxt.page != ln.page or not LABEL_ONLY.match(_label_text(ln.text))
                or len(nxt.text.split()) > 20 or LABEL_ONLY.match(_label_text(nxt.text))):
            continue
        if nxt.bold or nxt.size >= body + bump or (nxt.text.isupper() and not nxt.text.rstrip().endswith((".", ","))):
            out.add(ln.i)
    return out


def _merge_wrapped(cands: list[tuple[Line, str]], hints: DoclingHints | None = None) -> list[tuple[Line, str, str]]:
    """Join a heading that wraps onto a second line with the same style, and a
    bare "CHAPTER 10" label with the title line right after it. Lines that Docling
    puts in two different heading items stay two headings."""
    merged: list[tuple[Line, str, str]] = []
    last: Line | None = None  # the last line joined into merged[-1]
    for ln, num in cands:
        if merged and last is not None:
            prev, pnum, ptext = merged[-1]
            adjacent = ln.i == last.i + 1 and ln.page == prev.page and (hints is None or hints.same_item(last.i, ln.i))
            if adjacent and not num and ln.size == last.size and ln.bold == last.bold:
                merged[-1] = (prev, pnum, ptext + "\n" + ln.text)
                last = ln
                continue
            if adjacent and not num and "\n" not in ptext and LABEL_ONLY.match(_label_text(ptext)):
                merged[-1] = (prev, _label_text(ptext), ptext + "\n" + ln.text)
                last = ln
                continue
        merged.append((ln, num, ln.text))
        last = ln
    return merged


# The structural label an outline entry opens with, and its number: "Teil 2", "CHAPTER 1", "§ 12",
# "Artikel 5", "Annexe IV".
STRUCTURE_LABEL = re.compile(
    r"^(?P<kind>§+|(?:book|buch|livre|part|teil|partie|title|titel|titre|untertitel|chapter|kapitel|chapitre"
    r"|division|subdivision|section|abschnitt|unterabschnitt|subsection|sous-section|article|artikel|art\."
    r"|schedule|anlage|anhang|annex|annexe|appendix)\b)\s*\.?\s*(?P<n>\d+|[IVXLC]+\b|[A-Z]\b)",
    re.I,
)
LEADING_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")


# The usual nesting of structural labels, outermost first, used when an outline has no levels of its
# own. Annexes and schedules sit at the top, beside parts; plain numbers ("12 Duties") rank as articles.
LABEL_RANK = {
    **dict.fromkeys(("annex", "annexe", "anhang", "anlage", "schedule", "appendix"), 0),
    **dict.fromkeys(("book", "buch", "livre"), 1),
    **dict.fromkeys(("part", "teil", "partie"), 2),
    **dict.fromkeys(("title", "titre"), 3),
    **dict.fromkeys(("chapter", "kapitel", "chapitre"), 4),
    **dict.fromkeys(("division", "section", "abschnitt"), 5),
    **dict.fromkeys(("subdivision", "subsection", "sous-section", "unterabschnitt", "titel"), 6),
    "untertitel": 6.5,
    **dict.fromkeys(("article", "artikel", "art", "§", "#"), 7),
}


# Annexes, schedules and appendices take the level of the document's top kind (a UK Act's schedules sit
# beside its parts, an EU regulation's annexes beside its chapters).
TOP_KINDS = {"annex", "annexe", "anhang", "anlage", "schedule", "appendix"}


def _label_kind(text: str) -> tuple[str | None, str, int]:
    """(kind, number, extra depth) of a heading's text: ("teil", "2", 0) for "Teil 2 Allgemeines",
    ("#", "3.1", 1) for "3.1 Scope", (None, "", 0) for an unlabeled heading."""
    text = _label_text(text) if "\n" not in text else text
    m = STRUCTURE_LABEL.match(text)
    if m:
        kind = m.group("kind").lower().rstrip(".")
        return ("§" if kind.startswith("§") else kind), m.group("n").lower(), 0
    n = LEADING_NUMBER.match(text)
    if n:
        return "#", n.group(1), n.group(1).count(".")
    return None, "", 0


def _label_levels(texts: list[str], *, numbers_count: bool, min_share: float) -> list[int] | None:
    """Levels implied by the headings' structural labels, or None when the labels don't say enough:
    at least two kinds besides annexes, schedules and appendices (plain section numbers count as a
    kind only with `numbers_count`), and at least `min_share` of the headings labeled or numbered.
    A paper's numbered sections and "Appendix A" are therefore left to the other rules.

    Kinds are ranked by their usual nesting (part, chapter, section, article), corrected by the
    document itself: a kind whose numbering starts again at 1 after another kind's entry sits below
    that kind. A dotted number goes one level deeper per dot, annexes and schedules take the top
    kind's level, and an unlabeled heading sits just above the kind of the next labeled one (a UK
    Act's cross-heading above its sections, a regulation's title above its first chapter), or, when
    the next one is of the top kind, just below the kind of the previous labeled one."""
    parsed = [_label_kind(t) for t in texts]
    # A label that occurs once ("PART 385 OF THE CODE ...", a cross-reference that opens a line) says
    # nothing about the structure; its line counts as unlabeled.
    once = {k for k, _, _ in parsed if k not in TOP_KINDS and sum(x == k for x, _, _ in parsed) == 1}
    parsed = [(None, "", 0) if k in once else (k, n, d) for k, n, d in parsed]
    kinds = [k for k, _, _ in parsed]
    labeled = [k for k in kinds if k is not None]
    if (len({k for k in labeled if (numbers_count or k != "#") and k not in TOP_KINDS}) < 2
            or len(labeled) < min_share * len(kinds)):
        return None
    first = {k: kinds.index(k) for k in set(labeled)}
    order: list = sorted(set(labeled) - TOP_KINDS, key=lambda k: (LABEL_RANK.get(k, 7), labeled.count(k), first[k]))
    if not order:
        return None
    # Numbering that starts again after another kind's entry puts that kind above it. The most
    # common kind is the innermost one and is never put above another (its last entry before a
    # restart only means the label in between was missed).
    leaf = max(set(labeled) - TOP_KINDS, key=labeled.count)
    below: set[tuple[str, str]] = set()
    prev = None
    for i, (k, n, _) in enumerate(parsed):
        if k is None or k in TOP_KINDS:
            continue
        if prev is not None and prev not in (k, leaf) and n in ("1", "i", "a") and i != first[k]:
            below.add((prev, k))
        prev = k
    for _ in range(len(order)):
        moved = False
        for upper, lower in below:
            if (lower, upper) not in below and order.index(upper) > order.index(lower):
                order.remove(upper)
                order.insert(order.index(lower), upper)
                moved = True
        if not moved:
            break
    # An unlabeled heading ranks just above the kind of the next labeled one (a cross-heading above
    # its sections); when that is the top kind, just below the kind of the previous labeled one.
    outer = order[0]
    slot: list = []
    for i, k in enumerate(kinds):
        if k is not None:
            slot.append(None)
            continue
        b = next((x for x in kinds[i + 1:] if x is not None and x not in TOP_KINDS), None)
        p = next((x for x in reversed(kinds[:i]) if x is not None and x not in TOP_KINDS), None)
        slot.append(("before", b) if b is not None and (b != outer or p is None) else ("after", p) if p else None)
    for sl in sorted({x for x in slot if x is not None}, key=lambda x: (order.index(x[1]), x[0] == "after")):
        order.insert(order.index(sl[1]) + (sl[0] == "after"), sl)
    rank = {k: r + 1 for r, k in enumerate(order)}
    top = rank[outer]
    out = []
    for (k, _, d), sl in zip(parsed, slot, strict=True):
        if k in TOP_KINDS:
            out.append(top)
        elif k is not None:
            out.append(rank[k] + d)
        else:
            out.append(rank[sl] if sl is not None else 1)
    return out


def _flat_outline_levels(backbone: list, lines: list[Line]) -> None:
    """Give a one-level outline the levels its entries' own labels imply (`_label_levels`).

    Many PDFs carry a flat outline (German federal laws list every "Teil", "Kapitel" and "§" at
    one level), which says nothing about the hierarchy. Changes levels in place, and only when
    most entries open with a structural label or a section number."""
    if len(backbone) < 6 or len({a.level for a in backbone}) != 1:
        return
    texts = []
    for a in backbone:
        text = f"{a.number} {a.title}".strip() if a.number else a.title
        texts.append(text if _label_kind(text)[0] else lines[a.line].text.strip())
    levels = _label_levels(texts, numbers_count=True, min_share=0.5)
    if levels:
        for a, level in zip(backbone, levels, strict=True):
            a.level = level


Style = tuple[float, bool]


def _style_rank(s: Style) -> tuple[float, bool]:
    return (-s[0], not s[1])  # bigger first, bold before regular


def _levels_from_outline(styles: set[Style], known: dict[Style, int]) -> dict[Style, int]:
    """Give every heading style a level. Styles the outline uses take its
    level; others slot in by size: one below the nearest bigger known style,
    or one above the nearest smaller one."""
    order = sorted(styles | set(known), key=_style_rank)
    out: dict[Style, int] = {}
    for k, s in enumerate(order):
        if s in known:
            out[s] = known[s]
        elif k:
            out[s] = out[order[k - 1]] + 1
        else:
            smaller = next((known[t] for t in order if t in known), 2)
            out[s] = max(1, smaller - 1)
    return out


def _style_levels(heads: list[tuple[Line, str]]) -> dict[Style, int]:
    """Give every heading style a level when there is no outline.

    Numbered headings take their numbering depth ("2.1" -> 2). A style that two or more of them
    share, on two or more pages, takes their most common depth, and the other styles slot in
    around it by size (`_levels_from_outline`). An unnumbered heading in a section's style
    (References, Acknowledgements, an appendix "A Proofs") then sits beside the numbered
    sections, not one level below them.

    Otherwise, and when no such style holds top-level numbers (1, 2, 3), the levels are the
    styles' ranks: bigger first, bold before regular. Numbered lines on one page (a list of
    affiliations under the title) are not a document's numbering, and with only "2.1"-style
    numbers seen the top level is missing, so depth says nothing about the other styles."""
    depths: dict[Style, list[tuple[int, int]]] = defaultdict(list)
    for ln, num in heads:
        if re.fullmatch(r"\d+(?:\.\d+)*\.?", num):
            depths[(ln.size, ln.bold)].append((num.rstrip(".").count(".") + 1, ln.page))
    known = {}
    for s, seen in depths.items():
        ds = [d for d, _ in seen]
        if len(ds) >= 2 and len({p for _, p in seen}) >= 2:
            known[s] = min(set(ds), key=lambda d: (-ds.count(d), d))
    if 1 not in known.values():
        known = {}
    return _levels_from_outline({(ln.size, ln.bold) for ln, _ in heads}, known)


class RulesStrategy(Strategy):
    # The id predates the outline sources; kept so saved runs stay readable.
    id = "rules"
    label = "Free"
    description = (
        "No model, no cost. Uses the PDF's bookmarks or its table of contents as the outline when it has one, "
        "and font size, bold and numbering for everything else."
    )
    uses_llm = False

    async def run(self, ext: Extraction, ctx: Context) -> list[RawSection]:
        rules = self._rules(ext)
        backbone, source = outline_backbone(ext)
        if not backbone:
            ctx.progress(1.0, f"{len(rules)} headings found (typography and numbering)")
            return rules

        lines = ext.lines
        _flat_outline_levels(backbone, lines)
        by_line = {a.line: a for a in backbone}
        votes: dict[Style, list[int]] = defaultdict(list)
        for a in backbone:
            votes[(lines[a.line].size, lines[a.line].bold)].append(a.level)
        # A style's level is trusted when two or more outline entries use it,
        # or when it is bigger than every such style (a single chapter title).
        # One stray entry ("Introduction" set as a small run-in label) must
        # not drag every heading of that style up to its level.
        multi = [s for s, v in votes.items() if len(v) >= 2]
        top = min(multi, key=_style_rank) if multi else None
        known = {
            s: max(set(v), key=v.count)
            for s, v in votes.items()
            if len(v) >= 2 or top is None or _style_rank(s) < _style_rank(top)
        }
        abstract = {r.start_line for r in rules if _abstract_heading(lines[r.start_line])}
        rule_styles = {(lines[r.start_line].size, lines[r.start_line].bold) for r in rules if r.start_line not in abstract}
        level_of = _levels_from_outline(rule_styles, known)

        out = []
        for a in backbone:
            line, number, marker = a.line, a.number, lines[a.line].text
            if not number and a.line and split_number(ext, lines[a.line - 1]):
                # A bookmark without the number names the title line; the number sits before it.
                line, number = a.line - 1, lines[a.line - 1].text.strip()
                marker = f"{number} {marker}"
            out.append(RawSection(title=a.title, level=a.level, number=number, start_marker=marker[:160], start_line=line))
        covered = set(by_line) | {s.start_line for s in out}
        for r in rules:
            if r.start_line in covered or r.start_line + 1 in covered:
                continue
            ln = lines[r.start_line]
            dotted = re.fullmatch(r"\d+(?:\.\d+)*\.?", r.number)
            if r.start_line not in abstract:
                r.level = r.number.rstrip(".").count(".") + 1 if dotted else level_of[(ln.size, ln.bold)]
            out.append(r)
        out.sort(key=lambda s: s.start_line)
        _abstract_levels(out, abstract)
        ctx.progress(1.0, f"{len(out)} headings ({len(backbone)} from the {source}, {len(out) - len(backbone)} by typography)")
        return out

    def _rules(self, ext: Extraction) -> list[RawSection]:
        cands = _merge_wrapped(candidates(ext), hints_of(ext))
        # The abstract's heading does not take part in the style levels, so its style cannot shift
        # the other levels (see _abstract_levels).
        abstract = {ln.i for ln, _, _ in cands if _abstract_heading(ln)}
        style_level = _style_levels([(ln, num) for ln, num, _ in cands if ln.i not in abstract])
        # Legislation sets its structure in labels ("KAPITEL I", "Artikel 5"), often in the body face
        # or smaller, so typography ranks it upside down; when the labels are clear they set the levels.
        by_label = _label_levels([f"{num} {text}" if num and not text.startswith(num) else text.replace("\n", " ")
                                  for _, num, text in cands], numbers_count=False, min_share=0.3)
        out = []
        for k, (ln, num, text) in enumerate(cands):
            dotted = re.fullmatch(r"\d+(?:\.\d+)*\.?", num)
            if ln.i in abstract:
                level = 1  # set by _abstract_levels below
            elif by_label:
                level = by_label[k]
            else:
                level = num.rstrip(".").count(".") + 1 if dotted else style_level[(ln.size, ln.bold)]
            title = marker = text.replace("\n", " ")
            first, _, rest = text.partition("\n")
            if num and rest and _label_text(first) == num:
                title = rest.replace("\n", " ")  # "T e i l 1" / "Gemeinsame Bestimmungen"
            elif num and title.startswith(num):
                title = title[len(num):].strip()
            if ABSTRACT_RUNIN.match(title):
                title = re.match(r"\W*(\w+)", title).group(1)  # "Abstract", as printed
            out.append(RawSection(title=title, level=level, number=num, start_marker=marker[:160], start_line=ln.i))
        _abstract_levels(out, abstract)
        # Compress levels to 1..n so a document's top level is always 1.
        used = sorted({s.level for s in out})
        remap = {lv: i + 1 for i, lv in enumerate(used)}
        for s in out:
            s.level = remap[s.level]
        return out
