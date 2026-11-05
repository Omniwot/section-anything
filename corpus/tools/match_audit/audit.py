"""Zero-miss track A, steps 1 and 2 (F056): per document, every reference heading in every run (Free re-run
on rc/0.1.7; Quick and Standard from saved runs), the cause of each miss, and which candidate sources
hold each heading.

usage: PYTHONPATH=<sa-miss src> <sa-017 venv python> audit.py run [ids...]   (writes rows/<id>.json)
       ... audit.py one <id>                                              (prints a summary)
Causes: a text not extracted (a2: not in the text layer at all, by pypdfium2 too); b no heading signal
(plain body line); c a heading signal, removed by a rule (which); d the model left it out; e a match
failure (title or page); f the answer key (anchored on the printed contents list).
"""

from __future__ import annotations

import glob
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
from section_anything.docling_input import attach_hints, hints_of  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402
from section_anything.evaluate import _sim  # noqa: E402
from section_anything.pipeline import _line_at  # noqa: E402
from section_anything.strategies import rules as R  # noqa: E402
from section_anything.structure import anchor_bookmarks, anchor_toc, furniture_of, toc_of  # noqa: E402

GOLD = __import__("os").environ.get("GOLD", "v1")
ROWS = C.OUT / ("rows" if GOLD == "v1" else f"rows-{GOLD}")
QF = C.T / "quickfix-eval/out/quick-haiku/fix"
QK = C.T / "structure-eval/out/quick-haiku/base"
QKL = C.T / "structure-eval/out/quick-luna/base"
QJ = C.T / "adapter-validate/runs"
RES = C.ROOT / "section-anything/corpus/results"
SW = C.T / "standard-swings/out/claude-haiku-5-5"


def saved_runs(doc: dict) -> list[tuple[str, str, int, list[dict]]]:
    """(mode, source, repeat, sections) of the saved model runs on this document."""
    i, out = doc["id"], []

    def reps(pattern: str) -> list[str]:
        return sorted(glob.glob(pattern))

    fix = reps(str(QF / f"{i}--r*.json"))
    k = reps(str(QK / f"{i}--r*.json"))
    j = reps(str(QJ / "*" / "q_base" / f"{i}--r*.json"))
    if fix:
        out += [("quick-haiku", "F052 fix arm", n, json.loads(Path(p).read_text())["secs"]) for n, p in enumerate(fix)]
    elif k:
        out += [("quick-haiku", "F050 base arm", n, json.loads(Path(p).read_text())["secs"]) for n, p in enumerate(k)]
    elif j:
        out += [("quick-haiku", "F049 base arm", n, json.loads(Path(p).read_text())["out"]) for n, p in enumerate(j)]
    for n, p in enumerate(reps(str(QKL / f"{i}--r*.json"))):
        out.append(("quick-luna", "F050 base arm", n, json.loads(Path(p).read_text())["secs"]))
    if doc["set"] == "corpus":
        for mode, d, suf in (("quick-luna", "2026-10-20-llm_review-gpt-6-luna", "llm_review"),
                             ("standard-luna", "2026-10-20-llm_text-gpt-6-luna", "llm_text")):
            p = RES / d / f"{i}.{suf}.json"
            if p.exists():
                out.append((mode, f"corpus results {d[:10]}", 0, json.loads(p.read_text())))
    sw = reps(str(SW / "final" / "*" / f"{i}.run*.json")) + reps(str(SW / "after" / "unseen" / f"{i}.run*.json"))
    for n, p in enumerate(sw):
        x = json.loads(Path(p).read_text())
        out.append(("standard-haiku", "F051 " + Path(p).parent.parent.name + "/" + Path(p).parent.name, n, x["resolved"]))
    return out


def pred_lines(ext, spans: C.Spans, preds: list[dict]) -> None:
    """Each prediction's first line in this extraction: its own offset when the text there is its
    title, else its title looked up on its page."""
    for p in preds:
        line = None
        if p.get("first_line") is not None and p["first_line"] < len(ext.lines):
            line = p["first_line"]
        elif p.get("start") is not None and p["start"] < len(ext.text):
            line = _line_at(ext, p["start"])
        if line is not None:
            t = " ".join(x.text for x in ext.lines[line:line + 3])
            if _sim(p["title"], t) < 60 and C.norm(p["title"])[:12] not in C.norm(t):
                line = None
        if line is None:
            hit = spans.best(p["title"], [p["page"]], min_score=70)
            line = hit[1][0] if hit else None
        p["line"] = line


