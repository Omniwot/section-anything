"""Check that every gold title appears in the PDF text of its gold page.

    python check_gold.py slides- synth-     (id prefixes; none = all)
Headings marked image_only are skipped (no text layer there)."""

from __future__ import annotations

import json
import re
import sys

import pypdfium2 as pdfium
from common import FILES, GOLD


def _norm(s: str) -> str:
    return re.sub(r"\W+", "", s).lower()


def main(prefixes: list[str]) -> None:
    for g in sorted(GOLD.glob("*.json")):
        if prefixes and not g.stem.startswith(tuple(prefixes)):
            continue
        gold = json.loads(g.read_text())
        try:
            pdf = pdfium.PdfDocument(str(FILES / f"{g.stem}.pdf"))
        except pdfium.PdfiumError as e:
            print(f"{g.stem}: can't open ({e})")
            continue
        texts: dict[int, str] = {}
        bad = []
        for x in gold:
            if x.get("image_only"):
                continue
            p = x["page"]
            if p not in texts:
                texts[p] = _norm(pdf[p - 1].get_textpage().get_text_range()) if p <= len(pdf) else ""
            if _norm(x["title"])[:40] not in texts[p]:
                bad.append(x)
        print(f"{g.stem}: {len(gold)} gold, {len(bad)} not on page" + (f"  e.g. {bad[0]}" if bad else ""))
        pdf.close()


if __name__ == "__main__":
    main(sys.argv[1:])
