"""Heading detection from typography and numbering alone — no LLM, no cost.

The baseline every LLM strategy has to beat, and the candidate generator for
the "rules + LLM review" strategy.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from collections import defaultdict

from section_anything.docling_input import DoclingHints, hints_of
from section_anything.extract import Extraction, Line
from section_anything.outline_check import LETTER_SPACED
from section_anything.strategies.base import Context, RawSection, Strategy
from section_anything.structure import NUMBER_ALONE, TOC_TITLE, furniture_of, listing_of, outline_backbone, split_number, toc_of

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


WRAP_LEADING = 1.65  # baseline to baseline, in font sizes: a wrapped title's next line sits closer than this
WRAPPED_MAX = 3  # lines of a wrapped title


def _runs_on(ext: Extraction, ln: Line) -> bool:
    """The line continues into a lowercase line right below it: a bold term
    opening a paragraph or glossary entry, not a standalone heading. A title that
    wraps in its own style is not one (`_wrapped_title`)."""
    if ln.i + 1 >= len(ext.lines):
        return False
    nxt = ext.lines[ln.i + 1]
    return (nxt.page == ln.page and nxt.text[:1].islower() and (ln.y0 - nxt.y1) < ln.size
            and not _wrapped_title(ext, ln))


def _wrapped_title(ext: Extraction, ln: Line) -> bool:
    """`ln` is a line of a title that wraps: it and the lines set right under one another around it
    in its size and weight make two or three lines, and the line after them is set otherwise ("Remuneration
    policy for executive" / "directors", then the body text). A bold paragraph runs on for longer."""
    lines = ext.lines

    def under(a: Line, b: Line) -> bool:  # b is a's next line in the same style
        return (b.page == a.page and b.size == a.size and b.bold == a.bold
                and 0.5 * a.size < a.y0 - b.y0 <= WRAP_LEADING * max(a.size, 1.0))

    top = bottom = ln
    while top.i > 0 and under(lines[top.i - 1], top) and ln.i - top.i < WRAPPED_MAX:
        top = lines[top.i - 1]
    while bottom.i + 1 < len(lines) and under(bottom, lines[bottom.i + 1]) and bottom.i - top.i < WRAPPED_MAX:
        bottom = lines[bottom.i + 1]
    n = bottom.i - top.i + 1
    after = lines[bottom.i + 1] if bottom.i + 1 < len(lines) else None
    return 2 <= n <= WRAPPED_MAX and (after is None or not under(bottom, after))


# A multi-level section number ("2.3", "13.3.11"): no part starts with 0 except a lone 0 after the first.
SECTION_NUMBER = re.compile(r"[1-9]\d{0,2}(?:\.(?:0|[1-9]\d{0,2}))+")


def _few_letters(text: str, m: re.Match | None) -> bool:
    """Fewer letters than other characters: bold maths ("A, B", "ad∗"), figures, codes. A multi-level
    section number does not count against a capitalised title: "13.3.11 Hint" and "10.3 AVCs – JPS
    2015" are headings whose number is longer than their title. A plain number does ("31 March 2024
    £ million", "4 GeV2"), and so does a decimal ("0.040 Gyr", a figure's label) or a lower-case title
    ("2.5 µm, giving ...")."""
    if m is not None and SECTION_NUMBER.fullmatch(m.group("num").rstrip(".")):
        title = text[m.end():].strip()
        if title[:1].isupper():
            text = title
    return sum(c.isalpha() for c in text) < 0.5 * len(text.replace(" ", ""))


def _split_heading(ext: Extraction, ln: Line, loose: bool, skip: set[int], hints: DoclingHints | None) -> bool:
    """A number split off its title (`split_number`) whose title line is set in body type ("A." |
    "The Glucoamylase"), judged as the joined line would be: the pair reads as a numbered heading
    (strict mode: a multi-level number, "2.3"), the title starts with a capital, and it stands alone.
    The title and at most one line wrapped under it (same left edge, next baseline) do not end like a
    sentence and are followed by a gap wider than the next paragraph's line spacing, or by a page
    break. A numbered paragraph ("1.1 This is a companion paper, which ...") runs on at its line
    spacing and is left out."""
    lines = ext.lines
    t = lines[ln.i + 1]
    title = t.text.strip()
    joined = f"{ln.text.strip()} {title}"
    m = NUMBERING.match(joined)
    if (m is None or t.i in skip or CAPTION.match(title) or not title[:1].isupper()
            or (hints is not None and t.i in hints.body)
            or (not loose and not re.match(r"\d+\.\d+", m.group("num")))):
        return False
    block, j = [t], t.i + 1
    while j < len(lines):
        nx = lines[j]
        if not (nx.page == t.page and abs(nx.x0 - t.x0) <= 2 and nx.size == t.size and nx.bold == t.bold
                and 0 < block[-1].y0 - nx.y0 <= 1.6 * t.size):
            break
        block.append(nx)
        j += 1
        if len(block) > 2:
            return False
    end = block[-1].text.rstrip()
    if end.endswith((".", ",", ";", ":") if loose else (".", ",", ";", ":", "?")):
        return False
    if len(joined.split()) + sum(len(x.text.split()) for x in block[1:]) > 14:
        return False
    if j >= len(lines) or lines[j].page != t.page:
        return True
    nxt = lines[j]
    after = lines[j + 1] if j + 1 < len(lines) else None
    pitch = (nxt.y0 - after.y0 if after is not None and after.page == nxt.page and 0 < nxt.y0 - after.y0 <= 2.5 * nxt.size
             else 1.2 * t.size)
    return block[-1].y0 - nxt.y0 > 1.25 * max(pitch, t.size)


def _vertical(ext: Extraction, ln: Line) -> bool:
    """A one- or two-character line next to another such line: rotated text read letter by letter
    (the arXiv side stamp), not an index letter, which has entries between."""
    near = [ext.lines[j] for j in (ln.i - 1, ln.i + 1) if 0 <= j < len(ext.lines)]
    return any(x.page == ln.page and len(x.text.strip()) <= 2 for x in near)


# How a sentence, a quotation or a list item ends; a heading's last character is none of these.
SENTENCE_END = re.compile(r"[.,;:!?…”’\"'»]$")
# A schedule paragraph's number printed alone at the left margin ("9", "8A.", "12ZA").
PARAGRAPH_NUMBER = re.compile(r"[1-9]\d{0,2}[A-Z]{0,3}\.?")
# Space under a paragraph's own title, in font sizes: less than the most of a blank line that sets a
# cross-heading apart, more than a paragraph's line spacing leaves.
PARAGRAPH_TITLE_GAP = 0.5


def _neighbours(ext: Extraction, ln: Line) -> tuple[list[Line], Line | None, Line | None]:
    """The lines near `ln` on its page that are not furniture, and the nearest of them above and below it in
    its own column (overlapping it horizontally)."""
    lines = ext.lines
    furniture = furniture_of(ext)
    near = [o for o in lines[max(0, ln.i - 8): ln.i + 9] if o is not ln and o.page == ln.page and o.i not in furniture]
    mid = (ln.y0 + ln.y1) / 2
    col = [o for o in near if min(o.x1, ln.x1) > max(o.x0, ln.x0)]
    above = min((o for o in col if (o.y0 + o.y1) / 2 > mid), key=lambda o: o.y0 - ln.y1, default=None)
    below = min((o for o in col if (o.y0 + o.y1) / 2 < mid), key=lambda o: ln.y0 - o.y1, default=None)
    return near, above, below


# A paragraph number with an amendment mark run into it, set small and bold ("[F8115": note F81,
# paragraph 15).
AMENDED_NUMBER = re.compile(r"\[?F(\d{2,6})")


def _paragraph_number(ext: Extraction, ln: Line, below: Line | None) -> str | None:
    """The number of the paragraph that `ln` stands over, when it is printed alone at the left margin, left
    of `ln`, on the row of `below` (the line under `ln`, the paragraph's first line, in regular type): a UK
    Act's schedule paragraph under its own title ("Power to stop, board, divert and detain" over "2" |
    "(1) This paragraph applies ..."). None when there is no such paragraph. A section heading in bold, or a
    number run into its text ("6.12 Studies show ..."), is none. Nor is an entry of a contents list ("1" |
    "Implementation of the 1996, 2005 and 2007 Hague Conventions"): a paragraph's first line runs to the
    right margin or ends like a clause ("... is amended as follows.", "... the Theft Act 1968—").

    A number with an amendment mark run into it ("[F8115") marks such a paragraph too. Its number is the
    tail of the digits that follows the last plain paragraph number before it ("13", so "15" after the
    repealed 14), or "" when no tail fits."""
    if below is None or below.bold or below.italic or abs(below.size - ln.size) > 0.5:
        return None
    right = max(o.x1 for o in ext.lines[max(0, ln.i - 60): ln.i + 61] if o.page == ln.page)
    if not (below.x1 >= right - 2 * ln.size or below.text.rstrip()[-1:] in ".,;:—–-"):
        return None
    for o in ext.lines[max(0, min(ln.i, below.i) - 12): max(ln.i, below.i) + 13]:
        if (o is below or o.page != ln.page or o.italic or abs(o.y0 - below.y0) > 0.3 * ln.size
                or not (o.x1 < ln.x0 and 0 <= below.x0 - o.x1 <= 6 * ln.size)):
            continue
        t = o.text.strip()
        if PARAGRAPH_NUMBER.fullmatch(t) and not o.bold and abs(o.size - ln.size) <= 0.5:
            return t.rstrip(".")
        m = AMENDED_NUMBER.fullmatch(t)
        if m and o.size <= ln.size + 0.5:
            digits = m.group(1)
            prev = next((int(re.match(r"\d+", x.text.strip()).group()) for x in reversed(ext.lines[max(0, o.i - 400): o.i])
                         if abs(x.x0 - o.x0) <= 6 and not x.bold and PARAGRAPH_NUMBER.fullmatch(x.text.strip())
                         and not _in_margin(ext, x)), None)
            tail = next((str(prev + d) for d in (1, 2, 3) if prev is not None
                         and digits.endswith(str(prev + d)) and len(digits) > len(str(prev + d))), "")
            return tail
    return None


def _in_margin(ext: Extraction, ln: Line) -> bool:
    """`ln` sits in the top or bottom 6% of its page, where page numbers are."""
    pg = ext.pages[ln.page - 1] if 0 < ln.page <= len(ext.pages) else None
    return pg is not None and ((ln.y1 - pg.origin_y) > 0.94 * pg.height or (ln.y0 - pg.origin_y) < 0.06 * pg.height)


def _margins(ext: Extraction) -> dict[int, tuple[float, float]]:
    """Each page's text column: the leftmost start and rightmost end of its lines that are not furniture."""

    def make(ext: Extraction) -> dict[int, tuple[float, float]]:
        furniture = furniture_of(ext)
        out: dict[int, tuple[float, float]] = {}
        for o in ext.lines:
            if o.i not in furniture:
                a, b = out.get(o.page, (o.x0, o.x1))
                out[o.page] = (min(a, o.x0), max(b, o.x1))
        return out

    return ext.derived("text_margins", make)


def _centred(ext: Extraction, ln: Line) -> bool:
    """`ln` is set in the middle of its page's text column, away from both edges."""
    left, right = _margins(ext).get(ln.page, (ln.x0, ln.x1))
    width = right - left
    return (width > 0 and abs((ln.x0 + ln.x1) - (left + right)) / 2 <= 0.05 * width
            and ln.x0 - left >= 2 * ln.size and right - ln.x1 >= 2 * ln.size)


def _italic_block(ext: Extraction, ln: Line) -> list[Line]:
    """`ln` and the lines of an italic title wrapped with it: up to three lines in italics at its size and
    weight, each centred, set one under another at a wrapped line's spacing ("Human Trafficking and
    Exploitation (Criminal Justice and" / "Support for Victims) Act (Northern Ireland) 2015 (c. 2 (N.I.))").
    Just `ln` when it is not centred or has no such line next to it."""
    lines = ext.lines

    def wraps(a: Line, b: Line) -> bool:  # b is a's next line in the same title
        return (b.page == a.page and a.italic and b.italic and not a.bold and not b.bold and abs(b.size - a.size) <= 0.1
                and 0 < a.y0 - b.y0 <= WRAP_LEADING * a.size and _centred(ext, a) and _centred(ext, b))

    if not _centred(ext, ln):
        return [ln]
    block = [ln]
    while len(block) < WRAPPED_MAX and block[0].i > 0 and wraps(lines[block[0].i - 1], block[0]):
        block.insert(0, lines[block[0].i - 1])
    while len(block) < WRAPPED_MAX and block[-1].i + 1 < len(lines) and wraps(block[-1], lines[block[-1].i + 1]):
        block.append(lines[block[-1].i + 1])
    return block


def _italic_heading(ext: Extraction, ln: Line, body: float, skip: set[int]) -> bool:
    """A heading set in italics at body size, its only signal (a UK Act's cross-headings, "Types of
    sanction" above its sections): a line in italics, not bold, starting with a capital and not ending like
    a sentence, with its row to itself, set off by most of a blank line above and below from lines that
    are not italic, and not followed by a lowercase continuation. Emphasis inside a paragraph,
    quotations, captions, theorem statements and italic paragraphs have italic or close neighbours, share
    their row, or end like sentences. Lines in `skip` (contents lists without page numbers) are left out;
    furniture (running headers, often italic) is not a neighbour.

    A schedule paragraph's own title sits closer to its paragraph (`PARAGRAPH_TITLE_GAP`) when the
    paragraph's number stands alone at the margin on the row under it (`_paragraph_number`). An amendment
    mark run into the line ("[F64Human Trafficking ...") is read past. A centred title wrapped over two or
    three italic lines (`_italic_block`) is judged as one: its first line starts with a capital, its last
    does not end like a sentence, and the space is measured above the first and below the last."""
    if not ln.italic or ln.bold or abs(ln.size - body) > 0.5 or ln.i in skip:
        return False
    block = _italic_block(ext, ln)
    top, bottom = block[0], block[-1]
    if any(o.i in skip for o in block):
        return False
    first, last = AMENDMENT_MARK.sub("", top.text.strip()), bottom.text.strip()
    if not first[:1].isupper() or SENTENCE_END.search(last):
        return False
    lines = ext.lines
    _, above, _ = _neighbours(ext, top)
    _, _, below = _neighbours(ext, bottom)
    number = _paragraph_number(ext, bottom, below)
    nxt = lines[bottom.i + 1] if bottom.i + 1 < len(lines) and lines[bottom.i + 1].page == ln.page else None
    # The line read next continues the title, unless it is printed below the first line of the paragraph
    # the title stands over (a list under that line, read before it).
    if nxt is not None and nxt.text[:1].islower() and not (number is not None and nxt.y1 < below.y0):
        return False
    # A piece of a longer printed line (split at a formula): another line on its row close beside it.
    for x in block:
        near = _neighbours(ext, x)[0]
        if any(min(o.y1, x.y1) - max(o.y0, x.y0) > 0.5 * min(o.y1 - o.y0, x.y1 - x.y0)
               and max(o.x0 - x.x1, x.x0 - o.x1) < 0.5 * x.size for o in near):
            return False
    gap = 0.9 * ln.size
    if above is not None and (above.italic or above.y0 - top.y1 < gap):
        return False
    if below is None:
        return True
    space = bottom.y0 - below.y1
    return not below.italic and (space >= gap or (space >= PARAGRAPH_TITLE_GAP * ln.size and number is not None))


def _schedules_start(ext: Extraction) -> int | None:
    """The line of the document's first schedule label ("SCHEDULE 1"), outside running headers and
    contents lists; None without one."""

    def make(ext: Extraction) -> int:
        skip = furniture_of(ext) | toc_of(ext).lines
        return next((ln.i for ln in ext.lines if ln.i not in skip and LABEL_ONLY.match(_label_text(ln.text))
                     and _label_text(ln.text).lower().startswith("schedule")), -1)

    start = ext.derived("schedules_start", make)
    return None if start < 0 else start


def _group_heading(ext: Extraction, ln: Line, body: float, skip: set[int]) -> bool:
    """In a schedule, the italic heading of a group in a list of bodies or persons ("Local government" over
    "A county council in England or Wales." ...): an italic line at body size and regular weight, of at most
    twelve words, starting with a capital and not ending like a sentence, with its row to itself, set close
    above the group's first entry (a line in regular type starting with a capital) and either outdented from
    it or centred over it, with no italic line right above it. Groups like these sit only a few points
    apart, too close for `_italic_heading`."""
    start = _schedules_start(ext)
    t = AMENDMENT_MARK.sub("", ln.text.strip())
    if (start is None or ln.i <= start or not ln.italic or ln.bold or abs(ln.size - body) > 0.5 or ln.i in skip
            or not t[:1].isupper() or SENTENCE_END.search(t) or len(t.split()) > 12):
        return False
    near, above, below = _neighbours(ext, ln)
    if below is None or below.italic or below.bold or abs(below.size - ln.size) > 0.5:
        return False
    first = below.text.strip()
    if not (first[:1].isupper() or first[:1] == "[") or not 0 <= ln.y0 - below.y1 < 0.9 * ln.size:
        return False
    if above is not None and above.italic and above.y0 - ln.y1 < 0.9 * ln.size:
        return False
    if any(min(o.y1, ln.y1) - max(o.y0, ln.y0) > 0.5 * min(o.y1 - o.y0, ln.y1 - ln.y0) for o in near):
        return False  # shares its row
    return below.x0 >= ln.x0 + 1.5 * ln.size or (_centred(ext, ln) and not _centred(ext, below) and below.x0 < ln.x0)


# A UK Act's citation under its short title ("2015 CHAPTER 30", "2015 asp 12"), and the opening of its long
# title ("An Act to make provision about ...").
ACT_CITATION = re.compile(r"(?:1[89]|20)\d\d\s+(?:CHAPTER|asp|anaw|asc)\s+\d+", re.I)
LONG_TITLE = re.compile(r"An Act (?:to|for|respecting|relating to|establishing|providing for|concerning)\b")


def _act_title(ext: Extraction) -> set[int]:
    """A UK Act's title block below its short title: the citation line and the long title after it, from
    "An Act to ..." to the line that ends it with a full stop (the date of Royal Assent, "[26th March
    2015]", is set among its lines). The short title is the document's title; these lines are not
    headings. A long title set without a citation line (two or more lines in one type from "An Act to ...",
    in an Australian compilation) is one too, to its full stop or the end of its type."""

    def make(ext: Extraction) -> set[int]:
        lines, out = ext.lines, set()
        body = ext.body_size()
        for ln in lines:
            if ln.page > 10:
                break
            start = None
            if ACT_CITATION.fullmatch(ln.text.strip()):
                out.add(ln.i)
                start = next((x for x in lines[ln.i + 1: ln.i + 4] if LONG_TITLE.match(x.text.strip())), None)
            elif (LONG_TITLE.match(ln.text.strip()) and ln.i not in out and ln.size >= body and ln.i + 1 < len(lines)
                  and lines[ln.i + 1].page == ln.page and abs(lines[ln.i + 1].size - ln.size) <= 0.1):
                start = ln  # a long title set without a citation line above it (an Australian compilation)
            if start is None:
                continue
            prev = None
            for x in lines[start.i: start.i + 10]:
                if x.page != start.page or abs(x.size - start.size) > 0.1 or x.bold != start.bold:
                    break
                if prev is not None and (STRUCTURE_LABEL.match(x.text.strip()) or prev.y0 - x.y0 > 1.6 * x.size):
                    break  # the first Part's heading, set in the long title's type right under it
                out.add(x.i)
                prev = x
                if x.text.rstrip().endswith("."):
                    break
        return out

    return ext.derived("act_title", make)


def _quoted(text: str) -> bool:
    """The line opens a quotation it does not close, after a number or not ("“Slavery etc", "32A “Victims of
    slavery ..."): an amendment quoting another text's heading, not a heading of this one."""
    t = re.sub(r"^\s*\d+[A-Z]{0,3}\.?\s+", "", text.strip())
    return t[:1] in "“\"" and bool(t) and (t.count("“") > t.count("”") if t[0] == "“" else t.count('"') % 2 == 1)


# A defined term's line, not a heading: "Australian entity means:", "carries on business in Australia: see section 5".
DEFINITION_LEAD = re.compile(r"\bmeans\s*[:—–-]?\s*$|\bmeans:\s|^[^:]{2,60}:\s+see\b|\b(?:includes|is defined as)\s*:\s*$"
                             r"|^[a-z][a-z ,\-]{2,50}:\s+\w+.*\bif\s*:\s*$", re.I)
# The category a reference manual prints at the right of a definition's header line ("[Function]", "[Variable]").
DEFINITION_CATEGORY = re.compile(r"^\[[A-Z][A-Za-z ./-]{1,40}\]$")
LIST_MARK = re.compile(r"^\s*(\(?[a-z0-9]{1,3}[.)]|[•▪●◦■□►‣–—-])\s")


def _reference_entries(ext: Extraction) -> set[int]:
    """The header lines of a reference manual's definitions: a line with a bracketed category set at the right of its
    row ("integer index (string s, integer c)" ... "[Function]"), and the lines its argument list wraps onto (indented
    under it, in its size). They name a function, variable or command; the manual's headings are elsewhere."""

    def make(ext: Extraction) -> set[int]:
        lines, out = ext.lines, set()
        for c in lines:
            if not DEFINITION_CATEGORY.match(c.text.strip()):
                continue
            pg = ext.pages[c.page - 1] if 0 < c.page <= len(ext.pages) else None
            if pg is None or c.x0 < pg.origin_x + 0.55 * pg.width:
                continue
            row = [o for o in lines[max(0, c.i - 6): c.i + 7]
                   if o is not c and o.page == c.page and abs(o.y0 - c.y0) <= 3 and o.x1 <= c.x0]
            for d in row:
                out.add(d.i)
                j = d.i + 1
                while j < len(lines) and j - d.i <= 4:
                    n = lines[j]
                    if n.page == d.page and (n.i == c.i or DEFINITION_CATEGORY.match(n.text.strip())):
                        j += 1
                        continue
                    if (n.page == d.page and abs(n.size - d.size) <= 0.2 and n.x0 > d.x0 + 4
                            and 0 < d.y0 - n.y0 <= 3 * d.size):
                        out.add(n.i)  # the argument list wrapped onto the next line
                        j += 1
                        continue
                    break
        return out

    return ext.derived("reference_entries", make)


def _term_entries(ext: Extraction, body: float) -> set[int]:
    """Terms of a definition list (a glossary, a list of PEPs, a schema's members): a short line in body size, not
    numbered or labelled, that starts where the document's paragraphs start, over a definition whose first two lines
    start 10 pt or more further right, at one indent, in body type ("iterable" over "An object capable of returning its
    members ..."). A heading's paragraph starts at the margin, or indents its first line only."""

    def make(ext: Extraction) -> set[int]:
        counts: dict[float, int] = defaultdict(int)
        for ln in ext.lines:
            if len(ln.text.split()) > 10 and abs(ln.size - body) <= 0.5:
                counts[round(ln.x0 / 2) * 2] += 1
        if not counts:
            return set()
        start = max(counts, key=counts.get)  # where the document's paragraphs start
        lines, out = ext.lines, set()
        for ln in lines[:-2]:
            t = ln.text.strip()
            if (not t or abs(ln.x0 - start) > 2.5 or len(t.split()) > 8 or abs(ln.size - body) > 0.5 or LIST_MARK.match(t)
                    or NUMBERING.match(t) or LABEL_ONLY.match(_label_text(t))):
                continue
            a, b = lines[ln.i + 1], lines[ln.i + 2]
            if (a.page == b.page == ln.page and a.x0 >= ln.x0 + 10 and abs(b.x0 - a.x0) <= 2 and not a.bold
                    and abs(a.size - body) <= 0.6 and len(a.text.split()) >= 5 and not LIST_MARK.match(a.text)
                    and 0 < ln.y0 - a.y0 <= 2.2 * max(ln.size, 1.0)):
                out.add(ln.i)
        return out

    return ext.derived("term_entries", make)


# Names a cover page's own headings may carry.
COVER_HEADING = re.compile(r"^\W*(abstract|summary|executive summary|foreword|preface|introduction|contents|table of contents"
                           r"|acknowledg\w*|key findings|overview|about this \w+)\W*$", re.I)
COVER_MAX_LINES = 25
COVER_MAX_PROSE = 2


def _cover_lines(ext: Extraction) -> set[int]:
    """The lines of a cover page that are not headings: page 1, when it is sparse (at most 25 lines, at most two of more
    than 12 words) in a document of four pages or more whose pages are not (slides are), apart from its title block
    (the lines in its largest type), numbered or labelled lines, contents titles and the names a front page's headings
    carry ("Abstract", "Summary"). The rest are a cover's authors, dates, issue numbers and imprint ("Compilation date:",
    "7 November 2024", "A thesis submitted in partial fulfilment of ...")."""

    def make(ext: Extraction) -> set[int]:
        if len(ext.pages) < 4:
            return set()
        furniture = furniture_of(ext)
        per_page: dict[int, list[Line]] = defaultdict(list)
        for ln in ext.lines:
            if ln.i not in furniture and ln.text.strip():
                per_page[ln.page].append(ln)
        counts = sorted(len(v) for v in per_page.values())
        first = per_page.get(1, [])
        if (not first or not counts or counts[len(counts) // 2] <= COVER_MAX_LINES or len(first) > COVER_MAX_LINES
                or sum(1 for ln in first if len(ln.text.split()) > 12) > COVER_MAX_PROSE):
            return set()
        top = max(ln.size for ln in first)
        return {ln.i for ln in first if ln.size < top - 0.5 and not (
            NUMBERING.match(ln.text.strip()) or LABEL_ONLY.match(_label_text(ln.text)) or STRUCTURE_LABEL.match(ln.text.strip())
            or TOC_TITLE.match(ln.text.strip()) or COVER_HEADING.match(ln.text))}

    return ext.derived("cover_lines", make)


def _paragraph_line(ext: Extraction, ln: Line, excluded: set[int]) -> bool:
    """`ln` goes on from a paragraph in its own type: the line right above it, in its size, weight and slant, is too
    long for a heading (more than 16 words or 120 characters) or was left out as a defined term's line. A paragraph set
    slightly larger than the document's body type ends in short lines that are not headings."""
    if ln.i == 0:
        return False
    a = ext.lines[ln.i - 1]
    return (a.page == ln.page and abs(a.size - ln.size) <= 0.15 and a.bold == ln.bold and a.italic == ln.italic
            and 0 < a.y0 - ln.y0 <= 1.6 * max(ln.size, 1.0)
            and (len(a.text.split()) > 16 or len(a.text) > 120 or a.i in excluded))


def _numbered_paragraph(ext: Extraction, ln: Line, words: int) -> bool:
    """A numbered paragraph in body type ("7.64 For effective competition, consumers need to be able and willing to
    access" / "and assess key information ..."): ten words or more, run on into a line that starts in lower case."""
    if words < 10 or ln.i + 1 >= len(ext.lines):
        return False
    n = ext.lines[ln.i + 1]
    return (n.page == ln.page and abs(n.size - ln.size) <= 0.3 and n.text.strip()[:1].islower()
            and 0 < ln.y0 - n.y0 <= 2 * max(ln.size, 1.0))


def candidates(ext: Extraction, loose: bool = False) -> list[tuple[Line, str]]:
    """Lines that look like headings, with their numbering prefix ("" if none).
    `loose` widens recall for an LLM to filter afterwards; TOC lines are
    excluded either way.

    Strict mode also drops what our test corpus showed to be noise: numbered
    lines in body type ("1. Describe…", "a. E6 activates p53") unless the
    number is multi-level or keyword-led ("2.3", "Chapter 4"); repeated
    callout labels; and bold terms that run on into a paragraph.

    With Docling hints (`docling_input`), lines Docling labels as headings are candidates whatever
    their style, and strict mode drops lines it labels as body text, list items, captions or code,
    except the title line under a bare structural label.

    Both modes take a bare structural label ("CHAPITRE I", "PART 2", "SCHEDULE 1") together with the
    bold, larger or capitalised title line under it, however small or plain the label is set, and
    leave out the references printed beside a label (`side_notes`). Loose mode also keeps a bare
    division label with no such title line ("ANNEX II" above a numbered paragraph). Strict mode also
    drops the cells of table rows. In both, a line in italics at body size counts as styled when it is
    set apart like a heading (`_italic_heading`).

    A bare "§ 97" set bold or larger is a candidate although it has no letters. A section number
    split off a title set in body type counts when the pair stands as a numbered heading
    (`_split_heading`). Strict mode's letter-share test reads a capitalised title without its
    multi-level number (`_few_letters`).

    Strict mode also leaves out the entries of definition lists and reference manuals: a defined term's line
    ("Australian entity means:"), a definition's header line with its category at the right ("[Function]",
    `_reference_entries`), and a term over its indented definition (`_term_entries`); a cover page's lines below its
    title (`_cover_lines`); lines that go on from a paragraph in their own type (`_paragraph_line`); and numbered
    paragraphs in body type (`_numbered_paragraph`)."""
    body = ext.body_size()
    furniture = furniture_of(ext)
    toc = toc_of(ext).lines
    labels = set() if loose else _labels(ext, body)
    hints = hints_of(ext)
    bump = 0.4 if loose else 0.8
    out: list[tuple[Line, str]] = []
    split: set[int] = set()
    side = side_notes(ext)
    labelled = _label_lines(ext, furniture | toc, body, bump, side)
    # A title read before its label (`_titles_read_first`): its later lines go with its first one.
    read_first = {j: block[0] for lab, block in _titles_read_first(ext).items() if lab in labelled for j in block[1:]}
    titles = set(labelled.values()) | set(read_first)
    cells = set() if loose else _table_cells(ext, furniture | toc | side)
    listing = listing_of(ext) if any(ln.italic for ln in ext.lines) else set()
    skip = furniture | toc | side | cells
    split_titles: set[int] = set()
    act_title = set() if loose else _act_title(ext)
    entries = set() if loose else _reference_entries(ext) | _term_entries(ext, body) | _cover_lines(ext)
    defined: set[int] = set()  # defined terms' lines left out (their wrapped lines go with them)
    quote: Line | None = None  # the last line of an open quotation (`_quoted`) left out
    for ln in ext.lines:
        text = ln.text
        if ln.i in furniture or ln.i in toc or ln.i in side or ln.i in cells or CAPTION.match(text):
            continue
        if not loose and (ln.i in act_title or ln.i in entries):
            continue
        if not loose and abs(ln.size - body) <= 0.6 and DEFINITION_LEAD.search(text.strip()):
            defined.add(ln.i)
            continue
        if not loose and (ln.bold or ln.size >= body + bump) and _paragraph_line(ext, ln, defined):
            continue
        if not loose and (_quoted(text) or (quote is not None and ln.i == quote.i + 1 and ln.page == quote.page
                                            and (ln.size, ln.bold, ln.italic) == (quote.size, quote.bold, quote.italic))):
            # The quotation's lines in its style go with it, up to the one that closes it.
            quote = None if "”" in text else ln
            continue
        quote = None
        if ln.i in labelled or (loose and DIVISION_ONLY.match(_label_text(text))):
            out.append((ln, ""))  # joined with its title line by _merge_wrapped
            continue
        if split_number(ext, ln):
            # Joined with its title line by _merge_wrapped (Free) and LlmReviewStrategy._rows.
            out.append((ln, text.strip()))
            split.add(ln.i)
            if _split_heading(ext, ln, loose, skip, None if loose else hints):
                split_titles.add(ln.i + 1)
            continue
        if ln.i in split_titles:
            out.append((ln, ""))  # the title of a split-off number, judged with its number
            continue
        if hints is not None and ln.i in hints.headers:
            if loose or not (THEOREM.match(text) or text.strip().lower() in labels):
                m = NUMBERING.match(text)
                out.append((ln, m.group("num").strip() if m else ""))
            continue
        # Docling's body label does not override the title line under a bare label ("Teil 4" /
        # "Datenbanken der ..."), which with its label is a heading whatever Docling calls it, nor an
        # italic line set apart like a heading (`_italic_heading`).
        if (hints is not None and not loose and ln.i in hints.body and ln.i not in titles
                and not _italic_heading(ext, ln, body, listing)):
            continue
        styled = ln.size >= body + bump or (ln.bold and ln.size >= body - 0.3) or ln.i in titles
        # A bare "§ 97" set like a heading has no letters: a section with no title, or a repealed one.
        bare_label = styled and bool(LABEL_ONLY.match(_label_text(text)))
        if not re.search(r"[A-Za-z]", text) and not bare_label:
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
        m = NUMBERING.match(text)
        if not index_letter and not bare_label and (
            letters < (2 if loose else 3) or (not loose and _few_letters(text, m))
        ):
            continue
        # An italic line at body size set apart like a heading (`_italic_heading`) is styled too; it does
        # not make a bare label of a line without letters.
        styled = styled or _italic_heading(ext, ln, body, listing) or (not loose and _group_heading(ext, ln, body, listing))
        numbered = bool(m) and not text.rstrip().endswith((",", ";")) and words <= 14
        if not loose:
            if text.strip().lower() in labels or THEOREM.match(text):
                continue
            if numbered and not styled:
                num = m.group("num")
                # A label in body type opens a heading only when it is capitalised and its line does not run
                # on in lower case: "section 4 (soliciting murder)" in a list of offences and "Part 7 of the
                # Sentencing Code" wrapped from a sentence are references.
                label = bool(re.match(r"[A-Z][A-Za-z]{2,}", num)) and not text[m.end():].lstrip()[:1].islower()
                numbered = bool(re.match(r"\d+\.\d+", num) or label)
                numbered = numbered and not text.rstrip().endswith((".", "?", ":")) and not _numbered_paragraph(ext, ln, words)
            if styled and not numbered and ln.size < body + bump and ln.i not in titles and _runs_on(ext, ln):
                continue
        if styled or numbered:
            out.append((ln, m.group("num").strip() if m else ""))
    # A split-off number, or (strict mode) a bare label, counts only when its title line is a
    # candidate too.
    kept = {ln.i for ln, _ in out if ln.i not in split}

    def stays(ln: Line) -> bool:
        if ln.i in split:
            return ln.i + 1 in kept
        if ln.i in read_first:
            return read_first[ln.i] in kept
        return loose or ln.i not in labelled or labelled[ln.i] in kept

    return [(ln, num) for ln, num in out if stays(ln)]


LABEL_ONLY = re.compile(
    r"^(?:(?:chapter|part|section|appendix|unit|lesson|module|book|article|schedule|annex|title|rule|clause|regulation"
    r"|teil|kapitel|abschnitt|unterabschnitt|titel|untertitel|buch|artikel|anlage|anhang"
    r"|chapitre|titre|partie|livre|annexe|sous-section)\s+(?:\d+[A-Za-z]?|[IVXLC]+|[A-Z]|premier|première|unique)"
    r"|§+\s*\d+[a-z]?)[.:]?$",
    re.I,
)


# The bare labels of larger divisions. Not "Section", "Article" or "§": their bare numbers also fill
# contents lists and cross-reference columns.
DIVISION_ONLY = re.compile(
    r"^(?:part|chapter|schedule|annex|appendix|title|book|division|teil|kapitel|buch|titel|anlage|anhang"
    r"|chapitre|titre|partie|livre|annexe)\s+(?:\d+[A-Za-z]?|[IVXLC]+|[A-Z]|premier|première|unique)[.:]?$",
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


# The mark of an amendment run into the start of a line in a revised UK Act ("[F76SCHEDULE 4A",
# "[F64Human Trafficking ..."): "[F", the note's number, and the inserted text, which starts with a capital.
AMENDMENT_MARK = re.compile(r"^\[F\d+(?=[A-Z][A-Za-z])")


def _label_text(text: str) -> str:
    """The line's text with letter spacing removed ("T e i l 1" -> "Teil 1") and without an amendment mark
    run into it ("[F76SCHEDULE 4A" -> "SCHEDULE 4A"), for label matching."""
    t = AMENDMENT_MARK.sub("", text.strip())
    tokens = t.split()
    if len(tokens) >= 4 and all(len(x) == 1 for x in tokens):
        t = re.sub(r"(?<=[^\W\d_]) (?=[^\W\d_])", "", t)
    return t


def _label_lines(ext: Extraction, skip: set[int], body: float, bump: float, side: set[int]) -> dict[int, int]:
    """Bare structural labels ("CHAPITRE I", "Article premier", "T e i l 1") set on their own line
    above a title in bold, a larger size or capitals, as {label line: title line}. The label is
    often in the body face, so typography alone keeps the title and loses the label; both lines
    become candidates, and _merge_wrapped joins them. A reference printed beside the label
    (`side_notes`) is passed over: the title is the line after it. A title printed under its label
    but read before it is the label's title too (`_titles_read_first`)."""
    out = {}
    lines = ext.lines
    first = _titles_read_first(ext)
    for ln in lines[:-1]:
        if ln.i in first and ln.i not in skip and first[ln.i][0] not in skip:
            out[ln.i] = first[ln.i][0]
            continue
        j = ln.i + 1
        while j < len(lines) - 1 and j in side:
            j += 1
        nxt = lines[j]
        if (ln.i in skip or ln.i in side or nxt.i in skip or nxt.i in side or nxt.page != ln.page
                or not LABEL_ONLY.match(_label_text(ln.text))
                or len(nxt.text.split()) > 20 or LABEL_ONLY.match(_label_text(nxt.text))):
            continue
        if nxt.bold or nxt.size >= body + bump or (nxt.text.isupper() and not nxt.text.rstrip().endswith((".", ","))):
            out[ln.i] = nxt.i
    return out


def _titles_read_first(ext: Extraction) -> dict[int, list[int]]:
    """Bare labels whose title is printed right under them but read just before them, as {label line: the
    title's lines}: the extractor's reading order can put "PUBLIC AUTHORITIES UNDER A DUTY ..." before
    "SCHEDULE 3". The title (one to three lines set under one another in one style, read just before the
    label) is set in bold or capitals, starts under the label within two and a half of its sizes and
    overlaps it across, and the line after the label (side notes aside) is not closer under it."""

    def make(ext: Extraction) -> dict[int, list[int]]:
        lines, body = ext.lines, ext.body_size()
        side = side_notes(ext)
        skip = furniture_of(ext) | toc_of(ext).lines | side

        def across(a: Line, b: Line) -> bool:
            return min(a.x1, b.x1) > max(a.x0, b.x0)

        out = {}
        for ln in lines[1:]:
            prev = lines[ln.i - 1]
            if (ln.i in skip or prev.i in skip or prev.page != ln.page or not LABEL_ONLY.match(_label_text(ln.text))
                    or LABEL_ONLY.match(_label_text(prev.text)) or len(prev.text.split()) > 20):
                continue
            block = [prev]
            while len(block) < WRAPPED_MAX and block[0].i > 0:
                up = lines[block[0].i - 1]
                if not (up.page == prev.page and up.i not in skip and up.size == prev.size and up.bold == prev.bold
                        and 0 < up.y0 - block[0].y0 <= WRAP_LEADING * up.size and across(up, block[0])):
                    break
                block.insert(0, up)
            top = block[0]
            under = ln.y0 - top.y1
            if not (0 <= under <= 2.5 * ln.size and across(top, ln)):
                continue
            if not (top.bold or top.size >= body + 0.8 or (top.text.isupper() and not top.text.rstrip().endswith((".", ",")))):
                continue
            j = ln.i + 1
            while j < len(lines) - 1 and j in side:
                j += 1
            nxt = lines[j] if j < len(lines) else None
            if nxt is not None and nxt.page == ln.page and 0 <= ln.y0 - nxt.y1 <= under:
                continue
            out[ln.i] = [b.i for b in block]
        return out

    return ext.derived("titles_read_first", make)


def side_notes(ext: Extraction) -> set[int]:
    """References printed smaller beside a bare structural label, on its row and to its right: a UK
    Act sets the section that brings a schedule in next to the schedule's label ("SCHEDULE 1" ...
    "Section 5"). They belong to the label's heading block; they are neither headings nor the
    label's title, and the heading starts at the label."""
    skip = furniture_of(ext) | toc_of(ext).lines
    by_page: dict[int, list[Line]] = defaultdict(list)
    for ln in ext.lines:
        if ln.i not in skip:
            by_page[ln.page].append(ln)
    out = set()
    for lab in ext.lines:
        if lab.i in skip or not LABEL_ONLY.match(_label_text(lab.text)):
            continue
        # On the label's row: its top, or (a label with an amendment mark, "[F76SCHEDULE 4A", is set taller)
        # its middle, within 3 points.
        mid = (lab.y0 + lab.y1) / 2
        out |= {
            o.i for o in by_page[lab.page]
            if (abs(o.y0 - lab.y0) <= 3 or abs((o.y0 + o.y1) / 2 - mid) <= 3) and o.x0 >= lab.x1 + 10
            and o.size <= lab.size - 1 and len(o.text.split()) <= 6 and re.search(r"\d", o.text)
        }
    return out


def _printed(ext: Extraction, first: Line, text: str, side: set[int]) -> str:
    """The text of a heading joined by _merge_wrapped as printed, in reading order: with the side note
    that sits between a label and its title ("SCHEDULE 1 Section 5 INFORMATION ..."), so that the
    start marker is found where the heading is."""
    parts, j, need = [], first.i, text.count("\n") + 1
    while need and j < len(ext.lines):
        parts.append(ext.lines[j].text)
        need -= j not in side
        j += 1
    return " ".join(parts)


def _merge_wrapped(cands: list[tuple[Line, str]], hints: DoclingHints | None = None,
                   side: set[int] = frozenset(), ext: Extraction | None = None) -> list[tuple[Line, str, str]]:
    """Join a heading that wraps onto a second line with the same style, and a
    bare "CHAPTER 10" label with the title line right after it (or after the reference
    printed beside the label, `side_notes`). Lines that Docling puts in two different
    heading items stay two headings, except a bare label and its title: Docling often
    gives each its own item ("Article 3" / "Objet"), which as two headings matches
    neither ("Article 3 Objet"). A bare label never takes another bare label as its title, nor continues
    an italic heading before it ("Other" / "SCHEDULE 5"). Given the extraction, a label read just after its title (`_titles_read_first`) joins it too."""
    # The title's last line -> (its label, its first line).
    read_first = {t[-1]: (lab, t[0]) for lab, t in _titles_read_first(ext).items()} if ext is not None else {}
    merged: list[tuple[Line, str, str]] = []
    last: Line | None = None  # the last line joined into merged[-1]
    for ln, num in cands:
        if merged and last is not None:
            prev, pnum, ptext = merged[-1]
            if read_first.get(last.i) == (ln.i, prev.i) and not num:
                merged[-1] = (prev, _label_text(ln.text), ln.text + "\n" + ptext)
                last = None  # label and title make the whole heading
                continue
            next_line = ln.i > last.i and all(j in side for j in range(last.i + 1, ln.i)) and ln.page == prev.page
            if next_line and not num and ln.size == last.size and ln.bold == last.bold and (
                    hints is None or hints.same_item(last.i, ln.i)) and not (
                    last.italic != ln.italic and LABEL_ONLY.match(_label_text(ln.text))):
                merged[-1] = (prev, pnum, ptext + "\n" + ln.text)
                last = ln
                continue
            if (next_line and not num and "\n" not in ptext and LABEL_ONLY.match(_label_text(ptext))
                    and not LABEL_ONLY.match(_label_text(ln.text))):
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
# A section number, with the capital letters of an inserted section ("16A", "20WA") after a plain number.
LEADING_NUMBER = re.compile(r"^(\d+[A-Z]{0,3}(?:\.\d+)*)\.?\s+\S")


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


def _label_levels(texts: list[str], *, numbers_count: bool, min_share: float,
                  styles: list[Style] | None = None) -> list[int] | None:
    """Levels implied by the headings' structural labels, or None when the labels don't say enough:
    at least two kinds besides annexes, schedules and appendices (plain section numbers count as a
    kind only with `numbers_count`), and at least `min_share` of the headings labeled or numbered.
    A paper's numbered sections and "Appendix A" are therefore left to the other rules.

    Kinds are ranked by their usual nesting (part, chapter, section, article), corrected by the
    document itself: a kind whose numbering starts again at 1 after another kind's entry sits below
    that kind. A dotted number goes one level deeper per dot, annexes and schedules take the top
    kind's level, and an unlabeled heading sits just above the kind of the next labeled one (a UK
    Act's cross-heading above its sections, a regulation's title above its first chapter), or, when
    the next one is of the top kind, just below the kind of the previous labeled one. Given the headings' `styles`, an
    unlabeled heading that no labeled one follows (a compilation's endnotes, back matter) takes the level of the labeled
    kind set in its style, when there is one, instead of going under the last labeled heading."""
    parsed = [_label_kind(t) for t in texts]
    # A label that occurs once ("PART 385 OF THE CODE ...", a cross-reference that opens a line) says
    # nothing about the structure; its line counts as unlabeled.
    once = {k for k, _, _ in parsed if k not in TOP_KINDS and sum(x == k for x, _, _ in parsed) == 1}
    parsed = [(None, "", 0) if k in once else (k, n, d) for k, n, d in parsed]
    kinds = [k for k, _, _ in parsed]
    labeled = [k for k in kinds if k is not None]
    # An Act with schedules is set in labels even where its sections carry bare numbers ("1 Slavery ..."
    # under "PART 1"): its numbered sections are a kind of their own.
    numbers_count = numbers_count or "schedule" in labeled
    if (len({k for k in labeled if (numbers_count or k != "#") and k not in TOP_KINDS}) < 2
            or len(labeled) < min_share * len(kinds)):
        return None
    first = {k: kinds.index(k) for k in set(labeled)}
    order: list = sorted(set(labeled) - TOP_KINDS, key=lambda k: (LABEL_RANK.get(k, 7), labeled.count(k), first[k]))
    if not order:
        return None
    # Numbering that starts again after another kind's entry puts that kind above it. The most
    # common kind is the innermost one and is never put above another (its last entry before a
    # restart only means the label in between was missed). On a tie, the kind seen first wins, so the
    # result does not depend on PYTHONHASHSEED (it did on a US CFR part, F065).
    leaf = max(set(labeled) - TOP_KINDS, key=lambda k: (labeled.count(k), -first[k]))
    below: set[tuple[str, str]] = set()
    prev = None
    for i, (k, n, _) in enumerate(parsed):
        if k in TOP_KINDS:
            prev = None  # a schedule numbers its own Parts from 1: no sign of where they rank
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
        if b is None and styles is not None:
            same = [kinds[j] for j in range(len(kinds)) if kinds[j] is not None and kinds[j] not in TOP_KINDS
                    and abs(styles[j][0] - styles[i][0]) <= 0.5 and styles[j][1] == styles[i][1]]
            if same:
                slot.append(("same", max(set(same), key=same.count)))
                continue
        slot.append(("before", b) if b is not None and (b != outer or p is None) else ("after", p) if p else None)
    for sl in sorted({x for x in slot if x is not None and x[0] != "same"}, key=lambda x: (order.index(x[1]), x[0] == "after")):
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
            out.append(1 if sl is None else rank[sl[1]] if sl[0] == "same" else rank[sl])
    # The headings inside an annex or schedule (from its label to the next one) nest under it, in the order
    # the ranks give them: a schedule's Part one level below the schedule, the paragraphs' titles under
    # the Part, or under the schedule itself when it has no Parts. The levels outside them close up first,
    # so the body and the schedules count their levels alike (Part, cross-heading, section: 1, 2, 3).
    tops = [i for i, k in enumerate(kinds) if k in TOP_KINDS]
    if tops:
        inside = {i for a, b in zip(tops, [*tops[1:], len(out)], strict=True) for i in range(a + 1, b)}
        outer_levels = {lv: r + 1 for r, lv in enumerate(sorted({out[i] for i in range(len(out)) if i not in inside}))}
        top = outer_levels[top]
        for i in range(len(out)):
            if i not in inside:
                out[i] = outer_levels[out[i]]
        for a, b in zip(tops, [*tops[1:], len(out)], strict=True):
            inner = {lv: r for r, lv in enumerate(sorted(set(out[a + 1:b])))}
            for i in range(a + 1, b):
                out[i] = top + 1 + inner[out[i]]
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


def _style(ln: Line, body: float) -> Style:
    """A heading line's style for levels: (size, bold). A line in italics at body size and regular weight
    ranks below every other style: italics at body size mark a document's lowest headings (a report's
    minor headings, a paper's subsections). A UK Act's cross-headings take their level from its labels
    (`_label_levels`), or in an Act without Parts or Chapters from the sections under them (`_cross_headings`)."""
    return (0.0, False) if ln.italic and not ln.bold and abs(ln.size - body) <= 0.5 else (ln.size, ln.bold)


SECTION_NUMBER_ONLY = re.compile(r"\d+(?:\.\d+)*\.?")


def _cross_headings(ext: Extraction, cands: list[tuple[Line, str, str]], body: float, skip: set[int]) -> set[int]:
    """Indexes into `cands` of italic headings at body size set directly above a numbered heading in bold or
    larger type, with no text between them (lines in `skip`, running headers and side notes, aside): a UK
    Act's cross-headings ("Types of sanction" over sections 3 to 8). They head the sections that follow them,
    however the styles rank. A numbered paragraph in body type ("6.12 There is wide-ranging evidence ...")
    is not a section, and two at least: one such line is no pattern."""
    out = set()
    for k, (ln, _num, _text) in enumerate(cands[:-1]):
        nxt, num = cands[k + 1][0], cands[k + 1][1]
        if (_style(ln, body) == (0.0, False) and SECTION_NUMBER_ONLY.fullmatch(num) and nxt.page - ln.page in (0, 1)
                and (nxt.bold or nxt.size > body + 0.5) and all(j in skip for j in range(ln.i + 1, nxt.i))):
            out.add(k)
    return out if len(out) >= 2 else set()


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


def _style_levels(heads: list[tuple[Line, str]], body: float) -> dict[Style, int]:
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
    known, _mixed = _known_depths(heads, body)
    return _levels_from_outline({_style(ln, body) for ln, _ in heads}, known)


def _known_depths(heads: list[tuple[Line, str]], body: float,
                  depths: list[int | None] | None = None) -> tuple[dict[Style, int], set[Style]]:
    """The numbering depth each heading style stands for (`_style_levels`), and the styles that numbered headings
    of several depths share (fewer than three quarters at the style's depth): such a style says little about
    an unnumbered heading set in it ("2.1" and "2.1.1" in one style).

    `depths`, one per heading, replaces the depth read from each number (None for a heading that takes no part:
    unnumbered, or numbered outside the document's running numbers, `_numbering_spine`)."""
    seen_at: dict[Style, list[tuple[int, int]]] = defaultdict(list)
    for k, (ln, num) in enumerate(heads):
        if depths is not None:
            if depths[k] is not None:
                seen_at[_style(ln, body)].append((depths[k], ln.page))
        elif re.fullmatch(r"\d+(?:\.\d+)*\.?", num):
            seen_at[_style(ln, body)].append((num.rstrip(".").count(".") + 1, ln.page))
    known: dict[Style, int] = {}
    mixed: set[Style] = set()
    for s, seen in seen_at.items():
        ds = [d for d, _ in seen]
        if len(ds) >= 2 and len({p for _, p in seen}) >= 2:
            top = min(set(ds), key=lambda d: (-ds.count(d), d))
            known[s] = top
            if 4 * ds.count(top) < 3 * len(ds):
                mixed.add(s)
    if 1 not in known.values():
        known = {}
    return known, mixed


_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}


def _label_number(num: str) -> tuple[str, int] | None:
    """("chapter", 3) for a heading numbered "Chapter 3" or "CHAPTER III"; None for any other numbering and for
    annexes, schedules and appendices, which stand outside a document's running section numbers."""
    m = STRUCTURE_LABEL.match(num)
    if not m or m.group("kind").lower().rstrip(".") in TOP_KINDS or m.group("kind").startswith("§"):
        return None
    n = m.group("n").lower()
    if n.isdigit():
        return m.group("kind").lower().rstrip("."), int(n)
    if len(n) == 1 and n not in _ROMAN:
        return None
    vals = [_ROMAN[ch] for ch in n]
    return m.group("kind").lower().rstrip("."), sum(-v if v < nxt else v for v, nxt in zip(vals, [*vals[1:], 0], strict=True))


def _carries_on(prev: tuple[int, ...], nxt: tuple[int, ...], skip: int = 1) -> int:
    """How many levels of numbered sections stay open from the section numbered `prev` to the one numbered `nxt`,
    when `nxt` carries the same numbering on inside the same top-level section: 2 from 3.2.1 to 3.2.2 (3 and 3.2
    stay open), 1 from 3.1.2 to 3.2 and from 3 to 3.1. 0 when it does not (a new top-level number, a number
    that goes back, or one that skips more than `skip` numbers: one missed heading is allowed for)."""
    k = len(nxt) - 1
    if k < 1 or k > len(prev) or nxt[:k] != prev[:k]:
        return 0
    if k == len(prev):
        return k if nxt[k] <= 1 + skip else 0
    return k if 1 <= nxt[k] - prev[k] <= 1 + skip else 0


def _numbering_spine(nums: list[str]) -> list[tuple[int, ...] | None]:
    """Each heading's place in the document's running section numbers, or None when it has none.

    A multi-level number ("3.2", "3.2.1") is its own place. A single number ("3") is one too, unless the
    multi-level numbers before and after it run on inside one top-level section (`_carries_on`: "1." between 1.2
    and 1.3, a numbered list item or a line number of a listing): that section is still open, so the single
    number is not the document's next top-level section. A labeled heading ("Chapter 3") takes the place (3,)
    when the multi-level numbers under it start with its number ("3.1"), provided the document's headings of
    that kind do so twice or more and at least half of the times a multi-level number follows them: the label
    is then the numbering's top level."""
    paths: list[tuple[int, ...] | None] = []
    for num in nums:
        paths.append(tuple(int(x) for x in num.rstrip(".").split(".")) if SECTION_NUMBER_ONLY.fullmatch(num) else None)
    deep = [i for i, p in enumerate(paths) if p is not None and len(p) >= 2]
    labels = {i: lab for i, num in enumerate(nums) if paths[i] is None and (lab := _label_number(num))}
    checked: dict[str, list[tuple[int, bool]]] = defaultdict(list)
    for i, (kind, n) in labels.items():
        for j in range(i + 1, len(nums)):
            if j in labels and labels[j][0] == kind:
                break
            if paths[j] is not None and len(paths[j]) >= 2:
                checked[kind].append((i, paths[j][0] == n))
                break
    for seen in checked.values():
        good = [i for i, ok in seen if ok]
        if len(good) >= 2 and 2 * len(good) >= len(seen):
            for i in good:
                paths[i] = (labels[i][1],)
    out = list(paths)
    for i, p in enumerate(paths):
        if p is None or len(p) != 1:
            continue
        at = bisect_left(deep, i)
        if 0 < at < len(deep) and _carries_on(paths[deep[at - 1]], paths[deep[at]]):
            out[i] = None
    return out


def _keep_sections_open(levels: list[int], spine: list[tuple[int, ...] | None], fixed: set[int],
                        unsure: set[int] = frozenset()) -> None:
    """A heading cannot close a numbered section that the next numbered heading shows to be still open.

    Between two headings of the running numbers of which the second carries the first's numbering on
    (`_carries_on`: 3.2.1 and 3.2.2 leave 3 and 3.2 open), a heading whose level would close one of the open
    sections (an unnumbered heading in a style ranked with the chapters, a numbered list item) goes under the
    first of the two instead, one level below it, provided the open section has a numbered heading of its own
    (3.2 before 3.2.1 and 3.2.2). So does a heading there whose style says little about its
    level (`unsure`: a style that numbered headings of several depths share), unless a number is skipped between
    the two. The headings between the two keep
    their order of levels, so a smaller heading after it stays below it. Levels change in place; the headings
    in `fixed` are left alone."""
    idx = [i for i, p in enumerate(spine) if p is not None]
    seen: set[tuple[int, ...]] = set()
    for a, b in zip(idx, idx[1:], strict=False):
        seen.add(spine[a])
        # The two numbered headings' own levels must agree with their numbers (they do when the numbering
        # depth set them; labels may have set them otherwise). And the open section must have a heading of
        # its own: "26.1" and "26.2" with no "26" above them are a statute's inserted sections or a
        # regulation's "part.section" numbers, flat numbers that a group heading may well stand between.
        if (not _carries_on(spine[a], spine[b]) or levels[b] - levels[a] != len(spine[b]) - len(spine[a])
                or spine[b][:-1] not in seen):
            continue
        still_open = levels[b] - 1
        gap = [i for i in range(a + 1, b) if i not in fixed]
        # Where a number is skipped (4.5.2 then 4.5.4), a heading in between may be the skipped section with its
        # number unread: its style still counts.
        moves = [i for i in gap if levels[i] <= still_open or (i in unsure and _carries_on(spine[a], spine[b], skip=0))]
        if not moves:
            continue
        low = min(levels[i] for i in moves)
        order = sorted({levels[i] for i in gap if levels[i] >= low})
        for i in gap:
            if levels[i] >= low:
                levels[i] = max(levels[i], levels[a] + 1 + order.index(levels[i]))


def _running_levels(heads: list[tuple[Line, str, str]], body: float, fixed: set[int]) -> list[int]:
    """Levels from the document's running section numbers and its heading styles, for a document whose labels
    do not set them (`_label_levels`). `heads`: (first line, numbering, text) per heading; `fixed`: indexes of
    headings that take no part (the abstract).

    A heading on the running numbers (`_numbering_spine`) takes its numbering depth; every other heading takes
    its style's level (`_style_levels`, from the depths of the numbered headings set in each style). Last, no
    heading closes a numbered section that is still open (`_keep_sections_open`)."""
    # A label read as part of the title ("CHAPTER 3 METHODS" with no numbering of its own) counts as the numbering.
    nums = [num or (text.partition("\n")[0] if _label_number(text) else "") for _, num, text in heads]
    spine = _numbering_spine(nums)
    live = [k for k in range(len(heads)) if k not in fixed]
    pairs = [(heads[k][0], heads[k][1]) for k in live]
    known, mixed = _known_depths(pairs, body, [len(spine[k]) if spine[k] else None for k in live])
    style_level = _levels_from_outline({_style(ln, body) for ln, _ in pairs}, known)
    levels = [len(p) if p else style_level.get(_style(ln, body), 1) for (ln, _, _), p in zip(heads, spine, strict=True)]
    unsure = {k for k in live if spine[k] is None and not heads[k][1] and _style(heads[k][0], body) in mixed}
    _keep_sections_open(levels, spine, fixed, unsure)
    return levels


def _title_line(cands: list[tuple[Line, str, str]]) -> int | None:
    """Index of the document's own title among the candidates, as `pipeline.mark_doc_title` will flag it:
    the first, on page 1, unnumbered, and set at least 1 pt larger than every other candidate."""
    if len(cands) < 2 or cands[0][0].page != 1 or cands[0][1]:
        return None
    return 0 if cands[0][0].size >= max(ln.size for ln, _, _ in cands[1:]) + 1.0 else None


def _heading_parts(ext: Extraction, ln: Line, num: str, text: str, side: set[int], body: float) -> tuple[str, str, str]:
    """A merged heading (`_merge_wrapped`: first line `ln`, numbering `num`, its lines joined by "\\n") as Free
    reports it: (number, title without the number, the heading as printed for the start marker)."""
    title = text.replace("\n", " ")
    marker = _printed(ext, ln, text, side)
    first, _, rest = text.partition("\n")
    if num and rest and _label_text(first) == num:
        title = rest.replace("\n", " ")  # "T e i l 1" / "Gemeinsame Bestimmungen"
    elif num and title.startswith(num):
        title = title[len(num):].strip()
    if ABSTRACT_RUNIN.match(title):
        title = re.match(r"\W*(\w+)", title).group(1)  # "Abstract", as printed
    last = ext.lines[ln.i + text.count("\n")]
    if not num and _style(ln, body) == (0.0, False) and _style(last, body) == (0.0, False):
        # A schedule paragraph's own title takes the paragraph's number, printed at the margin
        # under it; the levels above were set without it.
        num = _paragraph_number(ext, last, _neighbours(ext, last)[2]) or ""
        title = AMENDMENT_MARK.sub("", title)  # "[F64Human Trafficking ..." as the reader sees it
    return num, title, marker


def headings_at(ext: Extraction, starts: list[int]) -> dict[int, tuple[int, str, str, str]]:
    """Free's reading of the headings that open on the lines `starts` (a model's section starts): {line: (the
    heading's first line, number, title, the heading as printed)}.

    A line's number is split off its title as Free splits it, and the heading takes the lines Free joins with it
    (`_merge_wrapped`): a title that wraps onto Free's next heading line in its style, a bare label ("CHAPTER 4",
    "PART 2") with the title line under it, a number split off its title. A bare number on its own line ("1" over
    "Introduction" in a thesis) takes the line under it as its title, and a title line whose bare number sits
    before it on its baseline ("4" | "Section 3: ...") starts at the number, as Free reads a bookmark that names
    the title line. A heading never takes a line another start opens on, nor a line Free does not count as
    heading-like (body text after a heading in body type). Free's titles are kept otherwise, except that a label
    or number left in one ("CHAPTER 1 INTRODUCTION", "A.2.1. Update Test Vector") becomes the number."""
    lines = ext.lines
    side = side_notes(ext)
    free = dict((ln.i, num) for ln, num in candidates(ext))
    hints, body = hints_of(ext), ext.body_size()
    opens = set(starts)

    def bare(ln: Line) -> bool:  # a section number alone ("1", "4.2"), not an index letter ("A")
        return bool(NUMBER_ALONE.match(ln.text.strip())) and any(c.isdigit() for c in ln.text)

    def after(j: int) -> int:
        while j < len(lines) and j in side:
            j += 1
        return j

    def read(i: int, own: set[int], title_line: bool = False) -> tuple[int, str, str, str]:
        ln = lines[i]
        m = NUMBERING.match(ln.text)
        num = free.get(i, ln.text.strip() if split_number(ext, ln) else m.group("num").strip() if m else "")
        group = [(ln, num)]
        joins_next = split_number(ext, ln) or bool(LABEL_ONLY.match(_label_text(ln.text)))
        j = after(i + 1)
        while j < len(lines) and len(group) <= WRAPPED_MAX:
            if (j in opens and j not in own) or not (j in free or j in own or (joins_next and len(group) == 1)):
                break
            group.append((lines[j], free.get(j, "")))
            j = after(j + 1)
        first, gnum, text = _merge_wrapped(group, hints, side, ext)[0]
        num, title, printed = _heading_parts(ext, first, gnum, text, side, body)
        if "\n" not in text and bare(first) and not title_line:
            nxt = after(i + 1)
            if nxt < len(lines) and lines[nxt].page == first.page and (nxt not in opens or nxt in own):
                _, n2, t2, p2 = read(nxt, own, True)
                return i, text.strip(), f"{n2} {t2}".strip(), f"{text.strip()} {p2}"
        if not num:
            head_line, _, rest_lines = text.partition("\n")
            head, _, rest = title.partition(" ")
            if rest_lines and LABEL_ONLY.match(_label_text(head_line)):
                num, title = _label_text(head_line), rest_lines.replace("\n", " ")
            elif rest and NUMBER_ALONE.match(head) and re.search(r"[\d.]", head):
                num, title = head, rest.strip()
        return i, num, title, printed

    out: dict[int, tuple[int, str, str, str]] = {}
    for i in sorted(opens):
        if not 0 <= i < len(lines):
            continue
        ln, prev = lines[i], lines[i - 1] if i else None
        if (prev is not None and i - 1 not in opens and prev.page == ln.page and not bare(ln)
                and (split_number(ext, prev) or bare(prev) and abs(prev.y0 - ln.y0) <= 0.3 * max(ln.size, 1.0))):
            out[i] = read(i - 1, {i})
        else:
            out[i] = read(i, {i})
    return out


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
        body = ext.body_size()
        _flat_outline_levels(backbone, lines)
        by_line = {a.line: a for a in backbone}
        votes: dict[Style, list[int]] = defaultdict(list)
        for a in backbone:
            votes[_style(lines[a.line], body)].append(a.level)
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
        rule_styles = {_style(lines[r.start_line], body) for r in rules if r.start_line not in abstract}
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
                r.level = r.number.rstrip(".").count(".") + 1 if dotted else level_of[_style(ln, body)]
            out.append(r)
        out.sort(key=lambda s: s.start_line)
        _abstract_levels(out, abstract)
        ctx.progress(1.0, f"{len(out)} headings ({len(backbone)} from the {source}, {len(out) - len(backbone)} by typography)")
        return out

    def _rules(self, ext: Extraction) -> list[RawSection]:
        side = side_notes(ext)
        cands = _merge_wrapped(candidates(ext), hints_of(ext), side, ext)
        # The abstract's heading does not take part in the style levels, so its style cannot shift
        # the other levels (see _abstract_levels).
        abstract = {ln.i for ln, _, _ in cands if _abstract_heading(ln)}
        body = ext.body_size()
        # Legislation sets its structure in labels ("KAPITEL I", "Artikel 5"), often in the body face
        # or smaller, so typography ranks it upside down; when the labels are clear they set the levels.
        texts = [f"{num} {text}" if num and not text.startswith(num) else text.replace("\n", " ") for _, num, text in cands]
        # The document's title stands outside the hierarchy (`pipeline.mark_doc_title`): set before a document's
        # first label, it would otherwise rank above the top kind and push every Part one level down.
        title = _title_line(cands)
        by_label = _label_levels([t for k, t in enumerate(texts) if k != title], numbers_count=False, min_share=0.3,
                                 styles=[_style(ln, body) for k, (ln, _, _) in enumerate(cands) if k != title])
        if by_label is not None and title is not None:
            by_label.insert(title, min(by_label, default=1))
        # Without clear labels (a short UK Act with no Parts or Chapters), italic cross-headings would rank
        # below every other style, under the sections they head: they go just above those sections.
        cross = set() if by_label else _cross_headings(ext, cands, body, furniture_of(ext) | side)
        if by_label:
            levels = list(by_label)
            _keep_sections_open(levels, _numbering_spine([num for _, num, _ in cands]), set())
        else:
            levels = _running_levels(cands, body, {k for k, (ln, _, _) in enumerate(cands) if ln.i in abstract})
        out = []
        for k, (ln, num, text) in enumerate(cands):
            level = 1 if ln.i in abstract else levels[k]  # the abstract's is set by _abstract_levels below
            num, title, marker = _heading_parts(ext, ln, num, text, side, body)
            out.append(RawSection(title=title, level=level, number=num, start_marker=marker[:160], start_line=ln.i))
        if cross:
            # The cross-headings take the level of the sections under them, and every heading at that level
            # or deeper goes one level down.
            top = min(out[k + 1].level for k in cross)
            for k, r in enumerate(out):
                if k in cross:
                    r.level = top
                elif r.level >= top and r.start_line not in abstract:
                    r.level += 1
        _abstract_levels(out, abstract)
        # Compress levels to 1..n so a document's top level is always 1.
        used = sorted({s.level for s in out})
        remap = {lv: i + 1 for i, lv in enumerate(used)}
        for s in out:
            s.level = remap[s.level]
        return out
