"""Outline check: sections a complete PDF outline does not list are dropped, and only then."""

from __future__ import annotations

import asyncio

from section_anything import Settings, pipeline
from section_anything.extract import Extraction, Line, OutlineItem, Page
from section_anything.outline_check import demote_unlisted_headings, is_standard_heading, rebound

BODY = "Ordinary body text runs on for a while in the regular face at the body size of the page."


def _ext(rows: list[tuple[str, float, bool]], outline: list[tuple[int, str, int]], per_page: int = 12) -> Extraction:
    """rows: (text, size, bold); outline: (level, title, page)."""
    lines, cursor = [], 0
    for i, (t, size, bold) in enumerate(rows):
        page, k = i // per_page + 1, i % per_page
        lines.append(Line(i=i, page=page, text=t, x0=72, y0=700 - k * 20, x1=500, y1=712 - k * 20,
                          size=size, bold=bold, start=cursor, end=cursor + len(t)))
        cursor += len(t) + 1
    pages = [Page(n=p, width=612, height=792, origin_x=0, origin_y=0, rotation=0, has_text=True)
             for p in range(1, lines[-1].page + 1)]
    ext = Extraction(pages, lines, "\n".join(t for t, _, _ in rows))
    ext.outline = [OutlineItem(level=lv, title=t, page=p) for lv, t, p in outline]
    return ext


def _sections(ext: Extraction, heads: list[tuple[int, int, str]], flags: dict[int, list[str]] | None = None) -> list[dict]:
    """heads: (line index, level, number). Titles are the line text after the number."""
    out = []
    for i, level, number in heads:
        ln = ext.lines[i]
        title = ln.text[len(number):].strip() if number else ln.text
        out.append({"number": number, "title": title, "level": level, "start": ln.start, "first_line": i,
                    "page_start": ln.page, "flags": list((flags or {}).get(i, []))})
    return rebound(out, ext)


def _paper(label: str = "Note", label_bold: bool = True) -> tuple[Extraction, list[dict]]:
    rows = [("1 Introduction", 14, True), (BODY, 10, False), (label, 10, label_bold), (BODY, 10, False),
            ("2 Methods", 14, True), (BODY, 10, False), ("2.1 Data", 12, True), (BODY, 10, False),
            ("3 Results", 14, True), (BODY, 10, False)]
    outline = [(1, "1 Introduction", 1), (1, "2 Methods", 1), (2, "2.1 Data", 1), (1, "3 Results", 1)]
    ext = _ext(rows, outline)
    return ext, _sections(ext, [(0, 1, "1"), (2, 2, ""), (4, 1, "2"), (6, 2, "2.1"), (8, 1, "3")])


def titles(secs: list[dict]) -> list[str]:
    return [s["title"] for s in secs]


def test_unlisted_heading_is_dropped_and_its_text_joins_the_previous_section():
    ext, secs = _paper()
    res = demote_unlisted_headings(secs, ext)
    assert res.reason == "demoted" and titles(res.demoted) == ["Note"]
    assert titles(res.sections) == ["Introduction", "Methods", "Data", "Results"]
    intro = res.sections[0]
    assert intro["end"] == ext.lines[3].end and intro["last_line"] == 3 and intro["id"] == 0
    assert [s["id"] for s in res.sections] == [0, 1, 2, 3]
    assert len(secs) == 5  # input untouched


def test_flat_outline_is_not_trusted():
    ext, secs = _paper()
    ext.outline = [OutlineItem(level=1, title=o.title, page=o.page) for o in ext.outline]
    assert demote_unlisted_headings(secs, ext).reason == "flat outline"


def test_unmatched_dotted_heading_means_the_outline_is_incomplete():
    ext, secs = _paper()
    ext.outline = [o for o in ext.outline if o.title != "2.1 Data"] + [OutlineItem(2, "1.1 Background", 1)]
    res = demote_unlisted_headings(secs, ext)
    assert res.reason == "unmatched numbered heading" and res.sections is secs


def test_section_number_of_an_unmatched_bookmark_counts_as_matched():
    ext, secs = _paper()
    ext.outline[2] = OutlineItem(level=2, title="2.1 Data sets and ??", page=1)  # bookmark text differs
    res = demote_unlisted_headings(secs, ext)
    assert res.reason == "demoted" and titles(res.demoted) == ["Note"]


def test_standard_headings_are_kept_even_letter_spaced():
    assert is_standard_heading("Abstract") and is_standard_heading("R E F E R E N C E S")
    assert is_standard_heading("A. Appendix: proofs") and not is_standard_heading("Abstraction layers")
    ext, secs = _paper(label="A B S T R A C T")
    assert demote_unlisted_headings(secs, ext).reason == "nothing to demote"


