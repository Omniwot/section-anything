"""Public laws and regulations from several countries; each drafting office
structures and styles headings differently. About 10 of the 100+ corpus
files, per the owner's 13 Oct decision. Gold comes from the publisher's XML
where there is one, otherwise bookmarks, otherwise the act's own printed
arrangement of sections (India, South Africa), always located in the body."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from common import Entry, anchor, built, extraction, fetch, from_bookmarks, register

LAW = "law/"
# "B" may be a separate drop-cap line, leaving "E IT ENACTED …".
ENACTED = (
    r"(?:\bbe|^\s*e)\s+it\s+(?:therefore\s+)?enacted\b|enacted\s+by\s+(?:parliament|the\s+oireachtas)"
    r"|\benacts,?\s+as\s+follows"
)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(el: ET.Element | None) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def xml_headings(path: Path, structural: dict[str, tuple[str, str]], skip: set[str]) -> list[tuple[int, str]]:
    """Headings of structural elements in document order. `structural` maps
    element name → (number child, title child); levels follow nesting among
    structural elements. Subtrees in `skip` (quoted amendments, contents
    lists) are ignored."""
    root = ET.parse(path).getroot()
    out: list[tuple[int, str]] = []

    def walk(el: ET.Element, depth: int) -> None:
        name = _local(el.tag)
        if name in skip:
            return
        d = depth
        if name in structural:
            num_tag, title_tag = structural[name]
            num = next((_text(c) for c in el if _local(c.tag) == num_tag), "") if num_tag else ""
            title = next((_text(c) for c in el if _local(c.tag) == title_tag), "")
            if not title and name == "Schedule":
                tb = next((c for c in el if _local(c.tag) == "TitleBlock"), None)
                title = next((_text(c) for c in tb if _local(c.tag) == "Title"), "") if tb is not None else ""
            label = " ".join(x for x in (num, title) if x).strip()
            if label:
                out.append((depth + 1, label))
                d = depth + 1
        for c in el:
            walk(c, d)

    walk(root, 0)
    return out


CONTENTS = r"^(?:contents(?: of act)?|arrangement of sections|table of contents)$"


def printed_contents(pdf: Path) -> tuple[list[tuple[int, str]], str]:
    """The act's own printed contents ("Arrangement of sections"): chapter
    lines (level 1), Part / Condition lines (2, 3) and numbered sections (4).
    Read from the contents marker until the first chapter line repeats,
    which is where the body begins. Running headers and margin line numbers
    are dropped; wrapped section titles are joined. Returns the items and the
    first heading line, so the body can be searched from its repeat."""
    from collections import Counter

    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    try:
        pages = [[ln.strip() for ln in doc[i].get_textpage().get_text_range().splitlines() if ln.strip()]
                 for i in range(len(doc))]
    finally:
        doc.close()
    furniture = {ln for ln, n in Counter(ln for p in pages for ln in set(p)).items() if n >= 3}
    flat = [ln for p in pages for ln in p if ln not in furniture and not re.fullmatch(r"\d{1,3}", ln)]
    start = next((i + 1 for i, ln in enumerate(flat) if re.match(CONTENTS, re.sub(r"[^A-Za-z ]", "", ln).strip(), re.IGNORECASE)), None)
    if start is None:
        return [], ""
    first = next((ln for ln in flat[start:] if re.fullmatch(r"(CHAPTER|PART)\s+[IVXLC\d]+[A-Z]?", ln, re.IGNORECASE)), "")
    lines, seen = [], 0
    for ln in flat[start:]:
        if ln == first:
            seen += 1
            if seen == 2:
                break
        if re.search(ENACTED, ln, re.IGNORECASE):  # contents printed before the enacting words
            break
        lines.append(ln)
    out: list[tuple[int, str]] = []
    pending_chapter = None
    for ln in lines:
        if re.fullmatch(r"(CHAPTER|PART)\s+[IVXLC\d]+[A-Z]?", ln, re.IGNORECASE):
            pending_chapter = ln
            continue
        sub = re.match(r"^(Part [A-Z]|Condition \d+)\b\s*(.*)", ln)
        if sub:
            out.append((2 if sub.group(1).startswith("Part") else 3, ln))
            continue
        if pending_chapter:
            if ln.isupper() or re.match(r"[A-Z][A-Z ,’'&-]+$", ln):
                out.append((1, f"{pending_chapter} {ln.title()}"))
                pending_chapter = None
                continue
            out.append((1, pending_chapter))
            pending_chapter = None
        m = re.match(r"^(\d+[A-Z]*)\.\s+(.+)", ln)
        if m:
            out.append((4, f"{m.group(1)}. {m.group(2).rstrip('.')}"))
        elif (out and out[-1][0] == 4 and not ln.endswith(":") and len(out[-1][1]) < 160 and not re.match(r"^\d", ln)
              and not re.match(r"(SECTIONS?|CLAUSES?|THE \w+ SCHEDULE)$", ln, re.IGNORECASE)):
            out[-1] = (4, f"{out[-1][1]} {ln.rstrip('.')}")
    return out, first


DOCS = [
    # id, url, cache file, title, licence, how, extra
    ("uk-climate-change-act-2008", "https://www.legislation.gov.uk/ukpga/2008/27/pdfs/ukpga_20080027_en.pdf",
     "uk-cca2008.pdf", "Climate Change Act 2008 (UK, as enacted)", "Open Government Licence v3.0",
     ("xml", "https://www.legislation.gov.uk/ukpga/2008/27/enacted/data.xml", "uk-cca2008.xml",
      {"Part": ("Number", "Title"), "Chapter": ("Number", "Title"), "Pblock": ("", "Title"),
       "P1group": ("", "Title"), "Schedule": ("Number", "Title")},
      {"BlockAmendment", "Contents", "Metadata", "EN"})),
    ("ie-data-protection-act-2018", "https://www.irishstatutebook.ie/eli/2018/act/7/enacted/en/pdf",
     "ie-dpa2018.pdf", "Data Protection Act 2018 (Ireland)", "Irish PSI licence (CC BY 4.0 compatible)",
     ("xml", "https://www.irishstatutebook.ie/eli/2018/act/7/enacted/en/xml", "ie-dpa2018.xml",
      {"part": ("", "title"), "chapter": ("", "title"), "sect": ("number", "title"), "schedule": ("", "title")},
      {"frontmatter", "toc"})),
    ("us-music-modernization-act", "https://www.govinfo.gov/content/pkg/PLAW-115publ264/pdf/PLAW-115publ264.pdf",
     "us-plaw-115-264.pdf", "Public Law 115-264, Music Modernization Act (US)", "US public domain",
     ("xml", "https://www.govinfo.gov/content/pkg/PLAW-115publ264/uslm/PLAW-115publ264.xml", "us-plaw-115-264.xml",
      {k: ("num", "heading") for k in ("division", "title", "subtitle", "part", "subpart", "chapter", "subchapter", "section")},
      {"quotedContent", "toc", "meta", "preface", "endMarker"})),
    ("us-chips-and-science-act", "https://www.govinfo.gov/content/pkg/PLAW-117publ167/pdf/PLAW-117publ167.pdf",
     "us-plaw-117-167.pdf", "Public Law 117-167, CHIPS and Science Act (US)", "US public domain",
     ("xml", "https://www.govinfo.gov/content/pkg/PLAW-117publ167/uslm/PLAW-117publ167.xml", "us-plaw-117-167.xml",
      {k: ("num", "heading") for k in ("division", "title", "subtitle", "part", "subpart", "chapter", "subchapter", "section")},
      {"quotedContent", "toc", "meta", "preface", "endMarker"})),
    ("ca-privacy-act", "https://laws-lois.justice.gc.ca/PDF/P-21.pdf", "ca-privacy.pdf",
     "Privacy Act, R.S.C. 1985, c. P-21 (Canada)", "Open Government Licence – Canada", ("bookmarks", {})),
    ("de-grundgesetz", "https://www.gesetze-im-internet.de/gg/GG.pdf", "de-gg.pdf",
     "Grundgesetz für die Bundesrepublik Deutschland (Germany, in German)", "Amtliches Werk, § 5 UrhG (public domain)",
     ("bookmarks", {})),
    ("au-privacy-act-1988", "https://www.legislation.gov.au/C2004A03712/2026-06-04/2026-06-04/text/original/pdf",
     "au-privacy.pdf", "Privacy Act 1988, compilation 104 (Australia, excerpt)", "CC BY 4.0",
     ("bookmarks", {"max_pages": 300})),
    ("jp-appi-english", "https://www.ppc.go.jp/files/pdf/APPI_english.pdf", "jp-appi.pdf",
     "Act on the Protection of Personal Information (Japan, English translation)", "CC BY 4.0 (e-Gov data portal)",
     ("bookmarks", {})),
    ("in-information-technology-act-2000",
     "https://www.indiacode.nic.in/bitstream/123456789/13116/1/it_act_2000_updated.pdf",
     "in-itact.pdf", "Information Technology Act, 2000 (India)", "Government of India (GODL-India)",
     ("printed",)),
    ("za-popia-2013", "https://www.gov.za/sites/default/files/gcis_document/201409/3706726-11act4of2013popi.pdf",
     "za-popia.pdf", "Protection of Personal Information Act 4 of 2013 (South Africa, Government Gazette)",
     "South African government publication", ("printed",)),
]


def build(force: bool = False) -> None:
    for key, url, name, title, licence, how in DOCS:
        eid = f"law-{key}"
        if built(eid) and not force:
            continue
        try:
            pdf = fetch(url, LAW + name, timeout=300)
        except RuntimeError as e:
            print(f"  ✗ {eid}: {e}")
            continue
        entry = Entry(id=eid, category="legislation", title=title, source_url=url, license=licence, gold_source="")
        if how[0] == "bookmarks":
            entry.gold_source, entry.complete = "bookmarks", False
            from_bookmarks(entry, pdf, **how[1])
            continue
        ext = extraction(pdf)
        # Section headings in many acts run into the first sentence ("1. Short title.—(1) This Act …").
        if how[0] == "xml":
            _, xurl, xname, structural, skip = how
            items = xml_headings(fetch(xurl, LAW + xname), structural, skip)
            entry.gold_source = "legislation-xml"
            # Search after the enacting words, past any printed contents.
            gold, missing = anchor(ext, items, pdf_titles=True, run_in=True, start_after=ENACTED)
            if len(missing) > 0.5 * len(items):
                gold, missing = anchor(ext, items, pdf_titles=True, run_in=True)
        else:
            items, first = printed_contents(pdf)
            entry.gold_source, entry.complete = "printed-contents", True
            hits = [i for i, ln in enumerate(ext.lines) if ln.text.strip() == first]
            enacted = [i for i, ln in enumerate(ext.lines) if re.search(ENACTED, ln.text, re.IGNORECASE)]
            body = max(hits[1] if len(hits) > 1 else 0, enacted[0] if enacted and hits and enacted[0] > hits[0] else 0)
            gold, missing = anchor(ext, items, pdf_titles=True, run_in=True, start_line=body)
        entry.notes = f"unanchored: {missing[:5]}" if missing else ""
        register(entry, pdf, gold, len(missing))
