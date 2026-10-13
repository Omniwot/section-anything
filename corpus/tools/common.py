"""Shared helpers for building the test corpus.

Every document gets a PDF in `corpus/files/` (git-ignored), a gold file in
`corpus/gold/` and an entry in `corpus/manifest.json` recording where it came
from, its licence and how its gold was made. Gold is never hand-written here:
it comes from source markup (LaTeX, JATS, legislation XML, wiki sections), a
published benchmark, bookmarks removed from the test copy, or a generator.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "files"
CACHE = FILES / "cache"
GOLD = ROOT / "gold"
MANIFEST = ROOT / "manifest.json"
BACKEND = ROOT.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.sectioning.extract import Extraction, extract, read_outline
from app.sectioning.markers import canon
from app.sectioning.structure import detect_toc
from rapidfuzz import fuzz

UA = "section-anything-corpus/0.1 (test corpus builder)"
for d in (FILES, CACHE, GOLD):
    d.mkdir(parents=True, exist_ok=True)


def _looks_right(path: Path) -> bool:
    """A file cached as .pdf must start like a PDF (servers return HTML error pages with 200/504)."""
    if path.suffix.lower() != ".pdf" and not path.name.endswith(".pdf.part"):
        return True
    with path.open("rb") as f:
        return b"%PDF" in f.read(1024)


def fetch(url: str, name: str, *, retries: int = 3, timeout: int = 120) -> Path:
    """Download once into the cache; later builds reuse the file."""
    path = CACHE / name
    if path.exists() and path.stat().st_size > 0 and _looks_right(path):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    polite = 3.5 if "arxiv.org" in url else 1.0  # arXiv asks for ≥3 s between requests
    err: Exception | None = None
    for attempt in range(retries + 2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            part = path.with_suffix(path.suffix + ".part")
            with urllib.request.urlopen(req, timeout=timeout) as r, part.open("wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            if not _looks_right(part):
                part.unlink()
                raise RuntimeError("got an HTML or error page instead of a PDF")
            part.replace(path)
            time.sleep(polite)
            return path
        except urllib.error.HTTPError as e:
            err = e
            if e.code == 404:
                break
            time.sleep((20 if e.code in (429, 503) else 3) * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"download failed: {url}: {err}")


def fetch_text(url: str, name: str) -> str:
    return fetch(url, name).read_text(encoding="utf-8", errors="replace")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def page_count(path: Path) -> int:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError:  # encrypted or corrupt upload-check files
        return 0
    try:
        return len(pdf)
    finally:
        pdf.close()


def rasterise(src: Path, dst: Path, pages: set[int] | None = None, *, dpi: int = 150, skew: float = 0.0,
              noise: float = 0.0, seed: int = 0) -> None:
    """Replace the given 1-based pages (all when None) with a JPEG of the page,
    so they have no text layer. `skew` rotates by degrees; `noise` (0–1) adds
    speckle and lowers contrast like a photocopy."""
    import io
    import random

    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter

    rnd = random.Random(seed)
    pdf = pdfium.PdfDocument(str(src))
    try:
        for i in range(len(pdf)):
            if pages is not None and i + 1 not in pages:
                continue
            page = pdf[i]
            w, h = page.get_size()
            img = page.render(scale=dpi / 72, grayscale=True).to_pil().convert("L")
            if skew:
                img = img.rotate(skew * (1 if rnd.random() < 0.5 else -1), expand=False, fillcolor=255,
                                 resample=Image.BICUBIC)
            if noise:
                px = img.load()
                for _ in range(int(img.width * img.height * noise * 0.004)):
                    x, y = rnd.randrange(img.width), rnd.randrange(img.height)
                    px[x, y] = 0 if rnd.random() < 0.6 else 255
                img = img.filter(ImageFilter.GaussianBlur(noise * 0.8)).point(lambda v: 40 + v * 0.75)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=70)
            buf.seek(0)
            pdf.del_page(i)
            new = pdf.new_page(w, h, index=i)
            obj = pdfium.PdfImage.new(pdf)
            obj.load_jpeg(buf, inline=True)
            obj.set_matrix(pdfium.PdfMatrix().scale(w, h))
            new.insert_obj(obj)
            new.gen_content()
        pdf.save(str(dst))
    finally:
        pdf.close()


def copy_pages(src: Path, dst: Path, pages: list[int] | None = None) -> None:
    """Write the given 1-based pages (all when None) to a new PDF. The copy
    has no bookmarks, so its gold can come from the source's bookmarks."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(src))
    out = pdfium.PdfDocument.new()
    try:
        idx = [p - 1 for p in pages] if pages else list(range(len(pdf)))
        out.import_pages(pdf, idx)
        out.save(str(dst))
    finally:
        out.close()
        pdf.close()


