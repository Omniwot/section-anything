"""Track M of the zero-miss plan (research finding F063): the F056 miss audit, with the match failures (cause e)
re-examined, for the code on PYTHONPATH and answer keys v1, v2 and v2.1 at once.

usage: PYTHONPATH=<src> TAG=<base|fix> [SPLIT=dev|test] <venv python> match_audit.py run [ids...]
       -> rows-<TAG>-<gold>/<id>.json, one per answer-key version (resumable per document)

Each miss keeps F056's cause (`cause`, `sub`, audit.py unchanged) and gets a second one (`cause2`, `sub2`):
- F056 tags e whenever any prediction's title reaches 85% of the heading's (the scorer's lenient measure) on its page
  ±1 or anywhere else, even when that prediction is paired with another reference heading ("Condition 6 Openness"
  for "Condition 5", "1.22 Income" for "2. Income"). cause2 counts a prediction elsewhere only when it is paired with
  no reference heading and has the same title (`same_title`: 90% plain similarity, or 95% with leading numbers set
  aside); otherwise the miss goes down F056's own b/c/d path (the heading was never predicted).
- e2 sub-causes: the prediction on the heading's printed line merges the next or previous heading, merges
  following text, is the title's tail or head, or differs; or the same title was predicted only elsewhere, on a
  contents-list line, a running header, or another body line.
Side metrics per run (never section_anything.evaluate.score, the published metric): `label_pairs`, reference
headings that are a bare structural label ("ANNEXE I", "Condition 4") matched by a prediction on their page ±1
whose title is that label followed by its title ("ANNEXE I CERTIFICAT DE GEL"); `max_pairs`, the size of a maximum
one-to-one pairing on the scorer's own pairs of headings.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit as A  # noqa: E402  (F056's audit: saved runs, prediction lines, causes)
import common as C  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402
from section_anything.docling_input import attach_hints  # noqa: E402
from section_anything.evaluate import _sim  # noqa: E402
from section_anything.structure import furniture_of, listing_of, toc_of  # noqa: E402

TAG = os.environ.get("TAG", "fix")
GOLDS = os.environ.get("GOLDS", "v1,v2,v2.1").split(",")
SPLIT = os.environ.get("SPLIT", "")
NUM = re.compile(r"^\s*(?:(?:chapter|part|section|article|art\.|schedule|annex|appendix|teil|kapitel|abschnitt|"
                 r"titel|anlage|anhang|chapitre|titre|annexe|condition|§+)\s*)?\(?(?:[ivxlcdm]+|\d+[a-z]?(?:\.\d+)*|[a-z])"
                 r"[.):]?\s+", re.IGNORECASE)
BARE_LABEL = re.compile(r"^\s*(?:part|chapter|schedule|annex|annexe|appendix|title|book|division|section|article|"
                        r"artikel|teil|kapitel|abschnitt|unterabschnitt|titel|anlage|anhang|chapitre|titre|partie|livre|"
                        r"condition|§+)\s*(?:\d+[a-z]?|[ivxlc]+|[a-z]|premier|première|unique)[.:]?\s*$", re.IGNORECASE)


def rows_dir(gold: str) -> Path:
    return C.OUT / f"rows-{TAG}-{gold}"


def same_title(a: str, b: str) -> bool:
    """The same heading text: 90% plain similarity of comparable lengths, or 95% with leading numbers set aside."""
    na, nb = C.norm(a), C.norm(b)
    if not na or not nb:
        return False
    if fuzz.ratio(na, nb) >= 90 and min(len(na), len(nb)) >= 0.9 * max(len(na), len(nb)):
        return True
    ba, bb = C.norm(NUM.sub("", a, count=1)), C.norm(NUM.sub("", b, count=1))
    return bool(ba) and bool(bb) and min(len(ba), len(bb)) >= 4 and fuzz.ratio(ba, bb) >= 95


def where(li, cont, toc, listing, furn) -> str:
    return ("contents" if li in toc or li in listing or li in cont else "running_header" if li in furn else "body")


def cause2(doc, gold, gi, L, preds, owner, kind, strict, loose, trace, places) -> tuple[str, str]:
    """F056's cause with the match failures re-examined (see the module docstring)."""
    g = gold[gi]
    st = L["status"]
    if st in ("contents", "none"):
        return A.cause(doc, g, L, preds, kind, strict, loose, trace)
    gp, gt = g["page"], g["title"]
    lines = L.get("lines") or []
    ng = C.norm(gt)
    at = [p for p in preds if p.get("line") is not None and lines and (p["line"] in lines or p["line"] == lines[0] - 1)]
    if at:
        p = min(at, key=lambda p: abs(p["line"] - lines[0]))
        pt = C.norm(p["title"])
        nxt, prv = (gold[gi + 1] if gi + 1 < len(gold) else None), (gold[gi - 1] if gi else None)
        if same_title(p["title"], gt):
            return "e", "paired_with_another_heading"
        if pt.startswith(ng[: max(4, len(ng) - 2)]) and len(pt) > len(ng):
            rest = pt[len(ng):]
            if nxt and C.norm(nxt["title"]) and fuzz.partial_ratio(C.norm(nxt["title"]), rest) >= 90:
                return "e", "merged_next_heading"
            return "e", "merged_following_text"
        if prv and C.norm(prv["title"])[:12] and pt.startswith(C.norm(prv["title"])[:12]) and ng[-12:] in pt:
            return "e", "merged_into_previous_heading"
        if ng.endswith(pt[-max(4, len(pt) - 2):]) and len(ng) > len(pt):
            return "e", "title_tail_only"
        if ng.startswith(pt[: max(4, len(pt) - 2)]) and len(ng) > len(pt):
            return "e", "title_head_only"
        if ng in pt:
            return "e", "title_inside_longer_heading"
        return "e", "title_differs"
    free = [p for j, p in enumerate(preds) if j not in owner and same_title(p["title"], gt)]
    if free:
        p = min(free, key=lambda p: abs(p["page"] - gp))
        w = places(p.get("line"))
        return "e", f"predicted_elsewhere:{w}"
    rest = [p for j, p in enumerate(preds) if j not in owner]  # F056's b/c/d path, without the paired predictions
    c, sub = A.cause(doc, g, L, [p for p in rest if not (_sim(gt, p["title"]) >= C.THRESHOLD)], kind, strict, loose, trace)
    return c, sub


