"""Typeset documents with reportlab (BSD) and record exact gold.

A document is a list of blocks:
    ("h", level, text)            heading
    ("runin", level, head, text)  heading run into its paragraph ("Causes.— text …")
    ("p", text)                   paragraph
    ("label", text)               bold short line that is NOT a heading (speaker names, captions)
    ("break",)                    scene break "* * *" (no heading)
    ("page",)                     page break
    ("table", rows)               table, rows of strings
    ("image",)                    a grey box standing in for a figure
Gold is every "h"/"runin" block with the page it landed on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


@dataclass
class Style:
    """House style. `heading[level]` = (font, size, align, upper, space_before)."""
    page: tuple = letter
    body_font: str = "Times-Roman"
    body_size: float = 11
    leading: float = 14
    align: int = TA_JUSTIFY
    columns: int = 1
    margin: float = 25 * mm
    heading: dict = field(default_factory=lambda: {
        1: ("Times-Bold", 18, TA_CENTER, False, 24),
        2: ("Times-Bold", 14, TA_LEFT, False, 16),
        3: ("Times-BoldItalic", 12, TA_LEFT, False, 12),
        4: ("Times-Italic", 11, TA_LEFT, False, 10),
    })
    header: str = ""        # running header text ("" = none); "{h1}" = current level-1 heading
    footer_numbers: bool = True
    first_line_indent: float = 0
    para_space: float = 4
    new_page_level: int = 0  # headings at this level start a new page (0 = never)
    runin_font: str = "Times-Bold"
    number_offset: int = 0   # printed page number = physical page - offset (front matter unnumbered)
    encrypt: str = ""        # user password; the file then can't be opened without it


class _Doc(BaseDocTemplate):
    """Records the page each heading paragraph was actually drawn on."""

    def __init__(self, *a, gold: list, **kw):
        super().__init__(*a, **kw)
        self.gold = gold

    def afterFlowable(self, flowable) -> None:
        entry = getattr(flowable, "_gold", None)
        if entry is not None and "page" not in entry:
            self.gold.append({**entry, "page": self.page})


def _heading(p: Paragraph, entry: dict) -> Paragraph:
    p._gold = entry
    return p


class _Box(Flowable):
    def __init__(self, w: float, h: float):
        super().__init__()
        self.width, self.height = w, h

    def draw(self) -> None:
        self.canv.setFillColor(colors.lightgrey)
        self.canv.rect(0, 0, self.width, self.height, stroke=0, fill=1)


def _t(s: str) -> str:
    return escape(s)


def render(blocks: list[tuple], style: Style, out: Path, title: str = "") -> list[dict]:
    gold: list[dict] = []
    state = {"h1": title}
    w, h = style.page
    m = style.margin
    gap = 8 * mm
    col_w = (w - 2 * m - gap * (style.columns - 1)) / style.columns
    frames = [Frame(m + i * (col_w + gap), m, col_w, h - 2 * m, id=f"c{i}", showBoundary=0) for i in range(style.columns)]

    def furniture(canv, doc) -> None:
        canv.saveState()
        canv.setFont(style.body_font, 8.5)
        if style.header:
            canv.drawCentredString(w / 2, h - m / 2, style.header.replace("{h1}", state["h1"]))
        if style.footer_numbers and doc.page > style.number_offset:
            canv.drawCentredString(w / 2, m / 2, str(doc.page - style.number_offset))
        canv.restoreState()

    doc = _Doc(str(out), pagesize=style.page, leftMargin=m, rightMargin=m, topMargin=m, bottomMargin=m,
               title=title, author="section-anything corpus generator", gold=gold,
               encrypt=style.encrypt or None)
    doc.addPageTemplates([PageTemplate(id="p", frames=frames, onPage=furniture)])

    body = ParagraphStyle("body", fontName=style.body_font, fontSize=style.body_size, leading=style.leading,
                          alignment=style.align, firstLineIndent=style.first_line_indent, spaceAfter=style.para_space)
    hs = {}
    for lvl, (font, size, align, _upper, before) in style.heading.items():
        hs[lvl] = ParagraphStyle(f"h{lvl}", fontName=font, fontSize=size, leading=size * 1.25, alignment=align,
                                 spaceBefore=before, spaceAfter=size * 0.5, keepWithNext=1)
    label = ParagraphStyle("label", parent=body, fontName="Times-Bold" if "Times" in style.body_font else "Helvetica-Bold",
                           alignment=TA_LEFT, spaceAfter=1, keepWithNext=1)
    story: list = []
    for b in blocks:
        kind = b[0]
        if kind == "h":
            _, lvl, text = b
            lvl = min(lvl, max(hs))
            upper = style.heading[lvl][3]
            shown = text.upper() if upper else text
            if style.new_page_level and lvl <= style.new_page_level and story:
                story.append(PageBreak())
            if lvl == 1:
                story.append(_SetH1(state, shown))
            story.append(_heading(Paragraph(_t(shown), hs[lvl]), {"level": lvl, "title": shown}))
        elif kind == "runin":
            _, lvl, head, text = b
            p = Paragraph(f'<font name="{style.runin_font}">{_t(head)}.</font>—{_t(text)}', body)
            story.append(_heading(p, {"level": lvl, "title": head, "run_in": True}))
        elif kind == "p":
            story.append(Paragraph(_t(b[1]), body))
        elif kind == "label":
            story.append(Paragraph(_t(b[1]), label))
        elif kind == "break":
            story.append(Paragraph("*&nbsp;&nbsp;&nbsp;*&nbsp;&nbsp;&nbsp;*", ParagraphStyle("brk", parent=body, alignment=TA_CENTER,
                                                                                         spaceBefore=6, spaceAfter=6)))
        elif kind == "tocline":
            _, lvl, text, page = b
            story.append(_TocLine(text, str(page), (lvl - 1) * 14, col_w, style.body_font, style.body_size,
                                  style.leading + 2))
        elif kind == "page":
            story.append(PageBreak())
        elif kind == "table":
            t = Table([[Paragraph(_t(c), ParagraphStyle("td", parent=body, fontSize=body.fontSize - 1.5,
                                                         leading=body.leading - 2, alignment=TA_LEFT)) for c in r]
                       for r in b[1]], repeatRows=1)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                   ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke)]))
            story += [Spacer(1, 4), t, Spacer(1, 6)]
        elif kind == "image":
            story += [Spacer(1, 4), _Box(col_w * 0.8, 120), Spacer(1, 6)]
    doc.build(story)
    return gold


class _TocLine(Flowable):
    """Contents line with dot leaders: 'Title . . . . . 12'."""

    def __init__(self, text, num, indent, width, font, size, height):
        super().__init__()
        self.text, self.num, self.indent, self.font, self.size = text, num, indent, font, size
        self.width, self.height = width, height

    def draw(self) -> None:
        c = self.canv
        c.setFont(self.font, self.size)
        c.drawString(self.indent, 2, self.text)
        c.drawRightString(self.width, 2, self.num)
        x = self.indent + c.stringWidth(self.text, self.font, self.size) + 6
        end = self.width - c.stringWidth(self.num, self.font, self.size) - 6
        while x < end:
            c.drawString(x, 2, ".")
            x += 4.5


class _SetH1(Flowable):
    def __init__(self, state: dict, text: str):
        super().__init__()
        self.state, self.text = state, text
        self.width = self.height = 0

    def draw(self) -> None:
        self.state["h1"] = self.text


PAGES = {"letter": letter, "a4": A4, "landscape": landscape(letter)}