def test_doc_title_and_front_matter_are_kept():
    rows = [("A Study of Things", 18, True), (BODY, 10, False), ("1 Introduction", 14, True), (BODY, 10, False),
            ("1.1 Scope", 12, True), (BODY, 10, False)]
    ext = _ext(rows, [(1, "1 Introduction", 1), (2, "1.1 Scope", 1)])
    secs = _sections(ext, [(0, 1, ""), (2, 1, "1"), (4, 2, "1.1")], flags={0: ["doc_title"]})
    assert demote_unlisted_headings(secs, ext).reason == "nothing to demote"


def test_dropped_first_section_becomes_front_matter():
    ext, secs = _paper()
    rows = [("Jane Doe, University of Somewhere", 11, True), (BODY, 10, False)]
    ext = _ext(rows + [(ln.text, ln.size, ln.bold) for ln in ext.lines], [(o.level, o.title, o.page) for o in ext.outline])
    secs = _sections(ext, [(0, 1, ""), (2, 1, "1"), (6, 1, "2"), (8, 2, "2.1"), (10, 1, "3")])
    res = demote_unlisted_headings(secs, ext)
    assert res.reason == "demoted" and titles(res.demoted) == ["Jane Doe, University of Somewhere"]
    front = res.sections[0]
    assert front["flags"] == ["front_matter"] and front["start"] == 0 and front["end"] == ext.lines[1].end


def test_strict_keeps_a_family_of_unlisted_headings_in_one_style():
    rows = [("1 Usage", 14, True), (BODY, 10, False), ("Install", 10, True), (BODY, 10, False),
            ("Configure", 10, True), (BODY, 10, False), ("2 Gallery", 14, True), (BODY, 10, False),
            ("2.1 Plots", 12, True), (BODY, 10, False), ("2.2 Maps", 12, True), (BODY, 10, False)]
    outline = [(1, "1 Usage", 1), (1, "2 Gallery", 1), (2, "2.1 Plots", 1), (2, "2.2 Maps", 1)]
    ext = _ext(rows, outline)
    secs = _sections(ext, [(0, 1, "1"), (2, 2, ""), (4, 2, ""), (6, 1, "2"), (8, 2, "2.1"), (10, 2, "2.2")])
    assert demote_unlisted_headings(secs, ext, strict=True).reason == "shared style"
    loose = demote_unlisted_headings(secs, ext, strict=False)
    assert loose.reason == "demoted" and titles(loose.demoted) == ["Install", "Configure"]


def test_strict_needs_half_of_the_sections_listed():
    rows = [("1 Usage", 14, True), (BODY, 10, False), ("2 Notes", 14, True), (BODY, 10, False),
            ("2.1 More", 12, True)] + [(f"Label {k}", 10 + k, True) for k in range(4)]
    outline = [(1, "1 Usage", 1), (1, "2 Notes", 1), (2, "2.1 More", 1)]
    ext = _ext(rows, outline)
    secs = _sections(ext, [(0, 1, "1"), (2, 1, "2"), (4, 2, "2.1")] + [(5 + k, 2, "") for k in range(4)])
    assert demote_unlisted_headings(secs, ext, strict=True).reason == "under half matched"
    assert demote_unlisted_headings(secs, ext, strict=False).reason == "demoted"


def test_outline_that_names_other_headings_is_not_trusted():
    ext, secs = _paper()
    ext.outline = [ext.outline[0], ext.outline[2]] + [OutlineItem(1, f"Chapter about topic {k}", 1) for k in range(5)]
    assert demote_unlisted_headings(secs, ext, strict=False).reason == "outline not found"


def test_bookmark_matches_on_its_page_or_the_next_only():
    ext, secs = _paper()
    ext.outline = [OutlineItem(o.level, o.title, 3) for o in ext.outline]  # every bookmark two pages off
    assert demote_unlisted_headings(secs, ext, strict=False).reason == "outline not found"


def test_no_outline_changes_nothing():
    ext, secs = _paper()
    ext.outline = []
    res = demote_unlisted_headings(secs, ext)
    assert res.reason == "no outline" and res.sections is secs and not res.demoted


def test_setting_reads_modes_from_the_environment(monkeypatch):
    assert Settings().demote_unlisted_headings == ["free"]
    monkeypatch.setenv("SECTIONANY_DEMOTE_UNLISTED_HEADINGS", '["free", "standard"]')
    assert Settings().demote_unlisted_headings == ["free", "standard"]
    monkeypatch.setenv("SECTIONANY_DEMOTE_UNLISTED_HEADINGS", "[]")
    assert Settings().demote_unlisted_headings == []


def test_pipeline_applies_the_check_only_in_the_chosen_modes():
    ext, _ = _paper()

    def run(modes: list[str]) -> tuple[list[dict], dict]:
        _raw, secs, metrics = asyncio.run(pipeline.run(ext, "rules", "", 0.0, settings=Settings(demote_unlisted_headings=modes)))
        return secs, metrics

    off, m_off = run([])
    assert "Note" in titles(off) and "outline_check" not in m_off
    on, m_on = run(["free"])
    assert "Note" not in titles(on) and m_on["outline_check"]["reason"] == "demoted"
    assert titles(run(["standard"])[0]) == titles(off)
