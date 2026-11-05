"""Strong Free headings a model left out are put back, or asked about once (research finding F059).
Fake model only."""

from __future__ import annotations

import asyncio
import re

from section_anything import keep, pipeline
from section_anything.config import Settings
from section_anything.errors import LlmCallFailed
from section_anything.extract import Extraction, Line, Page
from section_anything.llm import Usage
from section_anything.strategies import llm_text
from section_anything.strategies.llm_text import ReviewItem, ReviewResult

PAGES, PER_PAGE = 3, 4
SKIPPED = "6"  # the heading the fake model leaves out


def _doc() -> Extraction:
    """Numbered headings (12 pt bold) on three pages, each followed by two body lines (10 pt)."""
    lines, pages, cursor, n = [], [], 0, 0
    for p in range(1, PAGES + 1):
        pages.append(Page(n=p, width=612, height=792, origin_x=0, origin_y=0, rotation=0, has_text=True))
        rows = []
        for _ in range(PER_PAGE):
            n += 1
            rows += [(f"{n} Topic number {n}", 12.0, True),
                     (f"Body text about topic {n} runs on in the regular face for a while here.", 10.0, False),
                     (f"More plain text on topic {n}, set at the body size of the page, line two.", 10.0, False)]
        for k, (text, size, bold) in enumerate(rows):
            y0 = 740 - 22 * k - 5 * p
            lines.append(Line(i=len(lines), page=p, text=text, x0=72, y0=y0, x1=72 + 0.5 * size * len(text), y1=y0 + size,
                              size=size, bold=bold, start=cursor, end=cursor + len(text)))
            cursor += len(text) + 1
    return Extraction(pages, lines, "\n".join(ln.text for ln in lines))


async def _review(**kw) -> ReviewResult:
    """Keeps every numbered candidate but SKIPPED, at level 1."""
    kw["usage"].cost_usd += 0.001
    found = re.findall(r"^(\d+)\| p\d+ \S+ (\d+) (.*?)  ⟶", kw["user"], re.M)
    return ReviewResult(items=[ReviewItem(id=int(i), is_heading=num != SKIPPED, level=1, number=num, title=title)
                               for i, num, title in found])


class Ask:
    def __init__(self, keep_it: bool | None, fail: bool = False) -> None:
        self.keep_it, self.fail, self.calls = keep_it, fail, []

    async def __call__(self, **kw) -> keep.AskResult:
        self.calls.append(kw)
        if self.fail:
            raise LlmCallFailed("model call failed after 2 attempts: APIConnectionError")
        ids = [int(i) for i in re.findall(r"^(\d+)\| p", kw["user"], re.M)]
        return keep.AskResult(items=[keep.AskItem(id=i, is_heading=bool(self.keep_it), level=2, reason="a numbered step")
                                     for i in ids] if self.keep_it is not None else [])


def _run(monkeypatch, how: str, ask: Ask | None = None):
    monkeypatch.setattr(llm_text, "structured", _review)
    if ask is not None:
        monkeypatch.setattr(keep, "structured", ask)
    usage = Usage()
    _raw, sections, _m = asyncio.run(pipeline.run(_doc(), "llm_review", "fake", 1.0, usage=usage,
                                                  settings=Settings(keep_strong=how)))
    return sections, usage


def _numbers(sections: list[dict]) -> list[str]:
    return [s["number"] for s in sections if "front_matter" not in s["flags"]]


def test_off_leaves_the_answer_as_it_is(monkeypatch):
    sections, usage = _run(monkeypatch, "off")
    assert SKIPPED not in _numbers(sections)
    assert "kept_strong" not in usage.summary()


def test_restore_puts_a_left_out_strong_heading_back_at_the_models_level(monkeypatch):
    sections, usage = _run(monkeypatch, "restore")
    assert _numbers(sections) == [str(n) for n in range(1, PAGES * PER_PAGE + 1)]
    back = next(s for s in sections if s["number"] == SKIPPED)
    assert keep.FLAG in back["flags"] and back["level"] == 1
    note = usage.summary()["kept_strong"]
    assert note["how"] == "restore" and note["left_out"] == 1 and [r["title"] for r in note["restored"]] == [
        "6 Topic number 6"]


