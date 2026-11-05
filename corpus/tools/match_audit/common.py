"""Zero-miss track A (F055/F056): shared helpers for the miss audit, the candidate ceiling and gold v2.
Track M (F063) copy: writes to .tmp/match-fail and reads answer keys v1, v2 or v2.1 (gold_v21.py).

Run with the code under test on PYTHONPATH (worktree .tmp/sa-miss, rc/0.1.7 2066ab2) and the sa-017
venv. Saved extractions only (extractor v6): a document's no-bookmark extraction with its outline
cleared, or with the outline read from the bookmarked PDF (pypdfium2; the text is the same PDF's).
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from rapidfuzz import fuzz, process

from section_anything import Settings
from section_anything.docling_input import hints_of
from section_anything.evaluate import THRESHOLD
from section_anything.extract import Extraction, read_outline
from section_anything.llm import Usage
from section_anything.markers import canon
from section_anything.outline_check import demote_unlisted_headings
from section_anything.pipeline import Locator, mark_doc_title, resolve
from section_anything.strategies import rules as R
from section_anything.strategies.base import Context
from section_anything.structure import (furniture_of, listing_of, split_number,
                                        toc_of)

ROOT = Path("/Users/harshal/Desktop/omni/hustles")
T = ROOT / ".tmp"
MG, EXT, AV = T / "multigenre", T / "multigenre-ext", T / "adapter-validate"
CORPUS = T / "sa-miss" / "corpus"
OUT = T / "match-fail"
AUDIT_A = T / "miss-audit"  # track A's rows (F056)
CORPUS_V21 = T / "sa-match" / "corpus" / "gold-v2.1"  # the corpus sample's v2.1 keys (this branch)
CACHES = [T / "miss-audit/extcache/v6", AV / "extcache/v6", T / "structure-eval/extcache/v6", T / "adapter-eval/extcache/v6",
          T / "f054/extcache/v6", T / "f046/extcache/v6"]
DOCLING = [T / "docling-out-f042", T / "docling-out"]


# ── documents ──
def registry() -> list[dict]:
    docs = []

    def add(d: dict, root: Path, set_: str, split: str, genre: str, pdf: Path, nobm: Path | None) -> None:
        docs.append({"id": d["id"], "genre": genre, "set": set_, "split": split, "gold": str(root / d["gold"]),
                     "pdf": str(pdf), "nobm": str(nobm) if nobm else None, "complete": d.get("complete", True),
                     "pages": d.get("pages")})

    for d in json.loads((MG / "split.json").read_text())["documents"]:
        add(d, MG, "f042", d["split"], d["category"], MG / d["file"], MG / "files" / f"{d['id']}--nobm.pdf")
    for d in json.loads((MG / "split-recovered.json").read_text())["documents"]:
        add(d, MG, "recovered", d["split"], d["category"], MG / d["file"], MG / "files" / f"{d['id']}--nobm.pdf")
    for d in json.loads((EXT / "split-ext.json").read_text())["documents"]:
        add(d, EXT, "ext", "test", d["category"], EXT / d["file"], EXT / "files" / f"{d['id']}--nobm.pdf")
    for d in json.loads((AV / "split.json").read_text())["documents"]:
        add(d, AV, "new", d["split"], d["category"], AV / d["file"], AV / "files" / f"{d['id']}--nobm.pdf")
    for d in json.loads((CORPUS / "results/sample-3pc.json").read_text())["documents"]:
        d = {**d, "gold": f"gold/{d['id']}.json"}
        pdf = CORPUS / "files" / f"{d['id']}.pdf"
        if not pdf.exists():  # large corpus PDFs are kept out of git; the main checkout has them
            pdf = ROOT / "section-anything/corpus/files" / f"{d['id']}.pdf"
        add(d, CORPUS, "corpus", "dev", f"corpus-{d['category']}", pdf, None)
    return docs


def gold_of(doc: dict, version: str = "v1") -> list[dict]:
    p = Path(doc["gold"])
    if version == "v2":
        p = p.parent.parent / "gold-v2" / p.name
    elif version == "v2.1":
        p = CORPUS_V21 / p.name if doc["set"] == "corpus" else p.parent.parent / "gold-v2.1" / p.name
    return json.loads(p.read_text())


def cache_path(doc: dict) -> Path | None:
    for name in (f"{doc['id']}--no-bookmarks.json", f"{doc['id']}--bookmarks.json"):
        for c in CACHES:
            if (c / name).exists():
                return c / name
    return None


def load_ext(doc: dict, variant: str) -> Extraction | None:
    """variant "nobm": no outline; "bm": the bookmarked PDF's outline."""
    p = cache_path(doc)
    if p is None:
        return None
    ext = Extraction.load(p)
    ext.outline = read_outline(Path(doc["pdf"])) if variant == "bm" else []
    return ext


