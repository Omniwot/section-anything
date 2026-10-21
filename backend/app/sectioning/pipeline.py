"""Run a strategy, then resolve and validate what it proposed.

Strategies propose sections with markers and line hints. This module turns
proposals into exact character ranges and checks them, so every strategy is
held to the same contract:

- A section's start is located by finding its start marker in the text (near
  the strategy's line hint). A marker that can't be found is flagged, never
  silently trusted; the hint is used only as a fallback and is flagged too.
- Marker hits inside a table of contents are rejected when the marker also
  occurs in the body, and a proposal that only resolves into the TOC is
  dropped: TOC lines are never section starts.
- Each start offset belongs to one section. Proposals with the fewest
  candidate positions choose first, so a repeated heading ("10.1 Cell
  Division" in an outline, the body and a summary) can't steal another
  section's spot.
- Text before the first heading becomes an explicit "Front matter" section.
- Sections are ordered and non-overlapping. A section's own text runs to the
  next section of any level ("segment"); its full span, including
  subsections, runs to the next section at the same or a higher level.
- End markers, where given, are checked against the computed boundaries.
- Titles the strategy says are printed must actually appear at the section start.
"""

from __future__ import annotations

import bisect
import re
import time
from collections.abc import Callable

from app.sectioning.extract import Extraction
from app.sectioning.llm import Usage
from app.sectioning.markers import Locator, canon
from app.sectioning.strategies.base import Context, RawSection, Strategy
from app.sectioning.strategies.llm_text import LlmReviewStrategy, LlmTextStrategy
from app.sectioning.strategies.rules import RulesStrategy
from app.sectioning.structure import Toc, toc_of

FRONT_MATTER_MIN_CHARS = 300

# Ordered cheapest → most thorough; the UI slider follows this order.
STRATEGIES: list[Strategy] = [RulesStrategy(), LlmReviewStrategy(), LlmTextStrategy()]
BY_ID = {s.id: s for s in STRATEGIES}


def _line_at(ext: Extraction, pos: int) -> int:
    starts = [ln.start for ln in ext.lines]
    return max(0, bisect.bisect_right(starts, pos) - 1)


def _snap(ext: Extraction, start: int) -> int:
    """Snap to the start of the line when only a short prefix (a number the
    marker omitted, a bullet) sits before the match."""
    li = _line_at(ext, start)
    return ext.lines[li].start if start - ext.lines[li].start <= 6 else start


def _candidates(r: RawSection, ext: Extraction, loc: Locator, toc: Toc) -> list[tuple[int, list[str]]]:
    """Possible start offsets for one proposal, best first, with their flags."""
    lines = ext.lines
    hint_line = r.start_line if r.start_line is not None and 0 <= r.start_line < len(lines) else None
    hint = lines[hint_line].start if hint_line is not None else None
    out: list[tuple[int, list[str]]] = []
    if r.start_marker:
        window = None
        if hint_line is not None:
            window = (lines[max(0, hint_line - 3)].start, lines[min(len(lines) - 1, hint_line + 8)].end)
        hits = loc.find_all(r.start_marker, *window) if window else []
        hits = hits or loc.find_all(r.start_marker)
        body = [h for h in hits if not toc.contains(h.start)]
        hits = body or hits
        ref = hint if hint is not None else (hits[0].start if hits else 0)
        hits.sort(key=lambda h: abs(h.start - ref))
        out = [(_snap(ext, h.start), []) for h in hits]
        if not out:
            fuzzy = (loc.find(r.start_marker, near=hint, lo=window[0], hi=window[1]) if window else None) or loc.find(
                r.start_marker, near=hint
            )
            if fuzzy:
                out = [(_snap(ext, fuzzy.start), ["start_marker_fuzzy"] if fuzzy.method == "fuzzy" else [])]
    if not out and hint is not None:
        out = [(_snap(ext, hint), ["start_marker_not_found"])]
    return out


