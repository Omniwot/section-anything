"""Heading detection from typography and numbering alone — no LLM, no cost.

The baseline every LLM strategy has to beat, and the candidate generator for
the "rules + LLM review" strategy.
"""

from __future__ import annotations

import re
from collections import defaultdict

from app.sectioning.extract import Extraction, Line
from app.sectioning.strategies.base import Context, RawSection, Strategy

NUMBERING = re.compile(
    r"^(?P<num>(?:chapter|part|section|appendix|article|annex|unit|lesson)\s+[\dA-Z]+[.:]?"
    r"|\d+(?:\.\d+)*\.?"
    r"|[IVXLC]+\."
    r"|[A-Z]\.)\s+(?=\S)",
    re.I,
)
CAPTION = re.compile(r"^(fig(ure)?|table|chart|exhibit|source|note)s?\b[\s.:]*\d", re.I)


def _furniture(ext: Extraction) -> set[int]:
    """Running headers/footers and page numbers: text that repeats (digits
    masked) at about the same height on many pages."""
    seen: dict[tuple[str, int], set[int]] = defaultdict(set)
    for ln in ext.lines:
        key = (re.sub(r"\d+", "#", ln.text.lower()), round(ln.y0 / 12))
        seen[key].add(ln.page)
    threshold = max(3, int(len(ext.pages) * 0.3))
    repeated = {k for k, pages in seen.items() if len(pages) >= threshold}
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
            or re.fullmatch(r"[#\s\-–—|.]*(page\s*#)?[#\s]*", masked)
            or (in_margin and ln.size <= body)
        ):
            out.add(ln.i)
    return out


def candidates(ext: Extraction, loose: bool = False) -> list[tuple[Line, str]]:
    """Lines that look like headings, with their numbering prefix ("" if none).
    `loose` widens recall for an LLM to filter afterwards."""
    body = ext.body_size()
    furniture = _furniture(ext)
    bump = 0.4 if loose else 0.8
    out: list[tuple[Line, str]] = []
    for ln in ext.lines:
        text = ln.text
        if ln.i in furniture or CAPTION.match(text) or not re.search(r"[A-Za-z]", text):
            continue
        words = len(text.split())
        if len(text) > (160 if loose else 120) or words > (20 if loose else 16):
            continue
        m = NUMBERING.match(text)
        styled = ln.size >= body + bump or (ln.bold and ln.size >= body - 0.3)
        numbered = bool(m) and not text.rstrip().endswith((",", ";")) and words <= 14
        if styled or numbered:
            out.append((ln, m.group("num").strip() if m else ""))
    return out


def _merge_wrapped(cands: list[tuple[Line, str]]) -> list[tuple[Line, str, str]]:
    """Join a heading that wraps onto a second line with the same style."""
    merged: list[tuple[Line, str, str]] = []
    for ln, num in cands:
        if merged:
            prev, pnum, ptext = merged[-1]
            last_i = prev.i + ptext.count("\n")
            if (
                ln.i == last_i + 1 and ln.page == prev.page and not num
                and ln.size == prev.size and ln.bold == prev.bold
            ):
                merged[-1] = (prev, pnum, ptext + "\n" + ln.text)
                continue
        merged.append((ln, num, ln.text))
    return merged


class RulesStrategy(Strategy):
    id = "rules"
    label = "Rules"
    description = "Typography and numbering only. No LLM, free, instant."
    uses_llm = False

    async def run(self, ext: Extraction, ctx: Context) -> list[RawSection]:
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
        ctx.progress(1.0, f"{len(out)} headings found")
        return out