def outline_gold(src: Path, pages: list[int] | None = None, max_level: int | None = None) -> list[dict]:
    """Gold from the source PDF's bookmarks, renumbered to an excerpt's pages."""
    keep = {p: i + 1 for i, p in enumerate(pages)} if pages else None
    out = []
    for it in read_outline(src):
        if max_level and it.level > max_level:
            continue
        if keep is not None:
            if it.page not in keep:
                continue
            page = keep[it.page]
        else:
            page = it.page
        out.append({"level": it.level, "title": it.title.strip(), "page": page})
    return out


def extraction(path: Path) -> Extraction:
    """Our extraction of a corpus file, cached by hash for anchoring and eval."""
    cached = CACHE / f"{sha256(path)[:16]}.extraction.json"
    if cached.exists():
        return Extraction.load(cached)
    ext = extract(path)
    ext.save(cached)
    return ext


def _key(s: str) -> str:
    return canon(s).replace(" ", "")


def anchor(
    ext: Extraction, items: list[tuple[int, str]], *, pdf_titles: bool = False, max_gap_lines: int | None = None,
    run_in: bool = False, start_after: str | None = None, start_line: int | None = None,
) -> tuple[list[dict], list[str]]:
    """Find the page of each known heading, in document order.

    A heading matches a whole line (or up to three consecutive lines joined)
    outside the document's own table of contents, ignoring any leading
    numbering on either side. Search continues after the previous match, so
    headings must be given in reading order. Headings that can't be found are
    returned separately, never guessed. With `pdf_titles`, gold titles are
    the matched lines as printed ("IV. RESULTS"), which keeps the PDF's own
    numbering style. With `run_in`, a heading may also open a line and be
    followed by body text after a full stop, colon or dash; such gold entries
    are marked `run_in`. `start_after` skips everything up to the first line
    matching it (an act's enacting words, after its printed contents);
    `start_line` sets that position directly.

    A heading whose match lies beyond the next heading's match is treated as
    missing, so one false match far ahead can't swallow the rest.
    """
    lines = ext.lines
    toc = detect_toc(ext).lines
    keys = [_key(ENUM.sub("", ln.text)) for ln in lines]

    def find(t: str, pos: int) -> tuple[int | None, int | None, str | None]:
        end = len(lines) if max_gap_lines is None else min(len(lines), pos + max_gap_lines)
        for i in range(pos, end):
            if i in toc or not keys[i] or not t.startswith(keys[i][: max(1, min(len(keys[i]), 4))]):
                continue
            joined = ""
            for j in range(i, min(i + 3, len(lines))):
                joined += keys[j] if j == i else _key(lines[j].text)
                if joined == t or (len(t) >= 10 and abs(len(joined) - len(t)) <= 0.15 * len(t) and fuzz.ratio(joined, t) >= 92):
                    return i, j, None
                if len(joined) >= len(t) or not t.startswith(joined[: len(joined) - 2]):
                    break
            if run_in and len(t) >= 4 and keys[i].startswith(t):
                head = _run_in_prefix(lines[i].text, t)
                if head:
                    return i, i, head
        return None, None, None

    targets = [_key(ENUM.sub("", title)) or _key(title) for _, title in items]
    gold, missing = [], []
    pos = start_line or 0
    if start_after:
        pos = next((i for i, ln in enumerate(lines) if re.search(start_after, ln.text, re.IGNORECASE)), pos)
    for k, (level, title) in enumerate(items):
        t = targets[k]
        if not t:
            continue
        hit, span, runin = find(t, pos)
        if hit is not None and k + 1 < len(items) and targets[k + 1] and targets[k + 1] != t:
            nxt, _, _ = find(targets[k + 1], pos)
            if nxt is not None and nxt < hit:
                hit = None
        if hit is None:
            missing.append(title)
            continue
        if runin:
            gold.append({"level": level, "title": runin if pdf_titles else title, "page": lines[hit].page, "run_in": True})
            pos = hit + 1
            continue
        shown = " ".join(lines[k].text.strip() for k in range(hit, span + 1)) if pdf_titles else title
        gold.append({"level": level, "title": shown, "page": lines[hit].page})
        pos = span + 1
    return gold, missing


def _run_in_prefix(text: str, t: str) -> str | None:
    """The heading part of a run-in line ("2.1. Preliminaries. The …" →
    "2.1. Preliminaries") when it equals `t` once numbering is ignored."""
    for m in re.finditer(r"[.:—–](?=\s+\S|[—–(])", text):
        head = text[: m.start()].strip()
        k = _key(ENUM.sub("", head + " "))
        if k == t:
            return head
        if len(k) > len(t):
            return None
    return None


