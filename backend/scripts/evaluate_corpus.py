"""Score strategies on golden-corpus documents that exist locally. Free by default.

    python scripts/evaluate_corpus.py                 # free strategies only
    python scripts/evaluate_corpus.py --replay        # also re-resolve saved LLM proposals (free)
    python scripts/evaluate_corpus.py --strategy rules --show

Documents are matched to `corpus/manifest.json` by SHA-256 of
`data/docs/<id>/original.pdf`. `--replay` re-runs the resolver on raw proposals
saved by earlier runs (`data/docs/<id>/runs/<run>.raw.json`), so resolver
changes can be measured without paying for new model calls.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.sectioning import pipeline  # noqa: E402
from app.sectioning.evaluate import score  # noqa: E402
from app.sectioning.extract import Extraction  # noqa: E402
from app.sectioning.jobs import corpus_gold  # noqa: E402
from app.sectioning.markers import Locator  # noqa: E402
from app.sectioning.strategies.base import RawSection  # noqa: E402


def _docs() -> list[tuple[int, Path, list[dict]]]:
    out = []
    for d in sorted(Path(settings.DATA_DIR, "docs").iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 0):
        pdf = d / "original.pdf"
        if not pdf.exists() or not (d / "extraction.json").exists():
            continue
        gold = corpus_gold(hashlib.sha256(pdf.read_bytes()).hexdigest())
        if gold:
            out.append((int(d.name), d, gold))
    return out


def _line(name: str, acc: dict, n: int) -> str:
    lv = acc["level_agreement"]
    return (
        f"  {name:<28} sections {n:>4}  P {acc['precision']:.2f}  R {acc['recall']:.2f}  "
        f"F1 {acc['f1']:.2f}  levels {'—' if lv is None else f'{lv:.2f}'}"
    )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", action="append", help="limit to these strategy ids")
    ap.add_argument("--replay", action="store_true", help="re-resolve saved raw proposals of earlier LLM runs")
    ap.add_argument("--show", action="store_true", help="print missed and extra headings")
    args = ap.parse_args()

    docs = _docs()
    if not docs:
        print("No golden-corpus documents found under", Path(settings.DATA_DIR, "docs"))
        return
    for doc_id, d, gold in docs:
        ext = Extraction.load(d / "extraction.json")
        print(f"doc {doc_id}: {len(ext.pages)} pages, {len(gold)} gold headings")
        for s in pipeline.STRATEGIES:
            if s.uses_llm or (args.strategy and s.id not in args.strategy):
                continue
            _raw, sections, _ = await pipeline.run(ext, s.id, settings.LLM_MODEL, 0.0)
            acc = score(gold, sections)
            print(_line(s.id, acc, len(sections)))
            if args.show:
                print("    missed:", acc["missed"])
                print("    extra: ", acc["extra"])
        if args.replay:
            for raw_path in sorted((d / "runs").glob("*.raw.json")):
                saved = json.loads(raw_path.read_text())
                if args.strategy and saved["strategy"] not in args.strategy:
                    continue
                raw = [RawSection(**r) for r in saved["raw"]]
                sections = pipeline.finish(raw, ext, Locator(ext.text))
                acc = score(gold, sections)
                print(_line(f"replay run {raw_path.stem.split('.')[0]} ({saved['strategy']})", acc, len(sections)))
                if args.show:
                    print("    missed:", acc["missed"])
                    print("    extra: ", acc["extra"])


if __name__ == "__main__":
    asyncio.run(main())