def label_pairs(gold, preds, pairs) -> int:
    """Reference headings that are a bare label, unmatched, with a prediction on their page ±1 whose title is the
    label followed by its title (one prediction serves one label)."""
    used, n = set(), 0
    for gi, g in enumerate(gold):
        if gi in pairs or not BARE_LABEL.match(g["title"]):
            continue
        lab = C.norm(g["title"])
        for pj, p in enumerate(preds):
            pt = C.norm(p["title"])
            if pj not in used and abs(p["page"] - g["page"]) <= 1 and pt.startswith(lab) and len(pt) > len(lab) + 2:
                used.add(pj)
                n += 1
                break
    return n


def max_pairs(gold, preds, pairs) -> int:
    edges = {}
    for gi, g in enumerate(gold):
        for pj, p in enumerate(preds):
            if abs(p["page"] - g["page"]) <= 1 and _sim(g["title"], p["title"]) >= C.THRESHOLD:
                edges.setdefault(gi, []).append(pj)
    g2p, p2g = dict(pairs), {p: g for g, p in pairs.items()}
    sys.setrecursionlimit(100000)

    def aug(gi, seen):
        for pj in edges.get(gi, []):
            if pj in seen:
                continue
            seen.add(pj)
            if pj not in p2g or aug(p2g[pj], seen):
                g2p[gi], p2g[pj] = pj, gi
                return True
        return False

    for gi in edges:
        if gi not in g2p:
            aug(gi, set())
    return len(g2p)


def score_run(doc, gold, loc, ext, spans, sections, kind, strict, loose, trace, places) -> dict:
    preds = C.heads(sections)
    pairs = C.pair(gold, preds)
    A.pred_lines(ext, spans, preds)
    owner = {pj: gi for gi, pj in pairs.items()}
    misses = []
    for gi, g in enumerate(gold):
        if gi in pairs:
            continue
        c, sub = A.cause(doc, g, loc[gi], preds, kind, strict, loose, trace)
        c2, sub2 = cause2(doc, gold, gi, loc[gi], preds, owner, kind, strict, loose, trace, places)
        misses.append({"gi": gi, "cause": c, "sub": sub, "cause2": c2, "sub2": sub2})
    return {"n_pred": len(preds), "n_gold": len(gold), "matched": len(pairs), "misses": misses,
            "label_pairs": label_pairs(gold, preds, pairs), "max_pairs": max_pairs(gold, preds, pairs),
            "preds": [[p["title"], p["page"], p.get("line")] for p in preds]}