ENUM = re.compile(r"^\s*(?:(?:chapter|part|section|cap[íi]tulo|chapitre|kapitel|teil|parte|article|art\.)\s+)?\(?(?:[ivxlcdm]+|\d+(?:\.\d+)*|[a-z])[.)]?\s+", re.IGNORECASE)


def text_layer_ok(pdf_path: Path, sample: int = 20) -> bool:
    """False when most sampled pages decode to mostly non-ASCII-letter junk
    (a broken font encoding), so text checks can't be trusted."""
    texts = []
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        step = max(1, len(pdf) // sample)
        texts = [pdf[i].get_textpage().get_text_range() for i in range(0, len(pdf), step)]
    finally:
        pdf.close()
    letters = sum(c.isalpha() for t in texts for c in t)
    ascii_letters = sum(c.isascii() and c.isalpha() for t in texts for c in t)
    return letters > 0 and ascii_letters / letters > 0.9


def _page_texts(pdf_path: Path) -> list[str]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return [_key(pdf[i].get_textpage().get_text_range()) for i in range(len(pdf))]
    finally:
        pdf.close()


def locate_pages(pdf_path: Path, items: list[tuple[int, str]]) -> tuple[list[dict], list[str]]:
    """Coarser fallback to `anchor`: the first page, at or after the previous
    heading's page, whose pdfium text contains the heading. Used when our own
    extractor can't read a script (right-to-left, complex shaping)."""
    import pypdfium2 as pdfium

    texts = _page_texts(pdf_path)
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        words = [{w for w in canon(pdf[i].get_textpage().get_text_range()).split()} for i in range(len(pdf))]
    finally:
        pdf.close()

    def word_hit(title: str, p: int) -> bool:
        # Right-to-left text is often stored in visual order, so a word may be reversed.
        ws = canon(title).split()
        return bool(ws) and sum(w in words[p - 1] or w[::-1] in words[p - 1] for w in ws) >= 0.8 * len(ws)

    gold, missing, page = [], [], 1
    for level, title in items:
        k = _key(title)[:30]
        hit = next((p for p in range(page, len(texts) + 1) if k and k in texts[p - 1]), None)
        if hit is None:
            hit = next((p for p in range(page, len(texts) + 1) if word_hit(title, p)), None)
        if hit is None:
            missing.append(title)
            continue
        gold.append({"level": level, "title": title, "page": hit})
        page = hit
    return gold, missing


def verified(pdf_path: Path, gold: list[dict], window: int = 40) -> tuple[list[dict], int, str]:
    """Check each gold heading's page against the PDF's text and fix drift.

    Gold made against another edition of a PDF is shifted by a varying
    offset. A heading whose text is within ±1 page keeps its page; otherwise
    it moves to the nearest page (after applying the last seen offset) that
    contains its text, skipping pages that list many headings (contents
    pages). Headings not found within `window` pages are dropped.
    Returns (gold, dropped, note).
    """
    texts = _page_texts(pdf_path)
    keys = [_key(g["title"])[:30] for g in gold]
    bare = [_key(ENUM.sub("", g["title"]))[:30] for g in gold]  # some PDFs draw the number apart from the text
    hits = [
        [p for p in range(1, len(texts) + 1) if (k and k in texts[p - 1]) or (len(b) >= 8 and b in texts[p - 1])]
        for k, b in zip(keys, bare, strict=True)
    ]
    per_page: dict[int, int] = {}
    for k, h in zip(keys, hits, strict=True):
        if len(k) < 15 or len(h) > 5:  # only distinctive titles reveal a contents page
            continue
        for p in h:
            per_page[p] = per_page.get(p, 0) + 1
    listing = {p for p, n in per_page.items() if n >= 6}
    out, dropped, moved, offset = [], 0, 0, 0
    for g, h in zip(gold, hits, strict=True):
        cands = [p for p in h if p not in listing]
        if any(abs(p - g["page"]) <= 1 for p in cands):
            page = min((p for p in cands if abs(p - g["page"]) <= 1), key=lambda p: abs(p - g["page"]))
        elif cands:
            page = min(cands, key=lambda p: abs(p - (g["page"] + offset)))
            if abs(page - (g["page"] + offset)) > window:
                dropped += 1
                continue
            moved += 1
        else:
            dropped += 1
            continue
        offset = page - g["page"]
        out.append({**g, "page": page})
    note = f"{moved} gold pages corrected for edition drift" if moved else ""
    return out, dropped, note


@dataclass
class Entry:
    id: str
    category: str
    title: str
    source_url: str
    license: str
    gold_source: str  # latex | jats | legislation-xml | wiki-api | hips | bookmarks | gutenberg | generator
    complete: bool = True  # False when gold covers only some heading levels (recall is meaningful, precision isn't)
    variant: str = ""
    notes: str = ""
    file: str = ""
    gold: str = ""
    sha256: str = ""
    pages: int = 0
    gold_headings: int = 0
    unanchored: int = 0
    extra: dict = field(default_factory=dict)


def register(entry: Entry, pdf: Path, gold: list[dict], unanchored: int = 0) -> Entry:
    """Write the gold file and upsert the manifest entry by id."""
    dst = FILES / f"{entry.id}.pdf"
    if pdf.resolve() != dst.resolve():
        dst.write_bytes(pdf.read_bytes())
    gpath = GOLD / f"{entry.id}.json"
    gpath.write_text(json.dumps(gold, indent=1, ensure_ascii=False) + "\n")
    entry.file = f"files/{dst.name}"
    entry.gold = f"gold/{gpath.name}"
    entry.sha256 = sha256(dst)
    entry.pages = page_count(dst)
    entry.gold_headings = len(gold)
    entry.unanchored = unanchored
    data = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"documents": []}
    docs = [d for d in data["documents"] if d.get("id") != entry.id]
    docs.append({k: v for k, v in asdict(entry).items() if v not in ("", {}, None)})
    data["documents"] = sorted(docs, key=lambda d: (d.get("category", ""), d.get("id", "")))
    MANIFEST.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"  ✓ {entry.id}: {entry.pages} pp, {len(gold)} gold" + (f", {unanchored} unanchored" if unanchored else ""))
    return entry


