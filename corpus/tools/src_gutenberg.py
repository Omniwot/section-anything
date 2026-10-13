"""Long prose from Project Gutenberg (public domain in the US), typeset here
in a different house style per book so heading conventions vary: numbered
chapters, titled chapters, books containing chapters, stories with roman
parts, essays, numbered papers in two columns, run-in subsection heads,
plays with speaker names (bold lines that are not headings), and text with
no headings at all. Gold is exact: the generator records where it put
each heading."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

from common import CACHE, Entry, built, fetch_text, register
from gen import PAGES, Style, render
from reportlab.lib.enums import TA_CENTER, TA_LEFT


class _Blocks(HTMLParser):
    """h1–h4 and p elements, in order, between Gutenberg's START/END markers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[tuple[str, str]] = []
        self.cur: str | None = None
        self.buf: list[str] = []
        self.links = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4", "p"):
            self.cur, self.buf, self.links = tag, [], 0
        elif tag == "a" and self.cur and dict(attrs).get("href", "").startswith("#"):
            self.links += 1
        elif tag == "br" and self.cur:
            self.buf.append(" ")

    def handle_endtag(self, tag):
        if tag == self.cur:
            text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if text and not (self.cur == "p" and self.links):  # contents entries are links
                self.out.append((self.cur, text))
            self.cur = None

    def handle_data(self, data):
        if self.cur:
            self.buf.append(data)


def _book(gid: int) -> list[tuple[str, str]]:
    raw = fetch_text(f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}-images.html", f"gutenberg/pg{gid}.html")
    p = _Blocks()
    p.feed(raw)
    blocks = p.out
    # Drop Gutenberg's licence header and footer.
    start = next((i for i, (_, t) in enumerate(blocks) if "START OF THE PROJECT GUTENBERG" in t.upper()), -1) + 1
    end = next((i for i, (_, t) in enumerate(blocks) if "END OF THE PROJECT GUTENBERG" in t.upper()), len(blocks))
    return [(k, html.unescape(t)) for k, t in blocks[start:end]]


def _levels(blocks: list[tuple[str, str]]) -> list[tuple]:
    tags = sorted({k for k, _ in blocks if k != "p"})
    rank = {t: i + 1 for i, t in enumerate(tags)}
    out: list[tuple] = []
    for k, t in blocks:
        t = re.sub(r"\s*\{\d+\}", "", t)  # Gutenberg's original-page markers
        if k == "p":
            out.append(("p", t))
            continue
        m = re.search(r"\b(?:CHAPTER|BOOK|ACT|STAVE)\b", t)
        if m and m.start() > 0:  # illustration caption merged into the heading
            t = t[m.start():]
        bare = re.sub(r"^[ivxlcdm\d]+\.\s*", "", t, flags=re.IGNORECASE).casefold()
        if any(b[0] == "h" and re.sub(r"^[ivxlcdm\d]+\.\s*", "", b[2], flags=re.IGNORECASE).casefold() == bare
               for b in out[-4:]):
            continue
        out.append(("h", rank[k], t))
    return out


def _cap(blocks: list[tuple], words: int) -> list[tuple]:
    out, n = [], 0
    for b in blocks:
        out.append(b)
        n += len(b[-1].split())
        if n >= words:
            break
    while out and out[-1][0] == "h":
        out.pop()
    return out


def _drop_front(blocks: list[tuple], first: str) -> list[tuple]:
    """Start at the first heading matching `first` (skips title pages and contents)."""
    k = next((i for i, b in enumerate(blocks) if b[0] == "h" and re.search(first, b[2], re.IGNORECASE)), 0)
    return blocks[k:]


def _hamlet(blocks: list[tuple]) -> list[tuple]:
    """Speaker names (short all-caps paragraphs) become bold labels, which a
    heading detector must not take for headings."""
    out = []
    for b in blocks:
        if b[0] == "p" and re.fullmatch(r"[A-Z][A-Z .’']{1,24}\.?", b[1]):
            out.append(("label", b[1]))
        else:
            out.append(b)
    return out


def _darwin(blocks: list[tuple]) -> list[tuple]:
    """Origin's chapters open with a summary of topics; turn those topics into
    run-in heads ("Causes of Variability.— text") on the paragraphs that follow."""
    out, topics, since, lvl = [], [], 0, 2
    for i, b in enumerate(blocks):
        if b[0] == "h":
            topics, since, lvl = [], 0, b[1] + 1
            out.append(b)
            nxt = blocks[i + 1] if i + 1 < len(blocks) else None
            if nxt and nxt[0] == "p":
                topics = [t.strip(" .") for t in re.split(r"\.\s+(?=[A-Z])", nxt[1]) if 3 < len(t.strip()) < 60]
            continue
        since += 1
        if topics and since > 2 and len(b[1]) > 300:
            out.append(("runin", lvl, topics.pop(0), b[1]))
            since = 1
        else:
            out.append(b)
    return out


def _war_and_peace(blocks: list[tuple]) -> list[tuple]:
    return [("h", 1 if b[2].upper().startswith("BOOK") else 2, b[2]) if b[0] == "h" else b for b in blocks]