def docling_of(doc: dict, variant: str) -> dict | None:
    name = f"{doc['id']}.hier.json" if variant == "bm" else f"{doc['id']}--nobm.hier.json"
    for d in DOCLING:
        if (d / name).exists():
            return json.loads((d / name).read_text())
    if variant == "nobm" and doc["set"] == "corpus":  # corpus PDFs: one Docling run, the text is the same
        return docling_of(doc, "bm")
    return None


# ── locating headings in an extraction ──
def norm(s: str) -> str:
    return canon(s).replace(" ", "")


@dataclass
class Spans:
    """Every line, and every two and three consecutive lines on one page, as normalised text."""

    ext: Extraction
    keys: list[tuple[int, ...]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    page: list[int] = field(default_factory=list)
    by_page: dict[int, list[int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        lines = self.ext.lines
        for i, ln in enumerate(lines):
            for k in (1, 2, 3):
                js = tuple(range(i, i + k))
                if js[-1] >= len(lines) or lines[js[-1]].page != ln.page:
                    break
                t = norm(" ".join(lines[j].text for j in js))
                if not t:
                    continue
                self.by_page.setdefault(ln.page, []).append(len(self.keys))
                self.keys.append(js)
                self.texts.append(t)
                self.page.append(ln.page)
        self.lens = np.array([len(t) for t in self.texts])

    def sims(self, q: str, idx: list[int]) -> tuple[np.ndarray, np.ndarray]:
        """(evaluate._sim, plain ratio) of q against the spans idx. _sim is the ratio, or the partial
        ratio when the shorter side is at least half the longer (the scorer's own measure)."""
        if not idx or not q:
            return np.zeros(len(idx)), np.zeros(len(idx))
        ch = [self.texts[i] for i in idx]
        r = process.cdist([q], ch, scorer=fuzz.ratio, workers=1)[0]
        pr = process.cdist([q], ch, scorer=fuzz.partial_ratio, workers=1)[0]
        lens = self.lens[idx]
        comparable = np.minimum(lens, len(q)) >= 0.5 * np.maximum(lens, len(q))
        return np.where(comparable, np.maximum(r, pr), r), r

    def best(self, title: str, pages: list[int], exclude: set[int] = frozenset(), min_score: float = THRESHOLD,
             target: int | None = None, strict: bool = False):
        """(score, line indexes, page) of the best span on `pages` whose lines avoid `exclude`.
        The scorer's measure (or, `strict`, the plain ratio) must reach min_score; ties go to the
        higher plain ratio ("Direct Detection" over "Indirect Detection"), then the page nearest
        `target`, then the shorter span, then the earlier line."""
        q = norm(title)
        idx = [i for p in pages for i in self.by_page.get(p, []) if not exclude.intersection(self.keys[i])]
        if not idx:
            return None
        sim, r = self.sims(q, idx)
        s = r if strict else sim
        ok = np.flatnonzero(s >= min_score)
        if not len(ok):
            return None

        def rank(j: int):
            i = idx[j]
            return (round(float(s[j]), 6), float(r[j]), -abs(self.page[i] - target) if target else 0,
                    -len(self.keys[i]), -self.keys[i][0])

        j = max(ok, key=rank)
        i = idx[j]
        return float(s[j]), list(self.keys[i]), self.page[i]


LEADERS = re.compile(r"(?:[.:·]\s?){5,}")  # leaders of a contents entry ("Introduction . . . . 5", "Comments : : : : 7")


def contents_lines(ext: Extraction) -> set[int]:
    """Lines of printed contents lists: the library's contents detection (toc_of, listing_of), and any
    line with dot leaders, which the detection misses when the page numbers sit on lines of their own."""
    return set(toc_of(ext).lines) | set(listing_of(ext)) | {ln.i for ln in ext.lines if LEADERS.search(ln.text)}


def locate(ext: Extraction, gold: list[dict], spans: Spans | None = None) -> list[dict]:
    """For each gold heading: where its title is printed.
    status: "page" (a non-contents line on the gold page ±1), "contents" (only a contents-list line
    there), "far" (only more than one page away), "none" (nowhere in the extraction at 85%).
    For "contents", `body` is its first later copy outside contents lists and furniture."""
    spans = spans or Spans(ext)
    cont = contents_lines(ext)
    furn = furniture_of(ext)
    npages = max((ln.page for ln in ext.lines), default=0)
    out = []
    for g in gold:
        p = g["page"]
        near = [q for q in (p - 1, p, p + 1) if 1 <= q <= npages]
        hit = spans.best(g["title"], near, exclude=cont | furn, target=p)
        row = {"status": "none"}
        if hit:
            row = {"status": "page", "score": hit[0], "lines": hit[1], "page": hit[2]}
        else:
            c = spans.best(g["title"], near, target=p)
            if c and set(c[1]) & cont:
                row = {"status": "contents", "score": c[0], "lines": c[1], "page": c[2]}
                later = list(range(p + 2, npages + 1))
                b = spans.best(g["title"], later, exclude=cont | furn, strict=True)
                if b:
                    row["body"] = {"score": b[0], "lines": b[1], "page": b[2]}
            elif c:  # a furniture line (running header) on the page
                row = {"status": "page", "score": c[0], "lines": c[1], "page": c[2], "furniture": True}
            else:
                far = spans.best(g["title"], list(range(1, npages + 1)), exclude=cont, target=p)
                if far:
                    row = {"status": "far", "score": far[0], "lines": far[1], "page": far[2]}
        out.append(row)
    return out


_PDFIUM: dict[str, list[str]] = {}


def pdfium_pages(pdf: str) -> list[str]:
    """Each page's text from pypdfium2 (a second extractor), normalised."""
    if pdf not in _PDFIUM:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(pdf)
        try:
            _PDFIUM.clear()
            _PDFIUM[pdf] = [norm(doc[i].get_textpage().get_text_range()) for i in range(len(doc))]
        finally:
            doc.close()
    return _PDFIUM[pdf]


def in_text_layer(pdf: str, title: str, page: int) -> bool:
    pages = pdfium_pages(pdf)
    q = norm(title)
    if not q:
        return False
    for p in (page - 1, page, page + 1):
        if 1 <= p <= len(pages) and (q in pages[p - 1] or (len(q) >= 6 and fuzz.partial_ratio(q, pages[p - 1]) >= 90)):
            return True
    return False


# ── scoring with the pairs kept (section_anything.evaluate.score) ──
def heads(sections: list[dict]) -> list[dict]:
    return [{"title": f"{s.get('number', '') or ''} {s['title']}".strip(), "level": s.get("level", 1),
             "page": s["page_start"], "start": s.get("start"), "first_line": s.get("first_line")}
            for s in sections if "front_matter" not in (s.get("flags") or [])]


def pair(gold: list[dict], pred: list[dict]) -> dict[int, int]:
    from section_anything.evaluate import _sim

    cands = []
    for gi, g in enumerate(gold):
        for pj, p in enumerate(pred):
            if abs(p["page"] - g["page"]) <= 1:
                s = _sim(g["title"], p["title"])
                if s >= THRESHOLD:
                    cands.append((s, -abs(p["page"] - g["page"]), gi, pj))
    pairs, used = {}, set()
    for _s, _d, gi, pj in sorted(cands, reverse=True):
        if gi not in pairs and pj not in used:
            pairs[gi] = pj
            used.add(pj)
    return pairs


# ── why a line is not a candidate (mirrors rules.candidates, first rule that rejects it) ──
@dataclass
class CandCtx:
    ext: Extraction
    loose: bool

    def __post_init__(self) -> None:
        ext, loose = self.ext, self.loose
        self.body = ext.body_size()
        self.furniture = furniture_of(ext)
        self.toc = set(toc_of(ext).lines)
        self.labels = set() if loose else R._labels(ext, self.body)
        self.hints = hints_of(ext)
        self.bump = 0.4 if loose else 0.8
        self.side = R.side_notes(ext)
        self.labelled = R._label_lines(ext, self.furniture | self.toc, self.body, self.bump, self.side)
        self.titles = set(self.labelled.values())
        self.cells = set() if loose else R._table_cells(ext, self.furniture | self.toc | self.side)
        self.kept = {ln.i for ln, _ in R.candidates(ext, loose=loose)}

    def why(self, i: int) -> str:
        """"candidate", or the rule that leaves line i out; "plain" = neither styled nor numbered."""
        if i in self.kept:
            return "candidate"
        ln, text = self.ext.lines[i], self.ext.lines[i].text
        loose = self.loose
        for name, s in (("furniture", self.furniture), ("contents_list", self.toc), ("side_note", self.side),
                        ("table_cell", self.cells)):
            if i in s:
                return name
        if R.CAPTION.match(text):
            return "caption"
        if i in self.labelled or (loose and R.DIVISION_ONLY.match(R._label_text(text))):
            return "label_without_title"
        if split_number(self.ext, ln):
            return "split_number_without_title"
        if self.hints is not None and i in self.hints.headers:
            return "theorem_or_repeated_label"
        if self.hints is not None and not loose and i in self.hints.body:
            return "docling_body"
        if not re.search(r"[A-Za-z]", text):
            return "no_letters"
        words = len(text.split())
        if len(text) > (160 if loose else 120) or words > (20 if loose else 16):
            return "too_long"
        letters = sum(c.isalpha() for c in text)
        if len(text.strip()) <= 2 and R._vertical(self.ext, ln):
            return "vertical"
        index_letter = bool(re.fullmatch(r"[A-Z]", text.strip())) and ln.bold and ln.size >= self.body + 1.0
        if not index_letter and (letters < (2 if loose else 3) or (not loose and letters < 0.5 * len(text.replace(" ", "")))):
            return "few_letters"
        m = R.NUMBERING.match(text)
        styled = ln.size >= self.body + self.bump or (ln.bold and ln.size >= self.body - 0.3) or i in self.titles
        numbered = bool(m) and not text.rstrip().endswith((",", ";")) and words <= 14
        if not loose:
            if text.strip().lower() in self.labels:
                return "repeated_label"
            if R.THEOREM.match(text):
                return "theorem"
            if numbered and not styled:
                num = m.group("num")
                ok = bool(re.match(r"\d+\.\d+", num) or re.match(r"[A-Za-z]{3,}", num))
                if not (ok and not text.rstrip().endswith((".", "?", ":"))):
                    return "numbered_body_type"
            if styled and not numbered and ln.size < self.body + self.bump and i not in self.titles and R._runs_on(self.ext, ln):
                return "runs_on"
        if not styled and not numbered:
            return "plain"
        return "label_or_number_without_title"


# ── Free with every stage recorded ──
def free_trace(ext: Extraction, settings: Settings | None = None) -> dict:
    s = settings or Settings()
    strat = R.RulesStrategy()
    side = R.side_notes(ext)
    cands = R.candidates(ext)
    import inspect

    with_ext = "ext" in inspect.signature(R._merge_wrapped).parameters  # fix/match-failures passes the layout
    merged = R._merge_wrapped(cands, hints_of(ext), side, ext) if with_ext else R._merge_wrapped(cands, hints_of(ext), side)
    starts = {ln.i for ln, _, _ in merged}
    joined = {ln.i for ln, _ in cands} - starts
    rules_start = {r.start_line for r in strat._rules(ext)}
    ctx = Context(model="", usage=Usage(), cost_cap_usd=0.0, progress=lambda _f, _m: None, settings=s)
    raw = asyncio.run(strat.run(ext, ctx))
    secs, _extra = resolve(raw, ext, Locator(ext.text), strat.contents(ext))
    mark_doc_title(secs, ext)
    resolved = [x for x in secs]
    final = resolved
    if "free" in s.demote_unlisted_headings:
        final = demote_unlisted_headings(resolved, ext, strict=False).sections
    first = lambda xs: {x["first_line"] for x in xs if "front_matter" not in (x.get("flags") or [])}  # noqa: E731
    from section_anything.api import _public

    return {"cands": {ln.i for ln, _ in cands}, "joined": joined, "rules": rules_start,
            "raw": {r.start_line for r in raw}, "resolved": first(resolved), "final": first(final),
            "sections": [dict(_public(x)) | {"first_line": x["first_line"]} for x in final]}


def free_stage(tr: dict, lines: list[int]) -> str:
    """Where Free lost a heading whose first line is a candidate."""
    i = lines[0]
    if i in tr["joined"] or any(j in tr["joined"] for j in lines[:1]):
        return "merged_into_previous"
    if i not in tr["rules"]:
        return "rules_other"
    if i not in tr["raw"] and i - 1 not in tr["raw"]:
        return "outline_replaced"
    if i not in tr["resolved"] and i - 1 not in tr["resolved"]:
        return "resolve_failed"
    if i not in tr["final"] and i - 1 not in tr["final"]:
        return "outline_check"
    return "kept_title_differs"
