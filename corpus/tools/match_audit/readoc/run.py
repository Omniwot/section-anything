"""Run Section Anything Free on saved READoc extractions, with the library code from a given source
tree (main = rc/0.1.7 2066ab2 in .tmp/sa-017-rc, or fix/match-failures in .tmp/sa-match (F063; copied from F045).

usage (sa-014 env, python -I):
  python -I run.py <main|fix> <selection.json> <subset> <out_dir> [--only names.txt] [--docs a,b,...]
Writes <out_dir>/<main|fix>/free/<subset>__<id>.json (resolved sections). Skips files that exist,
so a stopped run resumes. Free makes no model calls. Stops itself through the laptop watchdog
(memory pressure 4, swap growth, heat)."""
import asyncio
import json
import sys
from pathlib import Path

SRC = {"main": "/Users/harshal/Desktop/omni/hustles/.tmp/sa-017-rc/packages/section-anything/src",
       "fix": "/Users/harshal/Desktop/omni/hustles/.tmp/sa-match/packages/section-anything/src"}
code, sel, subset, out = sys.argv[1:5]
sys.path.insert(0, SRC[code])
sys.path.insert(1, "/Users/harshal/Desktop/omni/hustles/.tmp/compare-2026-10-18/highest")
import watchdog  # noqa: E402
from section_anything import pipeline  # noqa: E402
from section_anything.extract import Extraction  # noqa: E402

assert pipeline.__file__.startswith(SRC[code]), pipeline.__file__
EXT = Path("/Users/harshal/Desktop/omni/hustles/.tmp/readoc-full-out/ext")
ids = json.load(open(sel))[subset]
names = [f"{subset}__{i}" for i in ids]
if "--only" in sys.argv:
    keep = set(Path(sys.argv[sys.argv.index("--only") + 1]).read_text().split())
    names = [n for n in names if n in keep]
if "--docs" in sys.argv:
    keep = set(sys.argv[sys.argv.index("--docs") + 1].split(","))
    names = [n for n in names if n in keep]
dest = Path(out) / code / "free"
dest.mkdir(parents=True, exist_ok=True)
if len(names) > 30:
    watchdog.start(f"match {code} {subset}", str(Path(out) / "watchdog.log"), pressure_limit=4, own_rss_limit_mb=2048)
for k, name in enumerate(names):
    f = dest / f"{name}.json"
    if f.exists() or not (EXT / f"{name}.extraction.json").exists():
        continue
    ext = Extraction.load(EXT / f"{name}.extraction.json")
    _raw, sections, _ = asyncio.run(pipeline.run(ext, "rules", "none", 0.0))
    f.write_text(json.dumps(sections, ensure_ascii=False))
    if k % 100 == 0:
        print(f"{code} {subset} {k + 1}/{len(names)}", flush=True)
print(f"{code} {subset} done", flush=True)
