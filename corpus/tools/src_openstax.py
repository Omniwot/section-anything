"""OpenStax textbook chapters (CC BY-NC-SA 4.0, and the book pages forbid ingestion into
LLMs or generative-AI offerings without OpenStax's written permission; checked 19 Oct 2026), cut from the full-book PDFs so the
excerpt has no bookmarks. Gold: chapter and section titles from the book's
bookmarks, subsection titles (h3/h4) from the matching openstax.org web
pages; pages are found by locating each heading in the excerpt. Follows the
convention of the hand-checked textbook-ch10 gold (no "Chapter Outline",
"Introduction" or "Learning Objectives")."""

from __future__ import annotations

import html
import re
import unicodedata
import urllib.parse
from pathlib import Path

from common import (
    CACHE,
    Entry,
    anchor,
    built,
    copy_pages,
    extraction,
    fetch,
    fetch_text,
    read_outline,
    register,
)

ASSETS = "https://assets.openstax.org/oscms-prodcms/media/documents/"
LOCAL_BIOLOGY = Path(__file__).resolve().parents[3] / ".tmp/sectioner-eval/biology-2e-full.pdf"

# (book slug, PDF file name, chapter number, why)
BOOKS = [
    ("biology-2e", None, 6, "science, figures and boxes"),
    ("calculus-volume-1", "calculus-volume-1_-_WEB.pdf", 3, "math: theorems, examples, exercises"),
    ("us-history", "US_History_-_WEB.pdf", 8, "narrative history, primary-source boxes"),
    ("introduction-python-programming", "Introduction_to_Python_Programming-WEB.pdf", 5, "code listings"),
    ("chemistry-2e", "chemistry-2e_-_WEB.pdf", 4, "formulas, worked examples"),
    ("psychology-2e", "Psychology2e_WEB.pdf", 6, "social science"),
    ("principles-economics-3e", "principles-economics-3e_-_WEB.pdf", 3, "graphs and tables"),
    ("introduction-philosophy", "Introduction_to_Philosophy-WEB.pdf", 4, "humanities prose"),
    ("writing-guide", "WritingGuide-WEB.pdf", 2, "writing guide, many short sections"),
    ("astronomy-2e", "astronomy-2e_-_WEB.pdf", 6, "astronomy: instruments, figures, worked examples"),
]
SKIP = {"chapter outline", "introduction", "learning objectives"}


def _slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _web_subheadings(book: str, chapter: int, title: str) -> list[tuple[int, str]]:
    """Section headings of one web page. Only titles that open a
    <section data-depth=N> count; feature boxes (Example, Definition, Media,
    Checkpoint …) use the same heading tags but sit in divs."""
    page = _slugify(title) if re.match(r"\d", title) else f"{chapter}-{_slugify(title)}"
    url = f"https://openstax.org/books/{urllib.parse.quote(book)}/pages/{page}"
    try:
        h = fetch_text(url, f"openstax/{_slugify(book)}/{page}.html")
    except RuntimeError:
        return []
    h = h.split("OpenStax’s mission", 1)[0]
    out = []
    for depth, inner in re.findall(
        r'<section[^>]*data-depth="(\d)"[^>]*>\s*<h[2-6][^>]*data-type="title"[^>]*>(.*?)</h[2-6]>', h, flags=re.DOTALL
    ):
        text = html.unescape(re.sub(r"<[^>]+>", " ", inner))
        text = re.sub(r"\s+", " ", text).strip()
        if text and text.lower() not in SKIP:
            out.append((int(depth) + 2, text))
    return out


def build(force: bool = False) -> None:
    for i, (book, fname, ch, why) in enumerate(BOOKS, 1):
        eid = f"openstax-{i:02d}"
        if built(eid) and not force:
            continue
        full = LOCAL_BIOLOGY if fname is None else fetch(ASSETS + fname, f"openstax/{fname}", timeout=900)
        outline = read_outline(full)
        tops = [o for o in outline if o.level == 1]
        start = next((k for k, o in enumerate(tops) if re.search(rf"\b{ch}\b", o.title)), None)
        if start is None:
            print(f"  ✗ {book}: chapter {ch} not in bookmarks")
            continue
        first = tops[start].page
        last = (tops[start + 1].page - 1) if start + 1 < len(tops) else first + 40
        pages = list(range(first, last + 1))
        items: list[tuple[int, str]] = [(1, tops[start].title)]
        web = 0
        for o in outline:
            if o.level == 2 and first <= o.page <= last and o.title.strip().lower() not in SKIP:
                items.append((2, o.title.strip()))
                subs = _web_subheadings(book, ch, o.title.strip())
                web += len(subs)
                items.extend(subs)
        out = CACHE / f"openstax/{eid}.pdf"
        copy_pages(full, out, pages)
        gold, missing = anchor(extraction(out), items)
        register(
            Entry(
                id=eid, category="textbooks", title=f"OpenStax {book}, chapter {ch}",
                source_url=f"https://openstax.org/details/books/{book}", license="CC BY-NC-SA 4.0; no LLM or generative-AI ingestion without OpenStax's written permission",
                gold_source="bookmarks+web", complete=web > 0, variant=why,
                notes=("" if web else "web pages not found: bookmarks only; ")
                + (f"unanchored: {missing[:5]}" if missing else ""),
                extra={"source_pages": [first, last]},
            ),
            out, gold, len(missing),
        )
