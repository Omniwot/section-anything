"""Heading detection from typography and numbering alone — no LLM, no cost.

The baseline every LLM strategy has to beat, and the candidate generator for
the "rules + LLM review" strategy.
"""

from __future__ import annotations

import re
from collections import defaultdict

from section_anything.extract import Extraction, Line
from section_anything.outline_check import LETTER_SPACED
from section_anything.strategies.base import Context, RawSection, Strategy
from section_anything.structure import furniture_of, outline_backbone, split_number, toc_of

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
    callout labels; and bold terms that run on into a paragraph."""
    body = ext.body_size()
    furniture = furniture_of(ext)
    toc = toc_of(ext).lines
    labels = set() if loose else _labels(ext, body)
    bump = 0.4 if loose else 0.8
    out: list[tuple[Line, str]] = []
    split: set[int] = set()
    for ln in ext.lines:
        text = ln.text
        if ln.i in furniture or ln.i in toc or CAPTION.match(text):
            continue
        if split_number(ext, ln):
            # Joined with its title line by _merge_wrapped (Free) and LlmReviewStrategy._rows.
            out.append((ln, text.strip()))
            split.add(ln.i)
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
        styled = ln.size >= body + bump or (ln.bold and ln.size >= body - 0.3)
        numbered = bool(m) and not text.rstrip().endswith((",", ";")) and words <= 14
        if not loose:
            if text.strip().lower() in labels or THEOREM.match(text):
                continue
            if numbered and not styled:
                num = m.group("num")
                numbered = bool(re.match(r"\d+\.\d+", num) or re.match(r"[A-Za-z]{3,}", num))
                numbered = numbered and not text.rstrip().endswith((".", "?", ":"))
            if styled and not numbered and ln.size < body + bump and _runs_on(ext, ln):
                continue
        if styled or numbered:
            out.append((ln, m.group("num").strip() if m else ""))
    # A split-off number counts only when its title line is a candidate too.
    kept = {ln.i for ln, _ in out if ln.i not in split}
    return [(ln, num) for ln, num in out if ln.i not in split or ln.i + 1 in kept]


LABEL_ONLY = re.compile(
    r"^(chapter|part|section|appendix|unit|lesson|module|book|article|schedule|annex|title|rule|clause|regulation)"
    r"\s+(\d+[A-Za-z]?|[IVXLC]+|[A-Z])[.:]?$",
    re.I,
)


def _merge_wrapped(cands: list[tuple[Line, str]]) -> list[tuple[Line, str, str]]:
    """Join a heading that wraps onto a second line with the same style, and a
    bare "CHAPTER 10" label with the title line right after it."""
    merged: list[tuple[Line, str, str]] = []
    for ln, num in cands:
        if merged:
            prev, pnum, ptext = merged[-1]
            last_i = prev.i + ptext.count("\n")
            adjacent = ln.i == last_i + 1 and ln.page == prev.page
            if adjacent and not num and ln.size == prev.size and ln.bold == prev.bold:
                merged[-1] = (prev, pnum, ptext + "\n" + ln.text)
                continue
            if adjacent and not num and "\n" not in ptext and LABEL_ONLY.match(ptext.strip()):
                merged[-1] = (prev, ptext.strip(), ptext + "\n" + ln.text)
                continue
        merged.append((ln, num, ln.text))
    return merged


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
        cands = _merge_wrapped(candidates(ext))
        # Rank distinct heading styles: bigger first, bold before regular. The abstract's heading
        # does not take part, so its style cannot shift the other levels (see _abstract_levels).
        abstract = {ln.i for ln, _, _ in cands if _abstract_heading(ln)}
        styles = sorted({(ln.size, ln.bold) for ln, _, _ in cands if ln.i not in abstract}, key=lambda s: (-s[0], not s[1]))
        style_level = {s: i + 1 for i, s in enumerate(styles)}
        out = []
        for ln, num, text in cands:
            dotted = re.fullmatch(r"\d+(?:\.\d+)*\.?", num)
            if ln.i in abstract:
                level = 1  # set by _abstract_levels below
            else:
                level = num.rstrip(".").count(".") + 1 if dotted else style_level[(ln.size, ln.bold)]
            title = marker = text.replace("\n", " ")
            if ABSTRACT_RUNIN.match(title):
                title = re.match(r"\W*(\w+)", title).group(1)  # "Abstract", as printed
            out.append(
                RawSection(
                    title=title[len(num):].strip() if num and title.startswith(num) else title,
                    level=level, number=num, start_marker=marker[:160], start_line=ln.i,
                )
            )
        _abstract_levels(out, abstract)
        # Compress levels to 1..n so a document's top level is always 1.
        used = sorted({s.level for s in out})
        remap = {lv: i + 1 for i, lv in enumerate(used)}
        for s in out:
            s.level = remap[s.level]
        return out
