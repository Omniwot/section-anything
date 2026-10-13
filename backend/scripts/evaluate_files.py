"""Score the free strategies on every file in corpus/manifest.json (no upload,
no model calls). Extractions are cached by file hash under corpus/files/cache.

    python scripts/evaluate_files.py                      # all categories
    python scripts/evaluate_files.py --category slides --show
    python scripts/evaluate_files.py --extract-only --shard 0/2 &   # fill the cache in parallel
    python scripts/evaluate_files.py --extract-only --shard 1/2

Per document: precision, recall, F1, level agreement. Precision is only
meaningful for documents whose gold is complete (bookmark gold often skips
the deepest levels), so category precision and F1 average complete
documents only; recall averages all. Headings on image-only pages stay in
the gold (a sectioner without OCR should miss them) and are counted per
document. Results go to corpus/results/.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CORPUS = BACKEND.parent / "corpus"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(CORPUS / "tools"))

from app.core.config import settings  # noqa: E402
from app.sectioning import pipeline  # noqa: E402
from app.sectioning.evaluate import score  # noqa: E402
from common import extraction  # noqa: E402


def _extract(path: str) -> str | None:
    try:
        extraction(Path(path))
        return None
    except Exception as e:  # noqa: BLE001 — reported per file
        return f"{type(e).__name__}: {e}"


def _mean(xs: list[float]) -> float | None:
    return round(statistics.mean(xs), 3) if xs else None


def _fmt(x: float | None) -> str:
    return "  — " if x is None else f"{x:.2f}"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", action="append")
    ap.add_argument("--id", action="append", help="limit to these document ids")
    ap.add_argument("--strategy", action="append", help="limit to these free strategy ids")
    ap.add_argument("--extract-only", action="store_true", help="only fill the extraction cache")
    ap.add_argument("--shard", default="0/1", help="with --extract-only: i/N takes every Nth file from i")
    ap.add_argument("--show", action="store_true", help="print missed and extra headings")
    args = ap.parse_args()

    docs = json.loads((CORPUS / "manifest.json").read_text())["documents"]
    docs = [d for d in docs if (not args.category or d["category"] in args.category) and (not args.id or d["id"] in args.id)]
    strategies = [s for s in pipeline.STRATEGIES if not s.uses_llm and (not args.strategy or s.id in args.strategy)]

    uploaded = {}
    for pdf in Path(settings.DATA_DIR, "docs").resolve().glob("*/original.pdf"):  # noqa: ASYNC240 (one-off CLI)
        uploaded[hashlib.sha256(pdf.read_bytes()).hexdigest()] = pdf
    for d in docs:
        if "file" not in d and d.get("sha256") in uploaded:
            d["file"] = str(uploaded[d["sha256"]])
    skipped = [d["id"] for d in docs if "file" not in d]
    if skipped:
        print("not found locally, skipped:", ", ".join(skipped))
    docs = [d for d in docs if "file" in d]
    paths = [str(CORPUS / d["file"]) for d in docs]
    errors: dict[str, str] = {}
    if args.extract_only:
        i, n = (int(x) for x in args.shard.split("/"))
        t0 = time.time()
        for p in paths[i::n]:
            err = _extract(p)
            print(f"{Path(p).name}: {err or 'ok'}  ({time.time() - t0:.0f}s)", flush=True)
        return

    rows = []
    for d, p in zip(docs, paths, strict=True):
        row = {"id": d["id"], "category": d["category"], "complete": d.get("complete", True),
               "variant": d.get("variant", "")}
        if p in errors:
            rows.append({**row, "error": errors[p]})
            print(f"{d['id']}: extraction failed ({errors[p][:80]})")
            continue
        try:
            ext = extraction(Path(p))
        except Exception as e:  # noqa: BLE001
            rows.append({**row, "error": f"{type(e).__name__}: {e}"})
            print(f"{d['id']}: extraction failed ({type(e).__name__}: {str(e)[:80]})")
            continue
        gold = json.loads((CORPUS / d["gold"]).read_text())
        row["gold"] = len(gold)
        row["gold_image_only"] = sum(1 for g in gold if g.get("image_only"))
        for s in strategies:
            t = time.time()
            _raw, sections, _ = await pipeline.run(ext, s.id, settings.LLM_MODEL, 0.0)
            acc = score(gold, sections) if gold else {}
            row[s.id] = {"sections": len(sections), "seconds": round(time.time() - t, 2),
                         **{k: acc.get(k) for k in ("precision", "recall", "f1", "level_agreement")}}
            r = row[s.id]
            print(f"{d['id']:<42} {s.id:<6} gold {len(gold):>4}  sections {len(sections):>4}  "
                  f"P {_fmt(r['precision'])}  R {_fmt(r['recall'])}  F1 {_fmt(r['f1'])}"
                  + ("" if row["complete"] else "  (recall only)")
                  + (f"  ({row['gold_image_only']} gold on image-only pages)" if row["gold_image_only"] else ""))
            if args.show and acc:
                print("    missed:", acc["missed"][:15])
                print("    extra: ", acc["extra"][:15])
        rows.append(row)

    print()
    summary = {}
    for s in strategies:
        print(f"{s.id}: per category (P and F1 over complete-gold documents; R over all with gold)")
        print(f"  {'category':<12} docs  P     R     F1    levels")
        cats = sorted({r["category"] for r in rows})
        for c in cats + ["ALL"]:
            rs = [r for r in rows if (c == "ALL" or r["category"] == c) and s.id in r and r.get("gold")]
            comp = [r for r in rs if r["complete"]]
            m = {"docs": len(rs),
                 "precision": _mean([r[s.id]["precision"] for r in comp]),
                 "recall": _mean([r[s.id]["recall"] for r in rs]),
                 "f1": _mean([r[s.id]["f1"] for r in comp]),
                 "levels": _mean([r[s.id]["level_agreement"] for r in rs if r[s.id]["level_agreement"] is not None])}
            summary.setdefault(s.id, {})[c] = m
            print(f"  {c:<12} {m['docs']:>4}  {_fmt(m['precision'])}  {_fmt(m['recall'])}  {_fmt(m['f1'])}  "
                  f"{_fmt(m['levels'])}")
    nogold = [r for r in rows if not r.get("gold") and "error" not in r]
    if nogold:
        print("\nno gold (section count only):",
              ", ".join(f"{r['id']}={r[strategies[0].id]['sections']}" for r in nogold if strategies))
    if errors or any("error" in r for r in rows):
        print("errors:", ", ".join(r["id"] for r in rows if "error" in r))

    out = CORPUS / "results" / f"{date.today()}-free.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "documents": rows}, indent=1) + "\n")
    print("\nwrote", out.relative_to(CORPUS.parent))


if __name__ == "__main__":
    asyncio.run(main())
