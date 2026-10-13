"""Heading detection from typography and numbering alone — no LLM, no cost.

The baseline every LLM strategy has to beat, and the candidate generator for
the "rules + LLM review" strategy.
"""

from __future__ import annotations

import re
from collections import defaultdict

from app.sectioning.extract import Extraction, Line
from app.sectioning.strategies.base import Context, RawSection, Strategy
from app.sectioning.structure import furniture_of, outline_backbone, toc_of

NUMBERING = re.compile(
    r"^(?P<num>(?:chapter|part|section|appendix|article|annex|unit|lesson)\s+[\dA-Z]+[.:]?"
    r"|\d+(?:\.\d+)*\.?"
    r"|[IVXLC]+\."
    r"|[A-Z]\.)\s+(?=\S)",
    re.I,
)
CAPTION = re.compile(r"^(fig(ure)?|table|chart|exhibit|source|note)s?\b[\s.:]*\d", re.I)


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


def candidates(ext: Extraction, loose: bool = False) -> list[tuple[Line, str]]:
    """Lines that look like headings, with their numbering prefix ("" if none).
    `loose` widens recall for an LLM to filter afterwards; TOC lines are
    excluded either way.

    Strict mode also drops what the golden corpus showed to be noise: numbered
    lines in body type ("1. Describe…", "a. E6 activates p53") unless the
    number is multi-level or keyword-led ("2.3", "Chapter 4"); repeated
    callout labels; and bold terms that run on into a paragraph."""
    body = ext.body_size()
    furniture = furniture_of(ext)
    toc = toc_of(ext).lines
    labels = set() if loose else _labels(ext, body)
    bump = 0.4 if loose else 0.8
    out: list[tuple[Line, str]] = []
    for ln in ext.lines:
        text = ln.text
        if ln.i in furniture or ln.i in toc or CAPTION.match(text) or not re.search(r"[A-Za-z]", text):
            continue
        words = len(text.split())
        if len(text) > (160 if loose else 120) or words > (20 if loose else 16):
            continue
        m = NUMBERING.match(text)
        styled = ln.size >= body + bump or (ln.bold and ln.size >= body - 0.3)
        numbered = bool(m) and not text.rstrip().endswith((",", ";")) and words <= 14
        if not loose:
            if text.strip().lower() in labels:
                continue
            if numbered and not styled:
                num = m.group("num")
                numbered = bool(re.match(r"\d+\.\d+", num) or re.match(r"[A-Za-z]{3,}", num))
                numbered = numbered and not text.rstrip().endswith((".", "?", ":"))
            if styled and not numbered and ln.size < body + bump and _runs_on(ext, ln):
                continue
        if styled or numbered:
            out.append((ln, m.group("num").strip() if m else ""))
    return out


LABEL_ONLY = re.compile(r"^(chapter|part|section|appendix|unit|lesson|module|book)\s+[\dA-Z]+[.:]?$", re.I)


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
    # The id predates the outline sources; kept so earlier runs still display.
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
        rule_styles = {(lines[r.start_line].size, lines[r.start_line].bold) for r in rules}
        level_of = _levels_from_outline(rule_styles, known)

        out = [
            RawSection(title=a.title, level=a.level, number=a.number, start_marker=lines[a.line].text[:160], start_line=a.line)
            for a in backbone
        ]
        covered = set(by_line)
        for r in rules:
            if r.start_line in covered or r.start_line + 1 in covered:
                continue
            ln = lines[r.start_line]
            dotted = re.fullmatch(r"\d+(?:\.\d+)*\.?", r.number)
            r.level = r.number.rstrip(".").count(".") + 1 if dotted else level_of[(ln.size, ln.bold)]
            out.append(r)
        out.sort(key=lambda s: s.start_line)
        ctx.progress(1.0, f"{len(out)} headings ({len(backbone)} from the {source}, {len(out) - len(backbone)} by typography)")
        return out

    def _rules(self, ext: Extraction) -> list[RawSection]:
        cands = _merge_wrapped(candidates(ext))
        # Rank distinct heading styles: bigger first, bold before regular.
        styles = sorted({(ln.size, ln.bold) for ln, _, _ in cands}, key=lambda s: (-s[0], not s[1]))
        style_level = {s: i + 1 for i, s in enumerate(styles)}
        out = []
        for ln, num, text in cands:
            dotted = re.fullmatch(r"\d+(?:\.\d+)*\.?", num)
            level = num.rstrip(".").count(".") + 1 if dotted else style_level[(ln.size, ln.bold)]
            title = text.replace("\n", " ")
            out.append(
                RawSection(
                    title=title[len(num):].strip() if num and title.startswith(num) else title,
                    level=level, number=num, start_marker=title[:160], start_line=ln.i,
                )
            )
        # Compress levels to 1..n so a document's top level is always 1.
        used = sorted({s.level for s in out})
        remap = {lv: i + 1 for i, lv in enumerate(used)}
        for s in out:
            s.level = remap[s.level]
        return out