def from_bookmarks(
    entry: Entry, src: Path, *, max_pages: int = 300, match: str | None = None, keep: bool = False, min_items: int = 5
) -> Entry | None:
    """Make a test copy of a bookmarked PDF with gold from its bookmarks.

    Long PDFs are cut at a top-level bookmark boundary (or to the bookmark
    whose title matches `match`, with its children). Bookmarks often stop
    above the deepest heading level, so gold is marked incomplete unless the
    caller knows better. The copy has no bookmarks unless `keep`.
    """
    outline = read_outline(src)
    n = page_count(src)
    first, stop, lvl = 1, n + 1, 0
    if match:
        k = next((i for i, o in enumerate(outline) if re.search(match, o.title, re.IGNORECASE)), None)
        if k is None:
            print(f"  ✗ {entry.id}: no bookmark matching {match!r}")
            return None
        lvl = outline[k].level
        first = outline[k].page
        stop = next((o.page for o in outline[k + 1 :] if o.level <= lvl and o.page > first), n + 1)
    if stop - first > max_pages:
        # Cut at the shallowest bookmark boundary that keeps at least half the budget.
        limit = first + max_pages
        for depth in (lvl + 1, lvl + 2, lvl + 3):
            cuts = [o.page for o in outline if o.level == depth and first + max_pages // 2 <= o.page <= limit]
            if cuts:
                stop = max(cuts)
                break
        else:
            stop = limit
    pages = list(range(first, stop))
    if keep and len(pages) == n:
        out = src
    else:
        out = CACHE / "excerpts" / f"{entry.id}.pdf"
        out.parent.mkdir(exist_ok=True)
        copy_pages(src, out, pages)
    gold = outline_gold(src, pages)
    if len(gold) < min_items:
        print(f"  ✗ {entry.id}: only {len(gold)} bookmarks in range")
        return None
    gold, dropped, note = verified(out, gold)
    if dropped > len(gold):
        print(f"  ✗ {entry.id}: {dropped} of {dropped + len(gold)} bookmarks not found in the text (junk outline)")
        return None
    entry.gold_source = entry.gold_source or "bookmarks"
    entry.variant = entry.variant or ("bookmarks" if keep else "bookmarks-removed")
    entry.notes = "; ".join(x for x in (entry.notes, note) if x)
    entry.extra = {**entry.extra, "source_pages": [pages[0], pages[-1]], "source_total_pages": n}
    return register(entry, out, gold, dropped)


def unregister(entry_id: str) -> None:
    """Remove an entry from the manifest with its gold and file."""
    data = json.loads(MANIFEST.read_text())
    data["documents"] = [d for d in data["documents"] if d.get("id") != entry_id]
    MANIFEST.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    for p in (GOLD / f"{entry_id}.json", FILES / f"{entry_id}.pdf"):
        p.unlink(missing_ok=True)


def built(entry_id: str) -> bool:
    if not MANIFEST.exists():
        return False
    return any(d.get("id") == entry_id for d in json.loads(MANIFEST.read_text())["documents"])
