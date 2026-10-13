"""Generated slide decks (one slide per page unless a handout). Decks vary
in aspect ratio, title placement, divider slides, agenda slides, title bars
with a navigation strip naming every section on every slide, "(cont.)"
slides, title-less image slides, two-up handouts and inconsistent fonts
from merged decks. Gold: divider slides are level 1, slide titles level 2;
"(cont.)" slides and title-less slides add nothing."""

from __future__ import annotations

import random
import re

from common import CACHE, Entry, built, register
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from src_synthetic import _filler, _title

W169 = (960, 540)
W43 = (720, 540)


def _bullets(rnd: random.Random, sents: list[str], n: int) -> list[str]:
    return [rnd.choice(sents) for _ in range(n)]


def _deck(rnd: random.Random, sections: int, per: tuple, *, cont: float = 0.0, untitled: float = 0.0) -> list[dict]:
    """[{section, title, bullets, cont, image}] — section set only on divider entries."""
    out = []
    for s in range(sections):
        name = _title(rnd)
        out.append({"divider": name})
        for _ in range(rnd.randint(*per)):
            t = _title(rnd)
            img = rnd.random() < untitled
            out.append({"title": None if img else t, "image": img})
            if not img and rnd.random() < cont:
                out.append({"title": f"{t} (cont.)", "cont": True})
    return out


def _wrap(c: canvas.Canvas, text: str, font: str, size: float, width: float) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        nxt = f"{cur} {w}".strip()
        if c.stringWidth(nxt, font, size) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = nxt
    return lines + ([cur] if cur else [])


def render_deck(path, slides: list[dict], sents: list[str], rnd: random.Random, *, size=W169, title_font="Helvetica-Bold",
                title_size=30, title_align="left", bar: bool = False, nav: bool = False, numbered: bool = False,
                number_footer: bool = True, agenda: bool = False, dividers: bool = True, handout: bool = False,
                fonts_vary: bool = False, deck_title: str = "") -> list[dict]:
    pw, ph = (letter if handout else size)
    c = canvas.Canvas(str(path), pagesize=(pw, ph))
    c.setTitle(deck_title)
    gold: list[dict] = []
    sections = [s["divider"] for s in slides if "divider" in s]
    page, slot, sec_n, n, in_sec = 1, 0, 0, 0, 0
    sw, sh = size
    scale = (pw - 72) / sw if handout else 1.0

    def begin():
        nonlocal page, slot
        if handout:
            if slot == 2:
                c.showPage()
                page += 1
                slot = 0
            c.saveState()
            c.translate(36, ph - 36 - (slot + 1) * (sh * scale + 20) + 10)
            c.scale(scale, scale)
            c.setStrokeColor(colors.grey)
            c.rect(0, 0, sw, sh)
        else:
            c.saveState()

    def end():
        nonlocal page, slot
        c.restoreState()
        if handout:
            slot += 1
        else:
            c.showPage()
            page += 1

    def furniture(i: int):
        if nav:
            c.setFont("Helvetica", 9)
            x = 20
            for k, s in enumerate(sections):
                c.setFillColor(colors.black if k == sec_n - 1 else colors.grey)
                c.drawString(x, sh - 14, s)
                x += c.stringWidth(s, "Helvetica", 9) + 16
                if x > sw - 80:
                    break
            c.setFillColor(colors.black)
        if number_footer:
            c.setFont("Helvetica", 9)
            c.drawRightString(sw - 20, 14, f"{i}")
            c.drawString(20, 14, deck_title)

    def draw_title(t: str, font: str, sz: float):
        if bar:
            c.setFillColor(colors.HexColor("#1f3a5f"))
            c.rect(0, sh - 90, sw, 62 if nav else 90, stroke=0, fill=1)
            c.setFillColor(colors.white)
        c.setFont(font, sz)
        y = sh - 70
        if title_align == "center":
            c.drawCentredString(sw / 2, y, t)
        else:
            c.drawString(40, y, t)
        c.setFillColor(colors.black)

    # title slide
    begin()
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(sw / 2, sh / 2 + 20, deck_title)
    c.setFont("Helvetica", 16)
    c.drawCentredString(sw / 2, sh / 2 - 20, "Workshop series, autumn session")
    end()
    if agenda:
        begin()
        draw_title("Agenda", title_font, title_size)
        c.setFont("Helvetica", 20)
        for k, s in enumerate(sections):
            c.drawString(70, sh - 140 - k * 34, f"{k + 1}. {s}" if numbered else f"• {s}")
        end()
    for s in slides:
        n += 1
        font, sz = title_font, title_size
        if fonts_vary:
            font = ["Helvetica-Bold", "Times-Bold", "Courier-Bold"][sec_n % 3]
            sz = [30, 26, 22][sec_n % 3]
        if "divider" in s:
            sec_n += 1
            in_sec = 0
            name = f"{sec_n}. {s['divider']}" if numbered else s["divider"]
            if not dividers:
                continue
            begin()
            gold.append({"level": 1, "title": name, "page": page})
            c.setFont(font, sz + 10)
            c.drawCentredString(sw / 2, sh / 2, name)
            furniture(n)
            end()
            continue
        begin()
        if s.get("title"):
            t = s["title"]
            if numbered and not s.get("cont"):
                in_sec += 1
                t = f"{sec_n}.{in_sec} {t}"
            if not s.get("cont"):
                gold.append({"level": 2 if dividers else 1, "title": t, "page": page})
            draw_title(t, font, sz)
        if s.get("image"):
            c.setFillColor(colors.lightgrey)
            c.rect(60, 60, sw - 120, sh - 120, stroke=0, fill=1)
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Oblique", 12)
            c.drawCentredString(sw / 2, 40, rnd.choice(sents)[:90])
        else:
            y = sh - 130
            for b in _bullets(rnd, sents, rnd.randint(3, 5)):
                for j, line in enumerate(_wrap(c, b, "Helvetica", 18, sw - 140)[:2]):
                    c.setFont("Helvetica", 18)
                    c.drawString(70, y, ("• " if j == 0 else "  ") + line)
                    y -= 26
                y -= 8
        furniture(n)
        end()
    if handout and slot:
        c.showPage()
    c.save()
    return gold


