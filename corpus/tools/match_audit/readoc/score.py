"""READoc heading-tree TEDS, main vs fix, paired per document.
usage (readoc-eval env): python score.py <run_dir> <setting> <selection.json> <subset> [--only names.txt] [--json out.json]
Prints n, means, paired change (fix - main) with a 95% bootstrap CI (4,000 resamples, seed 0),
better / same / worse (+-0.5 points), Wilcoxon p, and the five biggest changes each way."""
import json
import random
import statistics
import sys
from pathlib import Path
from scipy import stats
sys.path.insert(0, "/Users/harshal/Desktop/omni/hustles/.tmp/readoc-pilot")
import score as S  # noqa: E402

run, setting, sel, subset = sys.argv[1:5]
names = [f"{subset}__{i}" for i in json.load(open(sel))[subset]]
if "--only" in sys.argv:
    keep = set(Path(sys.argv[sys.argv.index("--only") + 1]).read_text().split())
    names = [n for n in names if n in keep]
rows = []
for n in names:
    i = n.split("__", 1)[1]
    g = S.heads((S.DATA / subset / "gt" / f"{i}.md").read_text(errors="ignore"))
    pm, pf = Path(run) / "main" / setting / f"{n}.json", Path(run) / "fix" / setting / f"{n}.json"
    if not g or not pm.exists() or not pf.exists():
        continue
    r = {"doc": n}
    for k, p in (("main", pm), ("fix", pf)):
        md = S.ours_md(p) or ""
        r[k] = 100 * S.calc_head_teds(S.heads(md) if md else [], g)
    rows.append(r)
d = [r["fix"] - r["main"] for r in rows]
rng = random.Random(0)
bs = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(4000)) if d else [0]
nz = [x for x in d if abs(x) > 1e-9]
res = {"setting": setting, "subset": subset, "n": len(rows),
       "main": statistics.mean(r["main"] for r in rows) if rows else None,
       "fix": statistics.mean(r["fix"] for r in rows) if rows else None,
       "change": statistics.mean(d) if d else None, "ci": [bs[100], bs[3899]] if d else None,
       "better": sum(x > 0.5 for x in d), "same": sum(-0.5 <= x <= 0.5 for x in d), "worse": sum(x < -0.5 for x in d),
       "wilcoxon_p": stats.wilcoxon(nz).pvalue if len(nz) >= 10 else None, "rows": rows}
print(f"{setting} {subset}: n={res['n']} main {res['main']:.2f} fix {res['fix']:.2f} change {res['change']:+.2f} "
      f"(95% CI {res['ci'][0]:+.2f} to {res['ci'][1]:+.2f}) b/s/w {res['better']}/{res['same']}/{res['worse']} p={res['wilcoxon_p']}")
for r in sorted(rows, key=lambda r: r["fix"] - r["main"])[:5] + sorted(rows, key=lambda r: r["fix"] - r["main"])[-5:]:
    print(f"   {r['doc']}: {r['main']:.1f} -> {r['fix']:.1f}")
if "--json" in sys.argv:
    Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(res, indent=1))
