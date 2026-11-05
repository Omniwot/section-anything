"""Zero-miss track A, step 5 (F058): answer keys v2, by documented rules only, never by looking at a
system's output. The originals stay as they are; v2 goes beside them (<set>/gold-v2/<id>.json) with a
CHANGES.jsonl line for every change.

Rules (applied in this order, to every document of the F042, F050-extended, F049 and corpus sets):
  R1 contents copy -> body copy. A reference heading is anchored on a printed contents list when, on
     its gold page ±1, its title is printed only in a contents list: lines our contents detection
     marks (toc_of, listing_of, lines with leaders), or a page the key itself shows to be one
     (CONTENTS_MIN or more of the key's headings are printed there and again, in the same order, at
     least 2 pages later; the page is in the first 15% of the document (or its first 10 pages), or
     those later copies span at least 20% of its pages). It
     moves to the first later copy of its title: printed at >= 85% plain similarity (rapidfuzz
     ratio after the scorer's normalisation) as a line or 2-3 consecutive lines of one page, outside contents lists and running
     headers or footers, at least 2 pages after the gold page and not before the previous heading's
     page and not after the page of the next heading printed where the key says (+1). Index entries
     ("smallness stratification, 40") and lines with leaders are not copies, and a title shorter than
     12 characters needs 95% once leading numbers are set aside ("Introduction" / "1 Introduction");
     when both carry a leading number, the numbers must agree ("7.15.1 Purpose" is not "7.17.1 Purpose").
     Without such a copy it stays (logged).
  R2 one printed line, one heading. Two consecutive reference headings with the same title (plain
     ratio >= 95% after normalisation) located on the same printed line: the second is dropped.
READoc's keys (an external benchmark) are never edited.

usage: PYTHONPATH=<sa-miss src> <venv python> gold_v2.py write | check
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402
from section_anything.structure import furniture_of  # noqa: E402

CONTENTS_MIN = 5
ORDER_MIN = 0.8
FRONT = 0.15  # share of the pages that counts as front matter
SPREAD = 0.2  # share of the pages the later copies must span otherwise


NUMBER = re.compile(r"^(?:[\dIVXLC]+[.)]?|[A-Z][.)]|\d+(?:\.\d+)+\.?)\s+", re.I)
INDEX_ENTRY = re.compile(r"(?:,\s*[\divxlc]+(?:\s*[-–,]\s*[\divxlc]+)*\.?|,)\s*$", re.I)


def accepts(title: str, text: str) -> float:
    """Plain similarity of a later copy, 0 when it is not a copy: an index entry ("smallness
    stratification, 40"), or a short title that only reaches 85 inside a longer line ("be convex.")."""
    if INDEX_ENTRY.search(text.strip()) or C.LEADERS.search(text):
        return 0.0
    nt, nx = NUMBER.match(title.strip()), NUMBER.match(text.strip())
    if nt and nx and C.norm(nt.group()) != C.norm(nx.group()):
        return 0.0  # another section's copy ("7.15.1 Purpose" is not "7.17.1 Purpose")
    a, b = C.norm(title), C.norm(text)
    r = fuzz.ratio(a, b)
    bare = fuzz.ratio(C.norm(NUMBER.sub("", title.strip())), C.norm(NUMBER.sub("", text.strip())))
    if (r >= 85 and len(a) >= 12) or bare >= 95:
        return float(max(r, bare))
    return 0.0


def first_copy(spans: C.Spans, ext, title: str, start_page: int, end_page: int, exclude: set[int]):
    """The first page from start_page to end_page with an accepted copy: (score, lines, page)."""
    for q in range(start_page, end_page + 1):
        hit = spans.best(title, [q], exclude=exclude, strict=True, min_score=60)
        if not hit:
            continue
        idx = [i for i in spans.by_page.get(q, []) if not exclude.intersection(spans.keys[i])]
        best = None
        for i in idx:
            text = " ".join(ext.lines[j].text for j in spans.keys[i])
            s = accepts(title, text)
            if s and (best is None or (s, -len(spans.keys[i])) > (best[0], -len(best[1]))):
                best = (s, list(spans.keys[i]), q)
        if best:
            return best
    return None


def revise(doc: dict) -> tuple[list[dict], list[dict], dict]:
    gold = C.gold_of(doc)
    ext = C.load_ext(doc, "nobm")
    if ext is None or not ext.lines:
        return gold, [], {"skipped": "no saved extraction" if ext is None else "no text layer"}
    spans = C.Spans(ext)
    loc = C.locate(ext, gold, spans)
    cont, furn = C.contents_lines(ext), furniture_of(ext)
    npages = max(ln.page for ln in ext.lines)
    # Pages the key shows to be contents pages: CONTENTS_MIN or more headings printed there and again later, in order.
    later: dict[int, tuple[int, int]] = {}
    by_page: dict[int, list[int]] = defaultdict(list)
    for gi, (g, L) in enumerate(zip(gold, loc, strict=True)):
        if L["status"] != "page":
            continue
        hit = first_copy(spans, ext, g["title"], L["page"] + 2, npages, cont | furn | set(L["lines"]))
        if hit:
            later[gi] = (hit[1][0], hit[2])
            by_page[L["page"]].append(gi)
    key_pages = set()
    for p, gis in by_page.items():
        if len(gis) < CONTENTS_MIN:
            continue
        gis = sorted(gis, key=lambda gi: loc[gi]["lines"][0])
        ups = sum(later[a][0] < later[b][0] for a, b in zip(gis, gis[1:], strict=False))
        pages = [later[gi][1] for gi in gis]
        # A contents page sits in the front matter, or its entries come back spread over the document
        # (a page of role names repeated in a table two pages later is not one).
        front = p <= max(10, FRONT * npages)
        spread = max(pages) - min(pages) >= SPREAD * npages
        if ups >= ORDER_MIN * (len(gis) - 1) and (front or spread):
            key_pages.add(p)
    # Each moved heading stays between its neighbours: not before the previous heading's page, not
    # after the page of the next heading that is printed where the key says (+1).
    trusted = [L["status"] == "page" and L["page"] not in key_pages for L in loc]
    nxt, bound = npages, [npages] * len(gold)
    for gi in range(len(gold) - 1, -1, -1):
        bound[gi] = nxt
        if trusted[gi]:
            nxt = min(npages, gold[gi]["page"] + 1)
    out, changes, prev_page = [], [], 0
    stats = {"key_contents_pages": sorted(key_pages), "contents_detected": 0, "contents_key_pages": 0,
             "moved": 0, "no_body_copy": 0, "dropped_duplicates": 0}
    for gi, (g, L) in enumerate(zip(gold, loc, strict=True)):
        g2 = dict(g)
        anchored = None
        if L["status"] == "contents":
            anchored = "contents list (detected)"
            stats["contents_detected"] += 1
        elif L["status"] == "page" and L["page"] in key_pages and gi in later:
            anchored = f"contents page (key shows it: page {L['page']})"
            stats["contents_key_pages"] += 1
        if anchored:
            excl = cont | furn | set(L.get("lines", []))
            hit = first_copy(spans, ext, g["title"], max(g["page"] + 2, prev_page), bound[gi], excl)
            if hit:
                g2["page"] = hit[2]
                stats["moved"] += 1
                changes.append({"doc": doc["id"], "rule": "R1", "index": gi, "title": g["title"], "page_v1": g["page"],
                                "page_v2": hit[2], "anchored_on": anchored, "copy_similarity": round(hit[0], 1),
                                "copy_text": " / ".join(ext.lines[i].text for i in hit[1])[:160]})
            else:
                stats["no_body_copy"] += 1
                changes.append({"doc": doc["id"], "rule": "R1-none", "index": gi, "title": g["title"],
                                "page_v1": g["page"], "anchored_on": anchored, "note": "no later copy; unchanged"})
        prev_page = max(prev_page, g2["page"])
        # R2: the same title on the same printed line as the previous kept heading
        if out and L["status"] == "page":
            pg, pl = out[-1]
            if pl is not None and pl == L["lines"][0] and fuzz.ratio(C.norm(pg["title"]), C.norm(g["title"])) >= 95:
                stats["dropped_duplicates"] += 1
                changes.append({"doc": doc["id"], "rule": "R2", "index": gi, "title": g["title"], "page_v1": g["page"],
                                "note": "same title on the same printed line as the heading before it; dropped"})
                continue
        out.append((g2, L["lines"][0] if L["status"] == "page" else None))
    return [g for g, _ in out], changes, stats


def target(doc: dict) -> Path:
    p = Path(doc["gold"])
    return p.parent.parent / "gold-v2" / p.name


def main() -> None:
    cmd = sys.argv[1]
    docs = C.registry()
    all_changes, summary = [], {}
    cache = C.OUT / "gold-v2-docs"
    cache.mkdir(exist_ok=True)
    for doc in docs:
        cp = cache / f"{doc['id']}.json"  # resumable: the memory guard may stop a run
        if cp.exists():
            v2, changes, stats = json.loads(cp.read_text())
        else:
            v2, changes, stats = revise(doc)
            cp.write_text(json.dumps([v2, changes, stats], ensure_ascii=False))
        summary[doc["id"]] = {"set": doc["set"], "genre": doc["genre"], "split": doc["split"], "n_v1": len(C.gold_of(doc)),
                              "n_v2": len(v2)} | stats
        all_changes += changes
        if cmd == "write":
            t = target(doc)
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text(json.dumps(v2, ensure_ascii=False, indent=1) + "\n")
        moved = sum(c["rule"] == "R1" for c in changes)
        if changes:
            print(f"{doc['id'][:50]:50s} {doc['set']:9s} R1 moved {moved}, R1 none {stats['no_body_copy']}, "
                  f"R2 {stats['dropped_duplicates']} key pages {stats['key_contents_pages']}", flush=True)
    for root in {target(d).parent for d in docs}:
        mine = [c for c in all_changes if target(next(d for d in docs if d["id"] == c["doc"])).parent == root]
        if cmd == "write":
            (root / "CHANGES.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in mine))
            (root / "README.md").write_text(README.format(n=len(mine)))
    (C.OUT / "gold-v2-summary.json").write_text(json.dumps(summary, indent=1))
    (C.OUT / "gold-v2-changes.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in all_changes))
    tot = defaultdict(int)
    for s in summary.values():
        for k in ("moved", "no_body_copy", "dropped_duplicates", "contents_detected", "contents_key_pages"):
            tot[k] += s.get(k, 0)
        tot["docs_changed"] += bool(s.get("moved") or s.get("dropped_duplicates"))
    print(dict(tot))


README = """# Answer keys v2 (research finding F058)

Written by `gold_v2.py` (Section Anything, branch eval/miss-audit, `corpus/tools/miss_audit/`) from the
keys in `../gold/`, which stay as they were. Only two documented rules change anything, applied to
every document without looking at any system's output:

- **R1, contents copy to body copy.** A heading whose title, on its key page and the pages either side,
  is printed only in a contents list (detected by the library's contents detection or by leader dots,
  or a page in the front matter, or whose later copies span 20% of the document, where 5 or more of
  the key's headings are printed and printed again, in the same order, at least 2 pages later)
  moves to the first later copy of its title: printed at 85% plain similarity or more (rapidfuzz
  ratio after the scorer's normalisation), outside contents lists and running headers or footers, at least 2 pages later, and not
  before the previous heading's page or after the next correctly placed heading's page (+1). Index
  entries and lines with leaders are not copies, titles under 12 characters need 95% once leading
  numbers are set aside, and two leading numbers must agree. With no such copy it is left as it was.
- **R2, one printed line, one heading.** A heading with the same title (plain ratio 95% or more)
  located on the same printed line as the heading before it is a duplicate and is dropped.

`CHANGES.jsonl` lists every change ({n} lines), with the old and new page and the text of the copy.
"""

if __name__ == "__main__":
    main()