def test_ask_keeps_what_the_model_keeps_at_its_level(monkeypatch):
    ask = Ask(keep_it=True)
    sections, usage = _run(monkeypatch, "ask", ask)
    assert len(ask.calls) == 1 and "6 Topic number 6" in ask.calls[0]["user"]
    assert next(s for s in sections if s["number"] == SKIPPED)["level"] == 2
    assert usage.kept_strong["restored"][0]["reason"] == "a numbered step"


def test_ask_drops_what_the_model_rejects_and_records_why(monkeypatch):
    sections, usage = _run(monkeypatch, "ask", Ask(keep_it=False))
    assert SKIPPED not in _numbers(sections)
    assert usage.kept_strong["rejected"] == [{"line": 15, "page": 2, "title": "6 Topic number 6", "reason": "a numbered step"}]


def test_a_failed_or_empty_ask_puts_the_heading_back(monkeypatch):
    for ask in (Ask(keep_it=None, fail=True), Ask(keep_it=None)):
        sections, usage = _run(monkeypatch, "ask", ask)
        assert SKIPPED in _numbers(sections)
    assert usage.kept_strong["restored"][0]["level"] == 1


def test_nothing_left_out_means_no_ask_call(monkeypatch):
    async def everything(**kw) -> ReviewResult:
        found = re.findall(r"^(\d+)\| p\d+ \S+ (\d+) (.*?)  ⟶", kw["user"], re.M)
        return ReviewResult(items=[ReviewItem(id=int(i), is_heading=True, level=1, number=num, title=t) for i, num, t in found])

    monkeypatch.setattr(llm_text, "structured", everything)
    ask = Ask(keep_it=True)
    monkeypatch.setattr(keep, "structured", ask)
    usage = Usage()
    asyncio.run(pipeline.run(_doc(), "llm_review", "fake", 1.0, usage=usage, settings=Settings(keep_strong="ask")))
    assert not ask.calls and usage.kept_strong == {"how": "ask", "left_out": 0, "restored": [], "rejected": []}


def test_level_map_follows_the_models_levels_and_extends_past_them():
    free = [{"first_line": 1, "level": 1, "flags": []}, {"first_line": 5, "level": 2, "flags": []},
            {"first_line": 9, "level": 3, "flags": []}]
    model = [{"first_line": 1, "level": 2, "flags": []}, {"first_line": 6, "level": 3, "flags": []}]
    assert keep.level_map(free, model) == {1: 2, 2: 3, 3: 4}


def test_ask_puts_a_heading_the_outline_lists_back_without_asking(monkeypatch):
    real = keep.evidence

    def listed(free, ext):  # the bookmarks list heading 6
        return [dict(ev, outline=1.0) if ev is not None and s["number"] == SKIPPED else ev
                for s, ev in zip(free, real(free, ext), strict=True)]

    monkeypatch.setattr(keep, "evidence", listed)
    ask = Ask(keep_it=False)
    sections, usage = _run(monkeypatch, "ask", ask)
    assert SKIPPED in _numbers(sections) and not ask.calls
    assert usage.kept_strong["restored"][0]["listed"] is True


def test_the_contents_check_summary_survives_a_heading_put_back(monkeypatch):
    monkeypatch.setattr(llm_text, "structured", _review)
    _raw, sections, metrics = asyncio.run(pipeline.run(
        _doc(), "llm_review", "fake", 1.0, usage=Usage(), settings=Settings(keep_strong="restore", contents_check=["quick"])))
    assert SKIPPED in _numbers(sections)
    assert "contents_check" in metrics and "possible_misses" in metrics


def test_ask_is_the_default(monkeypatch):
    # Default since the held-out READoc check of research finding F064 (Quick +1.76 TEDS, CI +1.36 to +2.18).
    assert Settings().keep_strong == "ask"
    monkeypatch.setattr(llm_text, "structured", _review)
    ask = Ask(keep_it=True)
    monkeypatch.setattr(keep, "structured", ask)
    _raw, sections, _m = asyncio.run(pipeline.run(_doc(), "llm_review", "fake", 1.0, usage=Usage(), settings=Settings()))
    assert SKIPPED in _numbers(sections) and len(ask.calls) == 1


def test_the_default_can_be_turned_off_by_environment(monkeypatch):
    monkeypatch.setenv("SECTIONANY_KEEP_STRONG", "off")
    assert Settings().keep_strong == "off"