def cause(doc: dict, g: dict, L: dict, preds: list[dict], kind: str, strict: C.CandCtx, loose: C.CandCtx,
          trace: dict | None) -> tuple[str, str]:
    st = L["status"]
    if st == "contents":
        return ("f", "contents_anchored") if L.get("body") else ("f", "contents_only")
    if st == "none":
        if C.in_text_layer(doc["pdf"], g["title"], g["page"]):
            return "a", "missed_by_our_extractor"
        return "a", "not_in_text_layer"
    gp, gt = g["page"], g["title"]
    if any(abs(p["page"] - gp) <= 1 and _sim(gt, p["title"]) >= C.THRESHOLD for p in preds):
        return "e", "taken_by_duplicate"
    if st == "far":
        return "e", "gold_page_far"
    if any(abs(p["page"] - gp) > 1 and _sim(gt, p["title"]) >= C.THRESHOLD for p in preds):
        return "e", "page_off"
    lines = L["lines"]
    ng = C.norm(gt)
    for p in preds:
        if p.get("line") is None:
            continue
        npt = C.norm(p["title"])
        contains = bool(ng) and (ng in npt or fuzz.partial_ratio(ng, npt) >= 90) and len(npt) > len(ng)
        if p["line"] in lines:
            if contains:
                return "e", "title_merged"
            if npt and npt in ng:
                return "e", "title_split"
            return "e", "title_differs"
        if p["line"] == lines[0] - 1 and contains:
            return "e", "title_merged"
    if kind == "free":
        kept = [i for i in lines if i in strict.kept]
        if not kept:
            reasons = [strict.why(i) for i in lines]
            r = next((x for x in reasons if x != "plain"), "plain")
            return ("b", "plain") if r == "plain" else ("c", r)
        stage = C.free_stage(trace, kept)
        return ("e", "title_differs") if stage == "kept_title_differs" else ("c", stage)
    in_strict = any(i in strict.kept for i in lines)
    in_loose = any(i in loose.kept for i in lines)
    if kind == "quick":
        if not in_loose:
            reasons = [loose.why(i) for i in lines]
            r = next((x for x in reasons if x != "plain"), "plain")
            return ("b", "plain") if r == "plain" else ("c", "loose:" + r)
        return "d", "model_rejected"
    return "d", "model_missed:" + ("free_candidate" if in_strict else "loose_candidate" if in_loose else "no_signal")


def score_run(doc, gold, loc, ext, spans, sections, kind, strict, loose, trace) -> dict:
    preds = C.heads(sections)
    pairs = C.pair(gold, preds)
    pred_lines(ext, spans, preds)
    misses = []
    for gi, g in enumerate(gold):
        if gi in pairs:
            continue
        c, sub = cause(doc, g, loc[gi], preds, kind, strict, loose, trace)
        misses.append({"gi": gi, "cause": c, "sub": sub})
    return {"n_pred": len(preds), "n_gold": len(gold), "matched": len(pairs), "misses": misses,
            "preds": [[p["title"], p["page"], p.get("line")] for p in preds]}


def ceiling(ext_nobm, ext_bm, hinted, gold, loc, strict: C.CandCtx, loose: C.CandCtx) -> list[dict]:
    body = ext_nobm.body_size()
    furn = furniture_of(ext_nobm)
    bm_lines = {a.line for a in anchor_bookmarks(ext_bm)} if ext_bm is not None and ext_bm.outline else set()
    bm_titles = [(o.title, o.page) for o in (ext_bm.outline if ext_bm is not None else [])]
    toc_anch = {a.line for a in anchor_toc(ext_nobm)}
    toc_titles = [e.title for e in toc_of(ext_nobm).entries]
    dl = hints_of(hinted).headers if hinted is not None and hints_of(hinted) else None
    lab = R._label_lines(ext_nobm, furn | set(toc_of(ext_nobm).lines), body, 0.8, R.side_notes(ext_nobm))
    out = []
    for gi, g in enumerate(gold):
        L = loc[gi]
        lines = (L.get("body") or {}).get("lines") if L["status"] == "contents" else L.get("lines")
        row = {"gi": gi, "status": L["status"]}
        if not lines:
            row["union"] = False
            out.append(row)
            continue
        lns = [ext_nobm.lines[i] for i in lines]
        first = lns[0]
        text = " ".join(x.text for x in lns)
        row |= {
            "furniture": any(i in furn for i in lines),
            "typography": any(x.size >= body + 0.8 or (x.bold and x.size >= body - 0.3) for x in lns),
            "typography_loose": any(x.size >= body + 0.4 or x.bold for x in lns),
            "numbering": bool(R.NUMBERING.match(first.text) or R.NUMBERING.match(text)),
            "labels": bool(R.STRUCTURE_LABEL.match(first.text) or R.LABEL_ONLY.match(R._label_text(first.text))
                           or any(i in lab or i in lab.values() for i in lines)),
            "bookmarks": bool(set(lines) & bm_lines or (lines[0] - 1) in bm_lines)
                         or any(abs(p - g["page"]) <= 1 and _sim(g["title"], t) >= C.THRESHOLD for t, p in bm_titles),
            "contents": bool(set(lines) & toc_anch) or any(_sim(g["title"], t) >= C.THRESHOLD for t in toc_titles),
            "docling": None if dl is None else bool(set(lines) & dl),
            "free_pool": any(i in strict.kept for i in lines),
            "quick_pool": any(i in loose.kept for i in lines),
            "size_delta": round(first.size - body, 1), "bold": first.bold, "words": len(text.split()),
        }
        row["union"] = any(row[k] for k in ("typography", "numbering", "labels", "bookmarks", "contents", "docling",
                                            "free_pool", "quick_pool"))
        if not row["union"]:
            row["why"] = loose.why(lines[0])
        out.append(row)
    return out


