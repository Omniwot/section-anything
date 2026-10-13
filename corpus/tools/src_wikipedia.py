"""Wikipedia articles as rendered by Wikimedia's PDF service (CC BY-SA 4.0).
Gold headings come from the parse API's section list; pages are found by
locating each heading line in the PDF."""

from __future__ import annotations

import html
import json
import re
import urllib.parse

from common import (
    Entry,
    anchor,
    built,
    extraction,
    fetch,
    fetch_text,
    locate_pages,
    register,
)

# (lang, title, why it's in the set)
ARTICLES = [
    ("en", "Photosynthesis", "science, deep sections, figures"),
    ("en", "World War I", "long history article, many levels"),
    ("en", "Ada Lovelace", "biography, short sections"),
    ("en", "List of largest cities", "mostly tables"),
    ("de", "Photosynthese", "German"),
    ("fr", "Révolution française", "French, long"),
    ("es", "Sistema solar", "Spanish"),
    ("ja", "光合成", "Japanese, CJK"),
    ("ar", "التمثيل الضوئي", "Arabic, right-to-left"),
    ("hi", "प्रकाश संश्लेषण", "Hindi, Devanagari"),
]


def _sections(lang: str, title: str) -> list[tuple[int, str]]:
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "sections", "format": "json", "redirects": 1})
    raw = fetch_text(f"https://{lang}.wikipedia.org/w/api.php?{q}", f"wiki/{lang}-{_slug(title)}.sections.json")
    out = []
    for s in json.loads(raw)["parse"]["sections"]:
        text = html.unescape(re.sub(r"<[^>]+>", "", s["line"])).strip()
        if text:
            out.append((int(s["toclevel"]) + 1, text))
    return out


def _slug(title: str) -> str:
    return re.sub(r"\W+", "_", title, flags=re.UNICODE).strip("_")[:60]


def build(force: bool = False) -> None:
    for i, (lang, title, why) in enumerate(ARTICLES, 1):
        eid = f"wiki-{i:02d}-{lang}"
        if built(eid) and not force:
            continue
        enc = urllib.parse.quote(title.replace(" ", "_"), safe="")
        pdf = fetch(f"https://{lang}.wikipedia.org/api/rest_v1/page/pdf/{enc}", f"wiki/{lang}-{_slug(title)}.pdf")
        items = [(1, title)] + _sections(lang, title)
        gold, missing = anchor(extraction(pdf), items)
        how = ""
        if len(missing) > 0.2 * len(items):
            alt, alt_missing = locate_pages(pdf, items)
            if len(alt_missing) < len(missing):
                gold, missing = alt, alt_missing
                how = "pages via pdfium text (our extractor misreads this script); "
        register(
            Entry(
                id=eid, category="wikipedia", title=f"{title} ({lang})",
                source_url=f"https://{lang}.wikipedia.org/wiki/{enc}", license="CC BY-SA 4.0",
                gold_source="wiki-api", variant=why,
                notes=how + (f"unanchored: {missing[:5]}" if missing else ""),
            ),
            pdf, gold, len(missing),
        )
