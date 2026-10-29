"""Compute the saved runs the Space shows for its three example papers. Run once by the maintainers,
never on the Space (the Space has no API key and calls no model).

For each paper: download it from arXiv, run section-anything in free, quick and standard mode, and
write examples/<arXiv id>.json with the headings, levels, pages and character spans of every run,
plus the run's version, model, date, calls, tokens, cost and time. The papers' text is not stored:
the Space extracts it again from the PDF it downloads and shows a section's text only when the slice
matches the saved run's hash of that section and its heading is where the span starts. pdfminer's
layout analysis can order a few lines (table cells) differently from one extraction to the next, so
each section also keeps a hash of its lines in sorted order (`lines_sha`).

    python make_examples.py --estimate          # extract and estimate the model cost; no model call
    OPENAI_API_KEY=... python make_examples.py  # free, quick and standard; sends the papers' text to the model

READoc heading-tree TEDS is added afterwards by a separate script (READoc's scorer is not part of
this repository); see the `readoc` field.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import section_anything
from section_anything import Settings, extract_pdf
from section_anything.markers import canon
from section_anything.pipeline import BY_ID

HERE = Path(__file__).parent
OUT = HERE / "examples"
SETTINGS = Settings(max_mb=20, max_pages=100, extract_timeout_seconds=120)
CAP_USD = 0.50  # stop if the estimate for all papers and modes is higher

EXAMPLES = [
    {
        "id": "2304.08485v2",
        "button": "Visual Instruction Tuning · 25 pages, bookmarks",
        "title": "Visual Instruction Tuning",
        "authors": "Liu et al.",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "why": "The paper in the README's demo. Its PDF has bookmarks, which Free uses as the outline. "
               "Not in READoc, so there is no answer key and no score.",
    },
    {
        "id": "2209.07299v2",
        "button": "Knowledge Is Flat · 13 pages, no bookmarks",
        "title": "Knowledge Is Flat: A Seq2Seq Generative Framework for Various Knowledge Graph Completion",
        "authors": "Chen et al.",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "why": "No PDF bookmarks, so Free has only typography and numbering to go on. Picked by a fixed "
               "rule: of the 73 held-out READoc arXiv papers with no bookmarks, 8-100 pages and at least "
               "8 headings in the answer key, the CC BY paper whose Free (0.1.5) READoc heading-tree TEDS "
               "was closest to the group's median (55.9). Its Free score, 49.9, is at the group's 41st "
               "percentile.",
    },
    {
        "id": "2305.06327v1",
        "button": "Thermalization, Chaos and Hydrodynamics · 88 pages, nested",
        "title": "Thermalization, Chaos and Hydrodynamics in Classical Hamiltonian Systems",
        "authors": "Ganapa",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "why": "Long and deeply nested: 88 pages, PDF bookmarks, and an answer key four levels deep. Picked "
               "by a fixed rule: of the 39 held-out READoc arXiv papers with 30-100 pages and an answer key "
               "at least three levels deep, the CC BY paper whose Free (0.1.5) READoc heading-tree TEDS was "
               "closest to the group's median (68.7). Its Free score, 60.4, is at the group's 38th "
               "percentile.",
    },
]


def pdf_urls(arxiv_id: str) -> list[str]:
    return [f"https://arxiv.org/pdf/{arxiv_id}", f"https://export.arxiv.org/pdf/{arxiv_id}"]


def heading_at(text: str, sec: dict) -> bool | None:
    """Does the section's printed heading appear where its span starts? None: nothing to check
    (front matter, or a title the model wrote)."""
    flags = sec.get("flags") or []
    if "front_matter" in flags or "generated_title" in flags or not (sec.get("title") or "").strip():
        return None
    title = canon(sec["title"])[:60]
    return bool(title) and title in canon(text[sec["start"]:sec["start"] + 400 + len(sec["title"])])


def slice_hashes(part: str) -> dict:
    """`sha`: the section's text. `lines_sha`: its lines in any order, so a section whose table cells came
    out in another order still matches (the same lines between the same headings)."""
    return {"sha": sha256(part)[:16], "lines_sha": sha256("\n".join(sorted(part.split("\n"))))[:16]}


def download(arxiv_id: str, folder: Path) -> Path:
    path = folder / f"{arxiv_id}.pdf"
    if not path.exists():
        req = urllib.request.Request(pdf_urls(arxiv_id)[0], headers={"User-Agent": "section-anything-space"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if not data.startswith(b"%PDF-"):
            sys.exit(f"{arxiv_id}: not a PDF")
        path.write_bytes(data)
        time.sleep(3)  # be gentle with arXiv
    return path


def sha256(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def estimate(paths: dict[str, Path]) -> float:
    total = 0.0
    for arxiv_id, path in paths.items():
        ext = extract_pdf(path, settings=SETTINGS)
        for mode, strategy in (("quick", "llm_review"), ("standard", "llm_text")):
            model = getattr(SETTINGS, f"{mode}_model")
            e = BY_ID[strategy].estimate(ext, model, SETTINGS)
            usd = SETTINGS.price_for(model).estimate(e.input_tokens, e.output_tokens, e.calls)
            total += usd
            print(f"{arxiv_id} {mode:<8} {model}: {e.calls} calls, ~{e.input_tokens:,} in / "
                  f"{e.output_tokens:,} out tokens, ~${usd:.4f}")
    print(f"estimate, all papers and modes: ${total:.4f} (stop above ${CAP_USD:.2f})")
    return total


def run(arxiv_id: str, path: Path, meta: dict) -> dict:
    data = path.read_bytes()
    out = {"schema": 1, **meta, "arxiv": f"https://arxiv.org/abs/{arxiv_id}", "pdf_urls": pdf_urls(arxiv_id),
           "pdf_sha256": sha256(data), "pdf_bytes": len(data), "readoc": None, "runs": {}}
    for mode in ("free", "quick", "standard"):
        opts = {"max_usd": CAP_USD, "over_budget": "fail"} if mode != "free" else {}
        tree = section_anything.section(path, mode, settings=SETTINGS, **opts)
        if tree.mode != mode or tree.downgraded:
            sys.exit(f"{arxiv_id} {mode}: ran as {tree.mode} ({tree.downgraded})")
        out.update(pages=tree.pages, text_chars=len(tree.text))
        s = tree.summary()
        out["runs"][mode] = {
            "section_anything": section_anything.__version__,
            "mode": mode,
            "model": tree.model,
            "date": datetime.now().strftime("%Y-%m-%d"),  # local date of the run
            "seconds": s["seconds"],
            "calls": s["calls"],
            "input_tokens": s["input_tokens"],
            "output_tokens": s["output_tokens"],
            "cost_usd": tree.cost_usd,
            "usage": tree.usage,
            "text_sha256": sha256(tree.text),
            "sections": [{**sec, **slice_hashes(tree.text[sec["start"]:sec["end"]]),
                          "heading_check": heading_at(tree.text, sec)} for sec in tree.sections],
        }
        print(f"{arxiv_id} {mode:<8} {tree.model or '-'}: {s['sections']} sections, {s['calls']} calls, "
              f"${tree.cost_usd:.4f}, {s['seconds']:.1f} s", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--estimate", action="store_true", help="estimate the model cost only")
    ap.add_argument("--pdfs", type=Path, help="folder for the downloaded PDFs (default: a temporary folder)")
    args = ap.parse_args()
    folder = args.pdfs or Path(tempfile.mkdtemp(prefix="sa-examples-"))
    folder.mkdir(parents=True, exist_ok=True)
    paths = {e["id"]: download(e["id"], folder) for e in EXAMPLES}
    total = estimate(paths)
    if args.estimate:
        return
    if total > CAP_USD:
        sys.exit("estimate over the cap: nothing sent to a model")
    OUT.mkdir(exist_ok=True)
    for e in EXAMPLES:
        result = run(e["id"], paths[e["id"]], e)
        (OUT / f"{e['id']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                                             encoding="utf-8")


if __name__ == "__main__":
    main()
