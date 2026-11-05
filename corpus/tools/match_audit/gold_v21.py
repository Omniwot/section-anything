"""Track M of the zero-miss plan (research finding F063): answer keys v2.1, by one more written rule on top of
v2 (F058's R1 and R2, gold_v2.py), never by looking at a system's output. v1 and v2 stay as they are; v2.1 goes
beside them (<set>/gold-v2.1/<id>.json) with a CHANGES.jsonl line for every change.

R3 mention copy -> printed heading. A reference heading moves when, on its key page and the pages either side, its
   title is printed only as a mention, never as a heading line of its own:
   - a list item ("• Types of exploits"), a quotation ("“Forced action”"), part of a sentence ("our estate.",
     "section 56 (regulations under section 1:"), a figure or table label ("ASSESSMENT / PHASE", "Reference"),
     or a contents entry whose leaders were cut ("2.1.2 Objectives of PERSÉE .");
   - or a line of a contents list under a printed "Contents" title (R1 only knew lists that the library or
     leader dots detect) that holds three or more of the key's headings;
   - when the title opens with a section number or a numbered label ("5.2", "A.3.2", "Teil 2", "SCHEDULE 3"),
     a copy without that number counts as a mention, in documents that print their headings' numbers (most
     numbered headings found on their key page carry the number there).
   It moves to the first later page with a printed copy: one R1 accepts (85% plain similarity, 95% for titles
   under 12 characters, the same leading number, not an index entry or leaders), outside contents lists and
   running headers, carrying the title's number when it has one, and not a mention as above. The copy must be
   at least 2 pages after the key page (a copy one page on is already matched by the scorer: nothing moves), not
   before the previous heading's page and not after the page of the next heading printed where the key says
   (+1). Without such a copy it stays (logged R3-none).
Titles are not edited. READoc's keys (an external benchmark) are never edited.

usage: PYTHONPATH=<src> <venv python> gold_v21.py write | check
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import gold_v2 as G2  # noqa: E402
from section_anything.structure import furniture_of  # noqa: E402

CONTENTS_TITLE = re.compile(r"^\W*(?:table of contents|contents|inhalt|inhaltsverzeichnis|inhaltsübersicht|sommaire|"
                            r"table des matières|arrangement of (?:sections|regulations|rules|act))\W*$", re.IGNORECASE)
NUMBERS_SHARE = 0.8  # numbered key headings printed with their number on the key page, for the number test
BLOCK_MIN = 3  # key headings anchored under a printed "Contents" title before the block counts as a contents list
BULLET = re.compile(r"^\s*[•●▪◦‣\-–]\s*")
QUOTE = re.compile(r"^\s*[“\"‘'«„]")
RESIDUE = re.compile(r"\s\.\s*$")  # "2.1.2 Objectives of PERSÉE ." -- a contents entry whose leaders were cut
LEAD = re.compile(r"^\s*(?:(?:part|chapter|section|schedule|annex|annexe|appendix|article|teil|kapitel|abschnitt|"
                  r"unterabschnitt|titel|anlage|anhang|chapitre|titre|partie|condition)\s*(?:\d+[a-z]?|[IVXLC]+)\b|"
                  r"§+\s*\d+[a-z]?|[A-Z](?:\.\d+)+|\d+(?:\.\d+)*)[.:]?(?=\s|$)", re.IGNORECASE)


def lead(text: str) -> str | None:
    m = LEAD.match(text)
    return C.norm(m.group()) if m else None


def mention(title: str, text: str, numbers: bool) -> str | None:
    """Why a printed copy of the title is a mention and not the heading itself, or None."""
    t = text.strip()
    if BULLET.match(t) and not BULLET.match(title):
        return "list item"
    if QUOTE.match(t) and not QUOTE.match(title):
        return "quotation"
    if RESIDUE.search(t):
        return "contents entry (leaders cut)"
    if lead(title) and lead(t) and lead(t) != lead(title):
        return "another heading's number"
    if numbers and lead(title) and lead(t) != lead(title):
        return "without the heading's number"
    if (title.strip()[:1].isupper() and t[:1].islower() and t[-1:] in ".,;:"
            and title.strip()[-1:] not in ".,;:"):
        return "part of a sentence"
    if not G2.accepts(title, t):
        return "part of a longer line or a fragment"
    return None


def copies(spans: C.Spans, ext, title: str, page: int, exclude: set[int]) -> list[tuple[str, list[int]]]:
    """(text, lines) of every span on `page` that holds the title at the scorer's measure, outside `exclude`."""
    q = C.norm(title)
    idx = [i for i in spans.by_page.get(page, []) if not exclude.intersection(spans.keys[i])]
    if not idx or not q:
        return []
    sim, _r = spans.sims(q, idx)
    out = []
    for j, i in enumerate(idx):
        if sim[j] >= C.THRESHOLD:
            out.append((" ".join(ext.lines[k].text for k in spans.keys[i]), list(spans.keys[i])))
    return out