def _assign(raw: list[RawSection], ext: Extraction, loc: Locator, toc: Toc) -> tuple[list, dict]:
    """Give each proposal one start offset no other proposal holds."""
    cands = [_candidates(r, ext, loc, toc) for r in raw]
    dropped = {"toc": 0, "duplicate": 0, "unanchored": 0}
    claimed: list[int] = []
    placed = []
    for i in sorted(range(len(raw)), key=lambda k: (len(cands[k]) or 10**9, k)):
        if not cands[i]:
            dropped["unanchored"] += 1  # nothing to anchor on: drop rather than guess
            continue
        free = [(s, f) for s, f in cands[i] if not toc.contains(s)]
        if not free:
            dropped["toc"] += 1
            continue
        pick = next(((s, f) for s, f in free if all(abs(s - c) > 3 for c in claimed)), None)
        if pick is None:
            dropped["duplicate"] += 1
            continue
        claimed.append(pick[0])
        placed.append((pick[0], raw[i], list(pick[1])))
    placed.sort(key=lambda t: t[0])
    return placed, dropped


def resolve(raw: list[RawSection], ext: Extraction, loc: Locator, toc: Toc | None = None) -> tuple[list[dict], dict]:
    text, lines = ext.text, ext.lines
    toc = toc if toc is not None else toc_of(ext)
    deduped, dropped = _assign(raw, ext, loc, toc)

    if deduped and deduped[0][0] >= FRONT_MATTER_MIN_CHARS and text[: deduped[0][0]].strip():
        top = min(r.level for _, r, _ in deduped)
        front = RawSection(title="Front matter", level=top, title_from_text=False, start_line=0)
        deduped.insert(0, (0, front, ["front_matter"]))

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
    return out, {"dropped": dropped, "toc_lines": len(toc.lines)}


def finish(raw: list[RawSection], ext: Extraction, loc: Locator) -> list[dict]:
    """Resolve proposals into sections (no metrics); used for replays."""
    return resolve(raw, ext, loc)[0]


def _rate(xs: list[bool | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def metrics(sections: list[dict], ext: Extraction, usage: Usage, seconds: float, extra: dict | None = None) -> dict:
    n = len(ext.text) or 1
    covered = n - sections[0]["start"] if sections else 0
    return {
        **(extra or {}),
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
    usage: Usage | None = None,
) -> tuple[list[RawSection], list[dict], dict]:
    """Returns the strategy's raw proposals (saved for replay), the resolved
    sections and the run metrics."""
    strategy = BY_ID[strategy_id]
    usage = usage or Usage()
    t0 = time.monotonic()
    ctx = Context(model=model, usage=usage, cost_cap_usd=cost_cap_usd, progress=progress or (lambda _f, _m: None))
    raw = await strategy.run(ext, ctx)
    sections, extra = resolve(raw, ext, Locator(ext.text))
    mark_doc_title(sections, ext)
    return raw, sections, metrics(sections, ext, usage, time.monotonic() - t0, extra)


GENERIC_FIRST = re.compile(
    r"^(abstract|summary|introduction|contents|table of contents|preface|foreword|overview|acknowledg|references|keywords|index)\b",
    re.I,
)


def mark_doc_title(sections: list[dict], ext: Extraction) -> None:
    """Flag the document's own title (`doc_title`): the first heading, on page 1, unnumbered,
    not a generic name, and set at least 1 pt larger than every other heading. Exports nest
    the other headings under it. Papers have such a title; READMEs and manuals often have
    several top-level headings of the title's size, so nothing is flagged there."""
    body = [s for s in sections if "front_matter" not in s["flags"]]
    if len(body) < 2:
        return
    first = body[0]
    size = lambda s: ext.lines[s["first_line"]].size if 0 <= s["first_line"] < len(ext.lines) else 0.0  # noqa: E731
    if (first["page_start"] == 1 and not (first["number"] or "").strip() and not GENERIC_FIRST.match(first["title"].strip())
            and size(first) >= max(size(s) for s in body[1:]) + 1.0):
        first["flags"].append("doc_title")


def estimates(ext: Extraction, prices: dict[str, dict[str, float]], cap_usd: float) -> list[dict]:
    """Per strategy and model: expected calls, tokens and cost. A run whose
    estimate is over the cap is blocked (owner decision: no override)."""
    out = []
    for s in STRATEGIES:
        e = s.estimate(ext)
        row = {
            "strategy": s.id, "calls": e.calls, "input_tokens": e.input_tokens, "output_tokens": e.output_tokens,
            "cost_usd": {}, "blocked": {},
        }
        for model, p in prices.items():
            cost = round((e.input_tokens * p["input"] + e.output_tokens * p["output"]) / 1e6, 4) if s.uses_llm else 0.0
            row["cost_usd"][model] = cost
            row["blocked"][model] = cost > cap_usd
        out.append(row)
    return out