def process(doc: dict) -> dict[str, dict]:
    t0 = time.monotonic()
    head = {k: doc[k] for k in ("id", "genre", "set", "split", "complete", "pages")}
    ext = C.load_ext(doc, "nobm")
    if ext is None:
        return {v: {"doc": head, "error": "no saved extraction"} for v in GOLDS}
    spans = C.Spans(ext)
    strict, loose = C.CandCtx(ext, False), C.CandCtx(ext, True)
    cont, furn, toc, listing = C.contents_lines(ext), furniture_of(ext), set(toc_of(ext).lines), set(listing_of(ext))

    def places(li):
        return None if li is None else where(li, cont, toc, listing, furn)

    runs = []  # (mode, source, rep, sections, kind, strict, loose, trace, ext)
    tr = C.free_trace(ext)
    runs.append(("free-nobm", f"{TAG} re-run", 0, tr["sections"], "free", strict, loose, tr, ext))
    ext_bm = C.load_ext(doc, "bm")
    if ext_bm.outline:
        trb = C.free_trace(ext_bm)
        runs.append(("free-bm", f"{TAG} re-run", 0, trb["sections"], "free", C.CandCtx(ext_bm, False),
                     C.CandCtx(ext_bm, True), trb, ext_bm))
    errors = {}
    for variant in ("bm", "nobm"):
        hier = C.docling_of(doc, variant)
        if hier is None:
            continue
        e = C.load_ext(doc, variant)
        try:
            attach_hints(e, hier)
        except Exception as exc:  # noqa: BLE001
            errors[variant] = f"{type(exc).__name__}: {exc}"[:200]
            continue
        trh = C.free_trace(e)
        runs.append((f"free-hints-{variant}", f"{TAG} re-run", 0, trh["sections"], "free", C.CandCtx(e, False),
                     C.CandCtx(e, True), trh, e))
    for mode, source, rep, sections in A.saved_runs(doc):
        kind = "quick" if mode.startswith("quick") else "standard"
        runs.append((mode, source, rep, sections, kind, strict, loose, None, ext))
    out = {}
    for v in GOLDS:
        gold = C.gold_of(doc, v)
        loc = C.locate(ext, gold, spans)
        res = {"doc": head, "gold": v, "loc": loc, "runs": [], "has_outline": bool(ext_bm.outline)}
        if errors:
            res["hint_errors"] = errors
        for mode, source, rep, sections, kind, s, lo, trc, e in runs:
            r = score_run(doc, gold, loc, e, spans, sections, kind, s, lo, trc, places)
            res["runs"].append({"mode": mode, "source": source, "rep": rep} | r)
        res["seconds"] = round(time.monotonic() - t0, 1)
        out[v] = res
    return out


def main() -> None:
    ids = sys.argv[2:]
    docs = [d for d in C.registry() if (not ids or d["id"] in ids)
            and (not SPLIT or ("test" if d["split"] == "test" else "dev") == SPLIT)]
    for v in GOLDS:
        rows_dir(v).mkdir(parents=True, exist_ok=True)
    for d in docs:
        if all((rows_dir(v) / f"{d['id']}.json").exists() for v in GOLDS):
            continue
        try:
            rs = process(d)
        except Exception as exc:  # noqa: BLE001 -- one document must not stop the rest
            err = {"doc": {k: d[k] for k in ("id", "genre", "set", "split", "complete", "pages")},
                   "error": f"{type(exc).__name__}: {exc}"[:300]}
            rs = {v: err for v in GOLDS}
        for v, r in rs.items():
            (rows_dir(v) / f"{d['id']}.json").write_text(json.dumps(r, ensure_ascii=False))
        r = next(iter(rs.values()))
        print(f"{d['id'][:50]:50s} {d['set']:9s} {r.get('seconds', '-')}s runs={len(r.get('runs', []))} "
              f"{r.get('error', '')}", flush=True)


if __name__ == "__main__":
    main()