def printed(spans, ext, title, page, exclude, numbers, *, own_number: bool = False) -> tuple[str, list[int]] | None:
    """The best copy of the title on `page` that is not a mention: (text, lines). With `own_number`, a title
    with a leading number or label needs a copy that carries it."""
    best = None
    for text, lines in copies(spans, ext, title, page, exclude):
        if mention(title, text, numbers or own_number) is None:
            s = G2.accepts(title, text)
            if best is None or (s, -len(lines)) > best[0]:
                best = ((s, -len(lines)), text, lines)
    return (best[1], best[2]) if best else None


def contents_blocks(ext, gold, loc) -> tuple[set[int], dict[int, int]]:
    """Lines under a printed contents title ("Contents", "Inhaltsübersicht", ...) to the end of its page, on
    pages where BLOCK_MIN or more key headings are anchored in that block: {line}, {title line: page}."""
    starts = [ln for ln in ext.lines if CONTENTS_TITLE.match(ln.text.strip())]
    out, titles = set(), {}
    for t in starts:
        block = {ln.i for ln in ext.lines if ln.page == t.page and ln.i > t.i}
        held = sum(1 for g, L in zip(gold, loc, strict=True) if L.get("lines") and L["status"] == "page"
                   and set(L["lines"]) <= block)
        if held >= BLOCK_MIN:
            out |= block
            titles[t.i] = t.page
    return out, titles


def revise(doc: dict) -> tuple[list[dict], list[dict], dict]:
    gold = C.gold_of(doc, "v2")
    ext = C.load_ext(doc, "nobm")
    if ext is None or not ext.lines:
        return gold, [], {"skipped": "no saved extraction" if ext is None else "no text layer"}
    spans = C.Spans(ext)
    loc = C.locate(ext, gold, spans)
    block, block_titles = contents_blocks(ext, gold, loc)
    excl = C.contents_lines(ext) | furniture_of(ext) | block
    npages = max(ln.page for ln in ext.lines)
    # Does the document print its headings' numbers? Most numbered key headings found on their page carry them.
    numbered = [(g, L) for g, L in zip(gold, loc, strict=True) if lead(g["title"]) and L["status"] == "page"]
    carry = sum(1 for g, L in numbered if any(lead(t) == lead(g["title"]) for t, _ in
                                              copies(spans, ext, g["title"], L["page"], excl)))
    numbers = bool(numbered) and carry >= NUMBERS_SHARE * len(numbered)
    # Which headings are printed where the key says (a heading line of their own on the key page ±1)?
    here: list[tuple[str, list[int]] | None] = []
    for g, L in zip(gold, loc, strict=True):
        if L["status"] not in ("page", "far"):
            here.append(("not checked", []))  # R1 cases (contents) and headings not in the text stay as v2 has them
            continue
        p = g["page"]
        hit = None
        for q in (p, p - 1, p + 1):
            if 1 <= q <= npages:
                hit = printed(spans, ext, g["title"], q, excl, numbers)
                if hit:
                    break
        here.append(hit)
    trusted = [h is not None for h in here]
    nxt, bound = npages, [npages] * len(gold)
    for gi in range(len(gold) - 1, -1, -1):
        bound[gi] = nxt
        if trusted[gi]:
            nxt = min(npages, gold[gi]["page"] + 1)
    out, changes, prev_page = [], [], 0
    stats = {"numbers_printed": numbers, "numbers_share": round(carry / len(numbered), 3) if numbered else None, "contents_titles": sorted(set(block_titles.values())), "moved": 0,
             "no_printed_copy": 0, "near": 0}
    for gi, (g, L) in enumerate(zip(gold, loc, strict=True)):
        g2 = dict(g)
        if not trusted[gi]:
            lines = L.get("lines") or []
            why = ("no copy on the key page" if L["status"] == "far" else
                   "contents list under a printed contents title" if lines and set(lines) <= block else
                   mention(g["title"], " ".join(ext.lines[i].text for i in lines), numbers) or "mention")
            seen = " / ".join(ext.lines[i].text for i in lines)[:120] if L["status"] == "page" else None
            hit = None
            for q in range(max(g["page"] + 1, prev_page), min(bound[gi], npages) + 1):
                c = printed(spans, ext, g["title"], q, excl | set(lines), numbers, own_number=True)
                if c:
                    hit = (q, c)
                    break
            if hit and hit[0] >= g["page"] + 2:
                g2["page"] = hit[0]
                stats["moved"] += 1
                changes.append({"doc": doc["id"], "rule": "R3", "index": gi, "title": g["title"], "page_v2": g["page"],
                                "page_v21": hit[0], "anchored_on": why, "key_page_text": seen,
                                "copy_text": hit[1][0][:160]})
            elif hit:
                stats["near"] += 1  # the printed copy is one page on: the scorer already matches it
            else:
                stats["no_printed_copy"] += 1
                changes.append({"doc": doc["id"], "rule": "R3-none", "index": gi, "title": g["title"],
                                "page_v2": g["page"], "anchored_on": why, "key_page_text": seen,
                                "note": "no later printed copy; unchanged"})
        prev_page = max(prev_page, g2["page"])
        out.append(g2)
    return out, changes, stats


