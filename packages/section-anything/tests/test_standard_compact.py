"""Standard's compact answer (research finding F078): the model returns only each section's start line, level and
whether its title is printed (with a title of its own when it is not). The number, a printed title and the start
marker are read from the line as Free reads a heading, and each section ends where the next one starts. Fake model
only."""

from __future__ import annotations

import asyncio

from section_anything import pipeline
from section_anything.extract import Extraction, Line, Page
from section_anything.llm import Usage
from section_anything.markers import Locator
from section_anything.strategies import llm_text
from section_anything.strategies.base import Context
from section_anything.strategies.llm_text import TEXT_SYSTEM, LlmTextStrategy, TextResult, TextSection

LEVELS = {"title": 1, "plain": 1, "split": 1, "wrapped": 2, "label": 1, "untitled": 2, "bare": 1}
NAMES = list(LEVELS)
BODY = "Body text of the section runs on in the regular face at body size, as paragraphs do."


def _doc() -> tuple[Extraction, dict[str, int]]:
    """One page per heading kind; `at` maps a name to the line the model gives as the start."""
    rows: list[tuple] = []  # (text, size, bold, x0, same baseline as the previous row)
    at: dict[str, int] = {}

    def add(name: str | None, text: str, size: float = 10.0, bold: bool = False, x0: float = 72, beside: bool = False):
        if name:
            at[name] = len(rows)
        rows.append((text, size, bold, x0, beside, page))

    page = 1
    add("title", "A Study of Sectioning", 20, True)
    for _ in range(3):
        add(None, BODY)
    add("plain", "1 Introduction", 14, True)
    for _ in range(3):
        add(None, BODY)
    page = 2
    add("split", "2", 14, True)
    add(None, "Methods", 14, True, x0=90, beside=True)  # a number split off its title on the same baseline
    for _ in range(3):
        add(None, BODY)
    add("wrapped", "2.1 A heading that is long enough that it wraps", 12, True)
    add(None, "onto a second line", 12, True)
    for _ in range(3):
        add(None, BODY)
    page = 3
    add("label", "CHAPTER 3", 12, True)
    add(None, "Results", 16, True)
    for _ in range(3):
        add(None, BODY)
    add("untitled", "Untitled paragraphs start here and say what the results were, at length and in detail.")
    for _ in range(3):
        add(None, BODY)
    page = 4
    add("bare", "4", 24, True)
    add(None, "Conclusions", 16, True)
    for _ in range(3):
        add(None, BODY)

    lines, cursor, y, last_page = [], 0, 800.0, 1
    for i, (text, size, bold, x0, beside, pg) in enumerate(rows):
        if pg != last_page:
            y, last_page = 800.0, pg
        if not beside and i:
            y -= 1.3 * max(size, rows[i - 1][1]) if rows[i - 1][1] == size and bold and rows[i - 1][2] else 2.2 * size
        lines.append(Line(i=i, page=pg, text=text, x0=x0, y0=y, x1=x0 + 0.5 * size * len(text), y1=y + size,
                          size=size, bold=bold, start=cursor, end=cursor + len(text)))
        cursor += len(text) + 1
    pages = [Page(n=n, width=612, height=850, origin_x=0, origin_y=0, rotation=0, has_text=True) for n in range(1, 5)]
    return Extraction(pages, lines, "\n".join(r[0] for r in rows)), at


def _answer(at: dict[str, int], lines: dict[str, int] | None = None) -> TextResult:
    lines = {**at, **(lines or {})}
    return TextResult(sections=[
        TextSection(start_line=lines[k], level=LEVELS[k], title_from_text=k != "untitled",
                    title="What the results were" if k == "untitled" else "")
        for k in NAMES
    ])


def _run(monkeypatch, answer):
    ext, at = _doc()
    seen = []

    async def fake(**kw):
        seen.append(kw)
        return answer(at)

    monkeypatch.setattr(llm_text, "structured", fake)
    ctx = Context(model="fake", usage=Usage(), cost_cap_usd=1.0)
    raw = asyncio.run(LlmTextStrategy().run(ext, ctx))
    return ext, at, raw, seen


def test_number_and_title_are_read_from_the_start_line(monkeypatch):
    ext, at, raw, seen = _run(monkeypatch, _answer)
    got = {k: (r.number, r.title, r.start_line, r.title_from_text) for k, r in zip(NAMES, raw, strict=True)}
    assert got["title"] == ("", "A Study of Sectioning", at["title"], True)
    assert got["plain"] == ("1", "Introduction", at["plain"], True)
    assert got["split"] == ("2", "Methods", at["split"], True)
    # A title that wraps onto a second line in its style takes that line.
    assert got["wrapped"] == ("2.1", "A heading that is long enough that it wraps onto a second line", at["wrapped"], True)
    # A bare label takes the title line under it.
    assert got["label"] == ("CHAPTER 3", "Results", at["label"], True)
    # No printed heading: the model's own title, marked as written by the model.
    assert got["untitled"][1:] == ("What the results were", at["untitled"], False)
    # A number alone on its line takes the line under it as its title.
    assert got["bare"] == ("4", "Conclusions", at["bare"], True)
    assert len(seen) == 1


def test_a_title_line_after_its_split_off_number_starts_at_the_number(monkeypatch):
    ext, at, raw, _ = _run(monkeypatch, lambda at: _answer(at, {"split": at["split"] + 1}))
    split = raw[2]
    assert (split.number, split.title, split.start_line) == ("2", "Methods", at["split"])


def test_sections_start_on_their_lines_and_end_at_the_next_start(monkeypatch):
    ext, at, raw, _ = _run(monkeypatch, _answer)
    sections, _ = pipeline.resolve(raw, ext, Locator(ext.text))
    starts = [ext.lines[at[k]].start for k in NAMES]
    assert [s["start"] for s in sections] == starts
    assert all(not ({"start_marker_fuzzy", "start_marker_not_found", "title_not_in_text"} & set(s["flags"]))
               for s in sections)
    for a, b in zip(sections, sections[1:], strict=False):
        assert a["end"] == b["start"] - 1  # the newline before the next section's first line
        assert a["end_marker"] == "" and a["model_end"] is None
    assert sections[-1]["end"] == len(ext.text)


def test_a_heading_never_takes_a_line_another_section_starts_on(monkeypatch):
    # The model lists the wrapped heading's second line as a section of its own.
    def answer(at):
        res = _answer(at)
        res.sections.insert(4, TextSection(start_line=at["wrapped"] + 1, level=3, title_from_text=True, title=""))
        return res

    _, at, raw, _ = _run(monkeypatch, answer)
    assert (raw[3].title, raw[4].title) == ("A heading that is long enough that it wraps", "onto a second line")


def test_the_prompt_asks_for_no_copied_text(monkeypatch):
    _, _, _, seen = _run(monkeypatch, _answer)
    assert seen[0]["system"] == TEXT_SYSTEM
    for gone in ("start_marker", "end_marker", "- number:", "Copy markers"):
        assert gone not in TEXT_SYSTEM
    fields = [ln.split(":")[0] for ln in TEXT_SYSTEM.split("For each section return:\n")[1].split("\n\n")[0].splitlines()]
    assert fields == ["- start_line", "- level", "- title_from_text", "- title"]
    assert set(TextSection.model_json_schema()["properties"]) == {"start_line", "level", "title_from_text", "title"}
