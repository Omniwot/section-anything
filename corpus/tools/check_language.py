"""Flag corpus files whose text is not mostly English: share of common
English function words among the words on a sample of pages. Image-only
files are checked through their `twin`.

    python check_language.py
"""

from __future__ import annotations

import json
import re

import pypdfium2 as pdfium
from common import FILES, MANIFEST

STOP = {"the", "of", "and", "to", "in", "a", "is", "that", "for", "it", "as", "with", "was", "on", "by", "be", "are",
        "this", "from", "or", "which", "an", "at", "not", "have", "has", "were"}


def english_share(path, sample: int = 12) -> float | None:
    try:
        pdf = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError:
        return None
    try:
        n = len(pdf)
        words: list[str] = []
        for i in range(0, n, max(1, n // sample)):
            words += re.findall(r"[^\W\d_]+", pdf[i].get_textpage().get_text_range().lower())
        return sum(w in STOP for w in words) / len(words) if words else None
    finally:
        pdf.close()


def main() -> None:
    docs = json.loads(MANIFEST.read_text())["documents"]
    for d in docs:
        if "file" not in d:
            continue
        src = d.get("extra", {}).get("twin")
        share = english_share(FILES / f"{src}.pdf" if src else FILES.parent / d["file"])
        flag = "" if share is None or share >= 0.12 else "  <-- not English?"
        print(f"{d['id']:<44} {'  — ' if share is None else f'{share:.2f}'}{flag}")


if __name__ == "__main__":
    main()