def target(doc: dict) -> Path:
    p = Path(doc["gold"])
    return C.CORPUS_V21 / p.name if doc["set"] == "corpus" else p.parent.parent / "gold-v2.1" / p.name


def main() -> None:
    cmd = sys.argv[1]
    only = os.environ.get("SPLIT", "")  # "dev" while the rule is designed; every document for the write
    docs = [d for d in C.registry() if not only or ("test" if d["split"] == "test" else "dev") == only]
    if cmd == "write" and only:
        sys.exit("write runs on every document")
    all_changes, summary = [], {}
    cache = C.OUT / "gold-v21-docs"
    cache.mkdir(exist_ok=True)
    for doc in docs:
        cp = cache / f"{doc['id']}.json"  # resumable: the memory guard may stop a run
        if cp.exists():
            v21, changes, stats = json.loads(cp.read_text())
        else:
            v21, changes, stats = revise(doc)
            cp.write_text(json.dumps([v21, changes, stats], ensure_ascii=False))
        summary[doc["id"]] = {"set": doc["set"], "genre": doc["genre"], "split": doc["split"],
                              "n_v2": len(C.gold_of(doc, "v2")), "n_v21": len(v21)} | stats
        all_changes += changes
        if cmd == "write":
            t = target(doc)
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text(json.dumps(v21, ensure_ascii=False, indent=1) + "\n")
        moved = sum(c["rule"] == "R3" for c in changes)
        if changes:
            print(f"{doc['id'][:50]:50s} {doc['set']:9s} {doc['split']:4s} R3 moved {moved}, none {stats['no_printed_copy']}"
                  f", near {stats['near']} numbers={stats['numbers_printed']}", flush=True)
    if cmd == "write":
        for root in {target(d).parent for d in docs}:
            mine = [c for c in all_changes if target(next(d for d in docs if d["id"] == c["doc"])).parent == root]
            (root / "CHANGES.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in mine))
            (root / "README.md").write_text(README.format(n=len(mine)))
    (C.OUT / "gold-v21-summary.json").write_text(json.dumps(summary, indent=1))
    (C.OUT / "gold-v21-changes.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in all_changes))
    tot = defaultdict(int)
    for s in summary.values():
        for k in ("moved", "no_printed_copy", "near"):
            tot[k] += s.get(k, 0)
        tot["docs_changed"] += bool(s.get("moved"))
    print(dict(tot))


README = """# Answer keys v2.1 (research finding F063)

Written by `gold_v21.py` (Section Anything, branch fix/match-failures, `corpus/tools/match_audit/`) from the
v2 keys in `../gold-v2/` (F058), which stay as they were, as do the originals in `../gold/`. One more documented
rule changes pages, applied to every document without looking at any system's output:

- **R3, mention copy to printed heading.** A heading whose title, on its key page and the pages either side, is
  printed only as a mention -- a list item, a quotation, part of a sentence, a figure or table label, a contents
  entry whose leaders were cut, a contents list under a printed "Contents" title holding three or more key
  headings, or (in documents that print their headings' numbers) a copy without the heading's number -- moves to
  the first later page where it is printed as a heading line of its own: R1's acceptance test, with the title's
  number when it has one, outside contents lists and running headers, at least 2 pages after the key page, not
  before the previous heading's page and not after the next correctly placed heading's page (+1). Without such
  a copy it is left as it was.

`CHANGES.jsonl` lists every change ({n} lines), with the old and new page, why the key page's copy is a mention,
and the text of the printed copy. Titles are not edited.
"""

if __name__ == "__main__":
    main()
