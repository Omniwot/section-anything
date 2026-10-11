"""Run a strategy, then resolve and validate what it proposed.

Strategies propose sections with markers and line hints. This module turns
proposals into exact character ranges and checks them, so every strategy is
held to the same contract:

- A section's start is located by finding its start marker in the text (near
  the strategy's line hint). A marker that can't be found is flagged, never
  silently trusted; the hint is used only as a fallback and is flagged too.
- Sections are ordered and non-overlapping. A section's own text runs to the
  next section of any level ("segment"); its full span, including
  subsections, runs to the next section at the same or a higher level.
- End markers, where given, are checked against the computed boundaries.
- Titles the strategy says are printed must actually appear at the section start.
"""

from __future__ import annotations

import bisect
import time
from collections.abc import Callable

from app.sectioning.extract import Extraction
from app.sectioning.llm import Usage
from app.sectioning.markers import Locator, canon
from app.sectioning.strategies.base import Context, RawSection, Strategy
from app.sectioning.strategies.llm_text import LlmReviewStrategy, LlmTextStrategy
from app.sectioning.strategies.rules import RulesStrategy

# Ordered cheapest → most thorough; the UI slider follows this order.
STRATEGIES: list[Strategy] = [RulesStrategy(), LlmReviewStrategy(), LlmTextStrategy()]
BY_ID = {s.id: s for s in STRATEGIES}


def _line_at(ext: Extraction, pos: int) -> int:
    starts = [ln.start for ln in ext.lines]
    return max(0, bisect.bisect_right(starts, pos) - 1)


def resolve(raw: list[RawSection], ext: Extraction, loc: Locator) -> list[dict]:
    text, lines = ext.text, ext.lines
    placed = []
    for r in raw:
        hint_line = r.start_line if r.start_line is not None and 0 <= r.start_line < len(lines) else None
        hint = lines[hint_line].start if hint_line is not None else None
        flags: list[str] = []
        hit = None
        if r.start_marker:
            if hint is not None:
                lo = lines[max(0, hint_line - 3)].start
                hi = lines[min(len(lines) - 1, hint_line + 8)].end
                hit = loc.find(r.start_marker, near=hint, lo=lo, hi=hi)
            hit = hit or loc.find(r.start_marker, near=hint)
        if hit:
            start = hit.start
            if hit.method == "fuzzy":
                flags.append("start_marker_fuzzy")
        elif hint is not None:
            start = hint
            flags.append("start_marker_not_found")
        else:
            continue  # nothing to anchor on: drop rather than guess
        # Snap to the start of the line when only a short prefix (a number the
        # marker omitted, a bullet) sits before the match.
        li = _line_at(ext, start)
        if start - lines[li].start <= 6:
            start = lines[li].start
        placed.append((start, r, flags))

    placed.sort(key=lambda t: t[0])
    deduped = []
    for start, r, flags in placed:
        if deduped and start - deduped[-1][0] <= 3:
            continue
        deduped.append((start, r, flags))

    out = []
    n = len(text)
    for k, (start, r, flags) in enumerate(deduped):
        seg_end = deduped[k + 1][0] if k + 1 < len(deduped) else n
        span_end = next((s for s, rr, _ in deduped[k + 1:] if rr.level <= r.level), n)
        seg_end_trim = seg_end - 1 if seg_end > start and text[seg_end - 1] == "\n" else seg_end

        end_found = end_agrees = model_end = None
        if r.end_marker.strip():
            hit = loc.find(r.end_marker, near=seg_end, lo=start, hi=min(n, span_end + 2000))
            end_found = hit is not None
            if hit:
                model_end = hit.end
                # Models end a section after its last body paragraph; the
                # computed boundary also takes trailing captions, credits and
                # callout boxes up to the next heading. A short gap is that
                # trailing material, not disagreement. Running past the
                # boundary into the next section is.
                target = min((seg_end_trim, span_end), key=lambda t: abs(t - hit.end))
                gap = target - hit.end
                end_agrees = -50 <= gap <= max(1500, int(0.1 * (span_end - start)))
            if not end_found:
                flags.append("end_marker_not_found")
            elif not end_agrees:
                flags.append("end_mismatch")

        title_ok = None
        if r.title_from_text and r.title:
            window = canon(text[start:start + 400 + len(r.title)])
            title_ok = canon(r.title)[:60] in window
            if not title_ok:
                flags.append("title_not_in_text")

        first_line, last_line = _line_at(ext, start), _line_at(ext, max(start, seg_end_trim - 1))
        out.append(
            {
                "id": k,
                "number": r.number,
                "title": r.title,
                "title_from_text": r.title_from_text,
                "level": r.level,
                "start": start,
                "end": seg_end_trim,
                "span_end": span_end,
                "first_line": first_line,
                "last_line": last_line,
                "page_start": lines[first_line].page if lines else 1,
                "page_end": lines[last_line].page if lines else 1,
                "start_marker": r.start_marker,
                "end_marker": r.end_marker,
                "end_marker_found": end_found,
                "model_end": model_end,
                "end_agrees": end_agrees,
                "title_verified": title_ok,
                "flags": flags,
            }
        )
    return out


def _rate(xs: list[bool | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def metrics(sections: list[dict], ext: Extraction, usage: Usage, seconds: float) -> dict:
    n = len(ext.text) or 1
    covered = n - sections[0]["start"] if sections else 0
    return {
        "sections": len(sections),
        "max_depth": max((s["level"] for s in sections), default=0),
        "coverage": round(covered / n, 4),
        "start_marker_exact": _rate(["start_marker_not_found" not in s["flags"] and "start_marker_fuzzy" not in s["flags"] for s in sections]),
        "start_marker_found": _rate(["start_marker_not_found" not in s["flags"] for s in sections]),
        "end_marker_found": _rate([s["end_marker_found"] for s in sections]),
        "end_agreement": _rate([s["end_agrees"] for s in sections]),
        "title_verified": _rate([s["title_verified"] for s in sections]),
        "flagged": sum(bool(s["flags"]) for s in sections),
        "seconds": round(seconds, 1),
        **usage.summary(),
    }


async def run(
    ext: Extraction,
    strategy_id: str,
    model: str,
    cost_cap_usd: float,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[list[dict], dict]:
    strategy = BY_ID[strategy_id]
    usage = Usage()
    t0 = time.monotonic()
    ctx = Context(model=model, usage=usage, cost_cap_usd=cost_cap_usd, progress=progress or (lambda _f, _m: None))
    raw = await strategy.run(ext, ctx)
    sections = resolve(raw, ext, Locator(ext.text))
    return sections, metrics(sections, ext, usage, time.monotonic() - t0)


def estimates(ext: Extraction, prices: dict[str, dict[str, float]]) -> list[dict]:
    out = []
    for s in STRATEGIES:
        e = s.estimate(ext)
        row = {"strategy": s.id, "calls": e.calls, "input_tokens": e.input_tokens, "output_tokens": e.output_tokens, "cost_usd": {}}
        for model, p in prices.items():
            row["cost_usd"][model] = round((e.input_tokens * p["input"] + e.output_tokens * p["output"]) / 1e6, 4) if s.uses_llm else 0.0
        out.append(row)
    return out
