"""Image-only copies of corpus documents that already have gold, so each
scanned file is scored against the same headings as its born-digital twin.
Variants cover resolution, skew, photocopy noise, a half-scanned file, and
non-Latin scripts. Needs OCR to section; without it a sectioner should
say so rather than return nothing silently. (hips-10 is the real-world
case of a broken text layer.)"""

from __future__ import annotations

import json

from common import (
    CACHE,
    FILES,
    GOLD,
    Entry,
    built,
    copy_pages,
    page_count,
    rasterise,
    register,
)

# (source id, max pages, dpi, skew degrees, noise 0-1, fraction of pages rasterised, why)
SCANS = [
    ("wiki-01-en", 40, 200, 0.0, 0.0, 1.0, "clean 200 dpi"),
    ("arxiv-02", 40, 150, 0.0, 0.0, 1.0, "two-column paper, 150 dpi"),
    ("openstax-06", 40, 150, 0.7, 0.0, 1.0, "textbook, slight skew"),
    ("prose-pride-and-prejudice", 40, 100, 0.0, 0.35, 1.0, "low resolution photocopy"),
    ("law-uk-climate-change-act-2008", 40, 200, 0.0, 0.25, 1.0, "act with noise"),
    ("manual-bash", 40, 150, 1.5, 0.0, 1.0, "manual, visible skew"),
    ("prose-hamlet", 40, 120, 0.4, 0.15, 1.0, "play, mild skew and noise"),
    ("synth-numbering-only", 40, 200, 0.0, 0.5, 1.0, "numbering-only headings, heavy noise"),
    ("wiki-05-de", 40, 150, 0.0, 0.0, 0.5, "half the pages scanned, half born-digital"),
    ("wiki-08-ja", 40, 200, 0.0, 0.0, 1.0, "Japanese script"),
]


def build(force: bool = False) -> None:
    d = CACHE / "scanned"
    d.mkdir(parents=True, exist_ok=True)
    manifest = {x["id"]: x for x in json.loads((FILES.parent / "manifest.json").read_text())["documents"]}
    for i, (src_id, cap, dpi, skew, noise, frac, why) in enumerate(SCANS, 1):
        eid = f"scan-{i:02d}-{src_id}"
        if built(eid) and not force:
            continue
        src = FILES / f"{src_id}.pdf"
        n = min(page_count(src), cap)
        excerpt = d / f"{eid}.text.pdf"
        copy_pages(src, excerpt, list(range(1, n + 1)))
        pages = None if frac >= 1 else {p for p in range(1, n + 1) if p % 2 == 0}
        out = d / f"{eid}.pdf"
        rasterise(excerpt, out, pages, dpi=dpi, skew=skew, noise=noise, seed=i)
        gold = [g for g in json.loads((GOLD / f"{src_id}.json").read_text()) if g["page"] <= n]
        gold = [{**g, "image_only": True} if pages is None or g["page"] in pages else g for g in gold]
        base = manifest[src_id]
        register(
            Entry(id=eid, category="scanned", title=f"{base['title']} (scanned)", source_url=base["source_url"],
                  license=base["license"], gold_source=base["gold_source"], complete=base.get("complete", True),
                  variant=why, notes=f"rasterised from {src_id}, first {n} pages",
                  extra={"twin": src_id, "dpi": dpi, "skew": skew, "noise": noise}),
            out, gold,
        )
