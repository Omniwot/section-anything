"""Track M (F063): tables from rows-<tag>-<gold>/ (match_audit.py).

usage: <venv python> match_report.py audit <split> [tags]      -> report-<split>.txt, summary-<split>.json
       ... match_report.py compare <split> base fix           -> compare-<split>.txt (paired bootstrap CIs)
Misses per 1,000 reference headings (pooled), precision (matched / predicted, pooled), causes as F056 tags them
(`cause`) and re-examined (`cause2`), and the two side metrics (label pairs; maximum pairing).
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

MODES = ["free-bm", "free-nobm", "free-hints-bm", "free-hints-nobm", "quick-haiku", "quick-luna", "standard-haiku",
         "standard-luna"]
GOLDS = ["v1", "v2", "v2.1"]
CAUSES = "abcdef"


def load(tag: str, gold: str, split: str) -> list[dict]:
    d = C.OUT / f"rows-{tag}-{gold}"
    rows = [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))]
    return [r for r in rows if "runs" in r and ("test" if r["doc"]["split"] == "test" else "dev") == split]


def agg(runs: list[tuple[dict, dict]]) -> dict:
    n_gold = sum(x["n_gold"] for _, x in runs)
    n_pred = sum(x["n_pred"] for _, x in runs)
    matched = sum(x["matched"] for _, x in runs)
    if not n_gold:
        return {}
    k = 1000 / n_gold
    c1 = Counter(m["cause"] for _, x in runs for m in x["misses"])
    c2 = Counter(m["cause2"] for _, x in runs for m in x["misses"])
    s1 = Counter(f"{m['cause']}:{m['sub']}" for _, x in runs for m in x["misses"] if m["cause"] == "e")
    s2 = Counter(f"{m['cause2']}:{m['sub2']}" for _, x in runs for m in x["misses"] if m["cause2"] == "e")
    moved = Counter(f"{m['sub']}->{m['cause2']}:{m['sub2']}" for _, x in runs for m in x["misses"]
                    if m["cause"] == "e" and m["cause2"] != "e")
    lab = sum(x["label_pairs"] for _, x in runs)
    mx = sum(x["max_pairs"] - x["matched"] for _, x in runs)
    return {"docs": len({r["doc"]["id"] for r, _ in runs}), "runs": len(runs), "gold": n_gold, "pred": n_pred,
            "per1000": round(k * (n_gold - matched), 1), "precision": round(matched / n_pred, 3) if n_pred else 0.0,
            "cause": {c: round(k * c1[c], 1) for c in CAUSES}, "cause2": {c: round(k * c2[c], 1) for c in CAUSES},
            "e_sub": {s: round(k * v, 1) for s, v in s1.most_common()},
            "e2_sub": {s: round(k * v, 1) for s, v in s2.most_common()},
            "e_retagged": {s: round(k * v, 1) for s, v in moved.most_common(12)},
            "label_pairs_per1000": round(k * lab, 1), "per1000_label_side": round(k * (n_gold - matched - lab), 1),
            "max_pairing_extra_per1000": round(k * mx, 1)}


def audit(split: str, tags: list[str]) -> None:
    out, lines = {}, []
    for tag in tags:
        for gold in GOLDS:
            rows = load(tag, gold, split)
            if not rows:
                continue
            lines.append(f"\n=== {tag} code, keys {gold}, {split} documents ({len(rows)}): miss/1k, causes (F056 | re-examined), precision")
            lines.append(f"{'mode':16s} {'docs':>4s} {'runs':>4s} {'gold':>6s} {'miss/1k':>8s} "
                         + " ".join(f"{c:>5s}" for c in CAUSES) + " | " + " ".join(f"{c:>5s}" for c in CAUSES)
                         + f" {'prec':>6s} {'lab-side':>8s} {'maxpair':>7s}")
            for mode in MODES:
                runs = [(r, x) for r in rows for x in r["runs"] if x["mode"] == mode]
                a = agg(runs)
                if not a:
                    continue
                out[f"{tag}|{gold}|{mode}"] = a
                lines.append(f"{mode:16s} {a['docs']:4d} {a['runs']:4d} {a['gold']:6d} {a['per1000']:8.1f} "
                             + " ".join(f"{a['cause'][c]:5.1f}" for c in CAUSES) + " | "
                             + " ".join(f"{a['cause2'][c]:5.1f}" for c in CAUSES)
                             + f" {a['precision']:6.3f} {a['per1000_label_side']:8.1f} {a['max_pairing_extra_per1000']:7.1f}")
            lines.append("  e sub-causes as F056 tags them, then re-examined (per 1,000):")
            for mode in MODES:
                a = out.get(f"{tag}|{gold}|{mode}")
                if a:
                    lines.append(f"    {mode:16s} F056: " + "; ".join(f"{k} {v}" for k, v in list(a["e_sub"].items())[:6]))
                    lines.append(f"    {'':16s} e2:   " + "; ".join(f"{k} {v}" for k, v in list(a["e2_sub"].items())[:8]))
                    lines.append(f"    {'':16s} e retagged: " + "; ".join(f"{k} {v}" for k, v in list(a["e_retagged"].items())[:6]))
            lines.append(f"  by genre ({tag}, {gold}): miss/1k, e (F056) -> e2, precision")
            for genre in sorted({r["doc"]["genre"] for r in rows}):
                for mode in MODES:
                    runs = [(r, x) for r in rows if r["doc"]["genre"] == genre for x in r["runs"] if x["mode"] == mode]
                    a = agg(runs)
                    if not a:
                        continue
                    out[f"{tag}|{gold}|{genre}|{mode}"] = a
                    lines.append(f"    {genre:26s} {mode:16s} n={a['docs']:3d} {a['per1000']:7.1f}  e {a['cause']['e']:5.1f} -> "
                                 f"{a['cause2']['e']:5.1f}  P {a['precision']:.3f}  e2: "
                                 + "; ".join(f"{k.split(':', 1)[1]} {v}" for k, v in list(a["e2_sub"].items())[:3]))
    (C.OUT / f"report-{split}.txt").write_text("\n".join(lines) + "\n")
    (C.OUT / f"summary-{split}.json").write_text(json.dumps(out, indent=1))
    print("\n".join(lines))


def per_doc(rows: list[dict], mode: str) -> dict[str, tuple[int, int, int, int, bool]]:
    """doc -> (missed, gold, matched, predicted, complete key), summed over the mode's runs."""
    out = {}
    for r in rows:
        xs = [x for x in r["runs"] if x["mode"] == mode]
        if xs:
            out[r["doc"]["id"]] = (sum(x["n_gold"] - x["matched"] for x in xs), sum(x["n_gold"] for x in xs),
                                   sum(x["matched"] for x in xs), sum(x["n_pred"] for x in xs), r["doc"]["complete"])
    return out