def _no_headings(blocks: list[tuple]) -> list[tuple]:
    out = []
    for b in blocks:
        if b[0] == "h":
            if out:
                out.append(("break",))
        else:
            out.append(b)
    return out


TIMES = {1: ("Times-Bold", 20, TA_CENTER, False, 30), 2: ("Times-Bold", 15, TA_CENTER, False, 22),
         3: ("Times-BoldItalic", 12, TA_LEFT, False, 12), 4: ("Times-Italic", 11, TA_LEFT, False, 10)}
SMALL_CAPS = {1: ("Times-Roman", 16, TA_CENTER, True, 30), 2: ("Times-Roman", 12, TA_CENTER, True, 18),
              3: ("Times-Italic", 11, TA_CENTER, False, 12), 4: ("Times-Italic", 11, TA_LEFT, False, 8)}
SANS = {1: ("Helvetica-Bold", 18, TA_LEFT, False, 24), 2: ("Helvetica-Bold", 13, TA_LEFT, False, 16),
        3: ("Helvetica-Bold", 11, TA_LEFT, False, 10), 4: ("Helvetica-Oblique", 10, TA_LEFT, False, 8)}
BODY_SIZE_BOLD = {1: ("Times-Bold", 11, TA_LEFT, False, 12), 2: ("Times-Bold", 11, TA_LEFT, False, 10),
                  3: ("Times-Bold", 11, TA_LEFT, False, 8), 4: ("Times-Italic", 11, TA_LEFT, False, 8)}

# (Gutenberg id, short id, title, first heading, word cap, transform, style, why)
BOOKS = [
    (1342, "pride-and-prejudice", "Pride and Prejudice", r"^chapter i\b", 60000, None,
     Style(heading=TIMES, header="PRIDE AND PREJUDICE", first_line_indent=14, para_space=0, new_page_level=2),
     "numbered chapters, chapter per page, running header"),
    (2701, "moby-dick", "Moby-Dick", r"^chapter 1\b", 60000, None,
     Style(heading=SMALL_CAPS, header="{h1}", first_line_indent=12, para_space=0),
     "titled chapters in small caps"),
    (1661, "sherlock-holmes", "The Adventures of Sherlock Holmes", r"scandal in bohemia", 70000, None,
     Style(heading=SANS, page=PAGES["a4"], body_font="Helvetica", body_size=10, leading=13, new_page_level=1),
     "stories with roman-numbered parts, sans serif, A4"),
    (2600, "war-and-peace", "War and Peace (opening)", r"^book one\b", 70000, _war_and_peace,
     Style(heading=TIMES, header="WAR AND PEACE", first_line_indent=14, para_space=0, new_page_level=1),
     "books containing chapters"),
    (2944, "emerson-essays", "Essays, First Series", r"^history$|^i\.? history", 50000, None,
     Style(heading=SMALL_CAPS, align=TA_LEFT, body_size=11.5, leading=15),
     "essays with long paragraphs, ragged right"),
    (1404, "federalist", "The Federalist Papers (1–20)", r"federalist no\. 1\b", 60000, None,
     Style(heading=BODY_SIZE_BOLD, columns=2, body_size=9.5, leading=11.5, margin=18 * 2.83),
     "two columns, body-size bold headings"),
    (1228, "origin-of-species", "On the Origin of Species", r"^chapter i\b", 60000, _darwin,
     Style(heading=TIMES, first_line_indent=12, para_space=0), "run-in subsection heads"),
    (1524, "hamlet", "Hamlet", r"^act i\b", 40000, _hamlet,
     Style(heading=SANS, body_size=10.5, leading=13, align=TA_LEFT, para_space=2),
     "play: acts and scenes, speaker names are bold labels"),
    (1952, "yellow-wallpaper", "The Yellow Wallpaper", r"wallpaper", 20000, _no_headings,
     Style(heading=TIMES, first_line_indent=14, para_space=0), "short story, no headings"),
    (205, "walden-no-headings", "Walden (headings removed)", r"^economy$", 50000, _no_headings,
     Style(heading=TIMES, header="WALDEN", first_line_indent=14, para_space=0),
     "headings replaced by scene breaks"),
]


def build(force: bool = False) -> None:
    for gid, key, title, first, cap, fn, style, why in BOOKS:
        eid = f"prose-{key}"
        if built(eid) and not force:
            continue
        blocks = _cap(_drop_front(_levels(_book(gid)), first), cap)
        if fn:
            blocks = fn(blocks)
        top = min((b[1] for b in blocks if b[0] in ("h", "runin")), default=1)
        blocks = [(b[0], b[1] - top + 1, *b[2:]) if b[0] in ("h", "runin") else b for b in blocks]
        out = CACHE / "gutenberg" / f"{eid}.pdf"
        gold = render(blocks, style, out, title=title)
        register(
            Entry(
                id=eid, category="prose", title=title, source_url=f"https://www.gutenberg.org/ebooks/{gid}",
                license="Public domain (US); Project Gutenberg text, typeset by the corpus generator",
                gold_source="generator", complete=True, variant=why,
                notes="no headings: score by section count only" if not gold else "",
            ),
            out, gold,
        )