def process(doc: dict) -> dict:
    t0 = time.monotonic()
    res = {"doc": {k: doc[k] for k in ("id", "genre", "set", "split", "complete", "pages")}, "runs": []}
    ext = C.load_ext(doc, "nobm")
    if ext is None:
        res["error"] = "no saved extraction"
        return res
    gold = C.gold_of(doc, GOLD)
    spans = C.Spans(ext)
    loc = C.locate(ext, gold, spans)
    res["loc"] = loc
    strict, loose = C.CandCtx(ext, False), C.CandCtx(ext, True)

    def add(mode, source, rep, sections, kind, s, lo, tr, e=ext):
        r = score_run(doc, gold, loc, e, spans, sections, kind, s, lo, tr)
        res["runs"].append({"mode": mode, "source": source, "rep": rep} | r)

    tr = C.free_trace(ext)
    add("free-nobm", "rc/0.1.7 re-run", 0, tr["sections"], "free", strict, loose, tr)
    ext_bm = C.load_ext(doc, "bm")
    if ext_bm.outline:
        s_bm, l_bm = C.CandCtx(ext_bm, False), C.CandCtx(ext_bm, True)
        trb = C.free_trace(ext_bm)
        add("free-bm", "rc/0.1.7 re-run", 0, trb["sections"], "free", s_bm, l_bm, trb, ext_bm)
    res["has_outline"] = bool(ext_bm.outline)
    hinted = None
    for variant in ("bm", "nobm"):
        hier = C.docling_of(doc, variant)
        if hier is None:
            continue
        e = C.load_ext(doc, variant)
        try:
            attach_hints(e, hier)
        except Exception as exc:  # noqa: BLE001
            res.setdefault("hint_errors", {})[variant] = f"{type(exc).__name__}: {exc}"[:200]
            continue
        hinted = hinted or e
        s_h, l_h = C.CandCtx(e, False), C.CandCtx(e, True)
        trh = C.free_trace(e)
        add(f"free-hints-{variant}", "rc/0.1.7 re-run", 0, trh["sections"], "free", s_h, l_h, trh, e)
    for mode, source, rep, sections in saved_runs(doc):
        kind = "quick" if mode.startswith("quick") else "standard"
        add(mode, source, rep, sections, kind, strict, loose, None)
    res["ceiling"] = ceiling(ext, ext_bm, hinted, gold, loc, strict, loose)
    res["seconds"] = round(time.monotonic() - t0, 1)
    return res


def main() -> None:
    cmd, ids = sys.argv[1], sys.argv[2:]
    docs = [d for d in C.registry() if not ids or d["id"] in ids]
    ROWS.mkdir(parents=True, exist_ok=True)
    if cmd == "one":
        r = process(docs[0])
        for run in r["runs"]:
            from collections import Counter
            print(run["mode"], run["source"], run["rep"], run["n_gold"], run["matched"], run["n_pred"],
                  Counter(f"{m['cause']}:{m['sub']}" for m in run["misses"]).most_common(6))
        print("seconds", r.get("seconds"), "error", r.get("error"))
        return
    for d in docs:
        dst = ROWS / f"{d['id']}.json"
        if dst.exists():
            continue
        try:
            r = process(d)
        except Exception as exc:  # noqa: BLE001 -- one document must not stop the rest
            r = {"doc": {k: d[k] for k in ("id", "genre", "set", "split", "complete", "pages")},
                 "error": f"{type(exc).__name__}: {exc}"[:300]}
        dst.write_text(json.dumps(r, ensure_ascii=False))
        print(f"{d['id'][:50]:50s} {d['set']:9s} {r.get('seconds', '-')}s runs={len(r.get('runs', []))} "
              f"{r.get('error', '')}", flush=True)


if __name__ == "__main__":
    main()