DECKS = [
    ("slides-01-wide-dividers", "Field Methods 101", "16:9, divider slides, left titles", {}, {}),
    ("slides-02-4x3-numbered", "Survey Statistics", "4:3, numbered sections and slides",
     {"size": W43, "numbered": True, "title_size": 26}, {}),
    ("slides-03-agenda", "Sensor Networks", "agenda slide listing sections, then dividers", {"agenda": True}, {}),
    ("slides-04-no-dividers", "Maintenance Planning", "slide titles only, no divider slides", {"dividers": False}, {}),
    ("slides-05-title-bar-nav", "Hydraulic Models", "white title on a dark bar; navigation strip names every section",
     {"bar": True, "nav": True}, {}),
    ("slides-06-continued", "Data Quality Review", "many '(cont.)' slides that repeat a title", {}, {"cont": 0.5}),
    ("slides-07-centred", "Acoustic Testing", "centred small titles", {"title_align": "center", "title_size": 22,
                                                                        "title_font": "Helvetica"}, {}),
    ("slides-08-handout", "Coastal Erosion", "two slides per portrait handout page", {"handout": True}, {}),
    ("slides-09-image-heavy", "Urban Heat", "title-less image slides between titled ones", {}, {"untitled": 0.4}),
    ("slides-10-merged-fonts", "Retrofit Case Studies", "merged deck: title font and size change per section",
     {"fonts_vary": True}, {}),
]


def build(force: bool = False) -> None:
    sents = [s for p in _filler() for s in re.split(r"(?<=[.;])\s+", p) if 40 < len(s) < 140]
    d = CACHE / "slides"
    d.mkdir(parents=True, exist_ok=True)
    for i, (eid, title, why, look, shape) in enumerate(DECKS, 1):
        if built(eid) and not force:
            continue
        rnd = random.Random(100 + i)
        slides = _deck(rnd, sections=rnd.randint(4, 6), per=(3, 6), **shape)
        out = d / f"{eid}.pdf"
        gold = render_deck(out, slides, sents, rnd, deck_title=title, **look)
        register(Entry(id=eid, category="slides", title=title, source_url="generated",
                       license="Generated; bullet text from public-domain Project Gutenberg books",
                       gold_source="generator", variant=why), out, gold)