def f1(m, g, p) -> float:
    rec, prec = (m / g if g else 0.0), (m / p if p else 0.0)
    return 2 * rec * prec / (rec + prec) if rec + prec else 0.0


def boot(ids, a, b, n=10000, seed=7):
    """Paired bootstrap over documents of fix minus base: miss/1k (pooled), precision (pooled), mean F1 of
    complete-key documents. Returns (point, lo, hi) for each, and per-document better/same/worse on F1."""
    rnd = random.Random(seed)

    def stats(sample):
        mb, gb = sum(a[i][0] for i in sample), sum(a[i][1] for i in sample)
        mf, gf = sum(b[i][0] for i in sample), sum(b[i][1] for i in sample)
        pb = sum(a[i][2] for i in sample) / max(1, sum(a[i][3] for i in sample))
        pf = sum(b[i][2] for i in sample) / max(1, sum(b[i][3] for i in sample))
        comp = [i for i in sample if a[i][4]]
        fd = (sum(f1(b[i][2], b[i][1], b[i][3]) - f1(a[i][2], a[i][1], a[i][3]) for i in comp) / len(comp)) if comp else 0.0
        return (1000 * mf / max(1, gf) - 1000 * mb / max(1, gb), pf - pb, fd)

    point = stats(ids)
    draws = [stats([rnd.choice(ids) for _ in ids]) for _ in range(n)]
    ci = []
    for k in range(3):
        xs = sorted(d[k] for d in draws)
        ci.append((point[k], xs[int(0.025 * n)], xs[int(0.975 * n) - 1]))
    bsw = Counter()
    for i in ids:
        if a[i][4]:
            d = f1(b[i][2], b[i][1], b[i][3]) - f1(a[i][2], a[i][1], a[i][3])
            bsw["better" if d > 0.0005 else "worse" if d < -0.0005 else "same"] += 1
    return ci, bsw


def compare(split: str, base: str, fix: str) -> None:
    lines = [f"Paired comparison, {split} documents: {fix} minus {base} (bootstrap over documents, 10,000 draws, 95% CI).",
             "miss/1k and precision pooled over the mode's runs; F1 = mean per-document F1 over complete-key documents.\n"]
    out = {}
    for gold in GOLDS:
        ra, rb = load(base, gold, split), load(fix, gold, split)
        if not ra or not rb:
            continue
        lines.append(f"--- keys {gold}")
        for mode in MODES:
            a, b = per_doc(ra, mode), per_doc(rb, mode)
            ids = sorted(set(a) & set(b))
            if not ids:
                continue
            (dm, dp, df), bsw = boot(ids, a, b)
            base_k = 1000 * sum(a[i][0] for i in ids) / sum(a[i][1] for i in ids)
            fix_k = 1000 * sum(b[i][0] for i in ids) / sum(b[i][1] for i in ids)
            pa = sum(a[i][2] for i in ids) / max(1, sum(a[i][3] for i in ids))
            pb = sum(b[i][2] for i in ids) / max(1, sum(b[i][3] for i in ids))
            changed = sum(1 for i in ids if a[i] != b[i])
            out[f"{gold}|{mode}"] = {"docs": len(ids), "changed": changed, "miss1k": [round(base_k, 1), round(fix_k, 1)],
                                     "d_miss1k": [round(x, 1) for x in dm], "precision": [round(pa, 3), round(pb, 3)],
                                     "d_precision": [round(x, 4) for x in dp], "d_f1": [round(x, 4) for x in df],
                                     "f1_better_same_worse": [bsw["better"], bsw["same"], bsw["worse"]]}
            lines.append(f"  {mode:16s} docs {len(ids):3d} (changed {changed:3d})  miss/1k {base_k:6.1f} -> {fix_k:6.1f} "
                         f"({dm[0]:+.1f}, CI {dm[1]:+.1f} to {dm[2]:+.1f})  precision {pa:.3f} -> {pb:.3f} "
                         f"({dp[0]:+.4f}, CI {dp[1]:+.4f} to {dp[2]:+.4f})  F1 {df[0]:+.4f} (CI {df[1]:+.4f} to {df[2]:+.4f})"
                         f"  better/same/worse {bsw['better']}/{bsw['same']}/{bsw['worse']}")
    (C.OUT / f"compare-{split}.txt").write_text("\n".join(lines) + "\n")
    (C.OUT / f"compare-{split}.json").write_text(json.dumps(out, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    cmd, split = sys.argv[1], sys.argv[2]
    if cmd == "audit":
        audit(split, sys.argv[3].split(",") if len(sys.argv) > 3 else ["base", "fix"])
    else:
        compare(split, sys.argv[3], sys.argv[4])
