"""HiPS benchmark (github.com/anybass/HiPS): open-access law books with
manually verified headings (level, title, page). Data is CC BY-NC 4.0; the
books themselves are mostly CC BY-NC-ND. Used locally only, never shipped."""

from __future__ import annotations

import csv
import io

from common import (
    CACHE,
    Entry,
    built,
    copy_pages,
    fetch,
    fetch_text,
    register,
    text_layer_ok,
    verified,
)

RAW = "https://raw.githubusercontent.com/anybass/HiPS/main/data"

# (slug, keep_bookmarks). Picked for spread of depth (2–7) and length (32–494 pp).
BOOKS = [
    ("access-to-justice-and-legal-empowerment-making-the-poor-central-in-legal-development-co-operati", False),
    ("aegis-or-achilles-heel-the-dilemma-of-homology-in-biopatents-in-the-wake-of-novozymes", False),
    ("boats-to-burn-bajo-fishing-activity-in-the-australian-fishing-zone", False),
    ("revisiting-chinas-competition-law-and-its-interaction-with-intellectual-property-rights", True),
    ("a-bird-that-flies-with-two-wings-kastom-and-state-justice-systems-in-vanuatu", False),
    ("agriculture-and-food-security-in-china-what-effect-wto-accession-and-regional-trade-arrangements", False),
    ("analogy-and-exemplary-reasoning-in-legal-discourse", False),
    ("border-flows-a-century-of-the-canadian-american-water-relationship", False),
    ("consumer-data-protection-in-brazil-china-and-germany-a-comparative-study", False),
    ("introduction-to-swiss-l", True),
    ("necessity-or-nuisance-recourse-to-human-rights-in-substantive-international-criminal-l", False),
    ("employee-participation-and-collective-bargaining-in-europe-and-chi", False),
]


def _licences() -> dict[str, tuple[str, str]]:
    rows = csv.DictReader(io.StringIO(fetch_text(f"{RAW}/data_sources.csv", "hips/data_sources.csv")))
    return {r["Title"].strip().lower(): (r["License"].strip(), r["URL"].strip()) for r in rows}


def _match(slug: str, lic: dict[str, tuple[str, str]]) -> tuple[str, str, str]:
    import re

    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    for title, (licence, url) in lic.items():
        if norm(title).startswith(slug[:60]) or slug.startswith(norm(title)[:60]):
            return title, licence, url
    return slug, "CC BY-NC-ND (per HiPS data_sources.csv)", ""


def build(force: bool = False) -> None:
    lic = _licences()
    for i, (slug, keep) in enumerate(BOOKS, 1):
        eid = f"hips-{i:02d}"
        if built(eid) and not force:
            continue
        pdf = fetch(f"{RAW}/PDFs/{slug}.pdf", f"hips/{slug}.pdf")
        rows = csv.reader(io.StringIO(fetch_text(f"{RAW}/GT_TOCs/{slug}.toc", f"hips/{slug}.toc")))
        gold = []
        for r in rows:
            if len(r) < 3 or not r[0].strip().isdigit() or not r[-1].strip().isdigit():
                continue
            gold.append({"level": int(r[0]), "title": ",".join(r[1:-1]).strip(), "page": int(r[-1])})
        title, licence, url = _match(slug, lic)
        out = pdf
        if not keep:
            out = CACHE / f"hips/{eid}.nobookmarks.pdf"
            copy_pages(pdf, out)
        if text_layer_ok(out):
            gold, unanchored, note = verified(out, gold)
            variant = "bookmarks" if keep else "bookmarks-removed"
        else:
            unanchored, note = 0, "broken font encoding: text layer is unreadable; HiPS pages kept unverified"
            variant = "broken-text-layer"
        register(
            Entry(
                id=eid, category="law-books", title=title.title(), source_url=url or f"{RAW}/PDFs/{slug}.pdf",
                license=f"{licence}; HiPS annotations CC BY-NC 4.0", gold_source="hips",
                variant=variant, notes=note,
                extra={"max_level": max(g["level"] for g in gold)},
            ),
            out, gold, unanchored,
        )
