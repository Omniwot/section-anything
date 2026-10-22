"""Score the saved Markdown with READoc's heading-tree TEDS: option off vs on (demoted headers become
`text`) vs the TITLE variant (a demoted first header becomes `title`), with paired statistics.

TITLE variant: Docling's Markdown export writes a TitleItem as `# text` and does not rank it with the
section headers, so the variant is the "on" Markdown with the demoted first header's paragraph
turned back into a `# ` line.

READoc's scoring code is not bundled (its repository has no licence). Clone
https://github.com/icip-cas/READoc, download the dataset (MIT) from
https://huggingface.co/datasets/lazyc/READoc, then:

  READOC_SRC=<READoc clone>/src/evaluation READOC_DATA=<dataset dir with arxiv/ and github/> \
      python score.py <run_dir>          # <run_dir>/{arxiv,github}/<id>.<variant>.md from run_docling.py
"""

import json
import os
import random
import re
import statistics
import sys
import types
from pathlib import Path

from scipy import stats

sys.modules["pandoc"] = types.ModuleType("pandoc")  # READoc uses pandoc only for tables
sys.path.insert(0, os.environ["READOC_SRC"])
from segmentation import extract_materials  # noqa: E402
from standardization import clean_md  # noqa: E402
from utils import calc_head_teds  # noqa: E402

DATA = Path(os.environ["READOC_DATA"])
RUN = Path(sys.argv[1])
SEL = json.load(open(Path(__file__).parent / "selection.json"))
HEAD = re.compile(r"^(#+)\s+(.*\S)\s*$")


def heads(md: str) -> list[str]:
    return extract_materials(clean_md(md))["subtask"]["heads"]


def title_variant(off_md: str, on_md: str) -> str:
    off_h = [m.group(2) for ln in off_md.splitlines() if (m := HEAD.match(ln))]
    lines = on_md.splitlines()
    on_h = [(i, m.group(2)) for i, ln in enumerate(lines) if (m := HEAD.match(ln))]
    if not off_h or any(t == off_h[0] for _, t in on_h):
        return on_md  # first header kept
    stop = on_h[0][0] if on_h else len(lines)
    for i in range(stop):
        if lines[i].strip() == off_h[0]:
            lines[i] = f"# {off_h[0]}"
            break
    return "\n".join(lines) + "\n"


def paired(name: str, pairs: list[tuple[float, float]]) -> str:
    d = [100 * (y - x) for x, y in pairs]
    rng = random.Random(0)
    bs = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(4000))
    p = stats.wilcoxon(d).pvalue if any(abs(x) > 1e-9 for x in d) else 1.0
    return (f"| {name} | {len(d)} | {100 * statistics.mean(x for x, _ in pairs):.1f} | "
            f"{100 * statistics.mean(y for _, y in pairs):.1f} | {statistics.mean(d):+.2f} | "
            f"{bs[100]:+.2f} to {bs[3899]:+.2f} | {sum(x > 0.5 for x in d)} / "
            f"{sum(abs(x) <= 0.5 for x in d)} / {sum(x < -0.5 for x in d)} | {p:.2g} |")


for subset in ("arxiv", "github"):
    rows = []
    for i in SEL[subset]:
        gold = heads((DATA / subset / "gt" / f"{i}.md").read_text(errors="ignore"))
        r = {}
        for suffix in ("", "_deep", "_top"):
            off_p, on_p = RUN / subset / f"{i}.off{suffix}.md", RUN / subset / f"{i}.on{suffix}.md"
            if off_p.exists() and on_p.exists():
                off_md, on_md = off_p.read_text(errors="ignore"), on_p.read_text(errors="ignore")
                r["off" + suffix] = calc_head_teds(heads(off_md), gold)
                r["on" + suffix] = calc_head_teds(heads(on_md), gold)
                r["title" + suffix] = calc_head_teds(heads(title_variant(off_md, on_md)), gold)
        if "on" in r:
            rows.append(r)
    deep = [r for r in rows if "on_deep" in r]
    print(f"\n### READoc-{subset}: {len(rows)} documents\n")
    print("| Comparison | n | before | after | mean change | 95% CI | better / same / worse | Wilcoxon p |")
    print("|---|---|---|---|---|---|---|---|")
    print(paired("off -> on (text)", [(r["off"], r["on"]) for r in rows]))
    print(paired("off -> on (title)", [(r["off"], r["title"]) for r in rows]))
    print(paired("deepest level removed: off -> on (text)", [(r["off_deep"], r["on_deep"]) for r in deep]))
    print(paired("deepest level removed: off -> on (title)", [(r["off_deep"], r["title_deep"]) for r in deep]))
    print(paired("top level only: off -> on (text)", [(r["off_top"], r["on_top"]) for r in rows]))
