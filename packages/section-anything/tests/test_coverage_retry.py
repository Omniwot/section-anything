"""Standard's coverage check: a window whose answer leaves many heading-like lines unlisted is read
once more, and the answer that lists more of them is kept (research finding F043). Fake model only."""

from __future__ import annotations

import asyncio
import re

from section_anything.config import Settings
from section_anything.errors import LlmCallFailed
from section_anything.extract import Extraction, Line, Page
from section_anything.llm import Usage
from section_anything.strategies import llm_text
from section_anything.strategies.base import Context
from section_anything.strategies.llm_text import COVERAGE_NOTE, LlmTextStrategy, TextResult, TextSection

BODY = "Ordinary body text runs on for a while in the regular face at the body size of the page."
HEADINGS = 30


def _manual() -> Extraction:
    """One long page of numbered headings (12 pt bold), each followed by two body lines (10 pt)."""
    rows = []
    for n in range(1, HEADINGS + 1):
        rows += [(f"{n} Topic number {n}", 12.0, True), (BODY, 10.0, False), (BODY, 10.0, False)]
    lines, cursor = [], 0
    for i, (text, size, bold) in enumerate(rows):
        y0 = 1900 - 20 * i
        lines.append(Line(i=i, page=1, text=text, x0=72, y0=y0, x1=72 + 0.5 * size * len(text), y1=y0 + size,
                          size=size, bold=bold, start=cursor, end=cursor + len(text)))
        cursor += len(text) + 1
    page = Page(n=1, width=612, height=1950, origin_x=0, origin_y=0, rotation=0, has_text=True)
    return Extraction([page], lines, "\n".join(r[0] for r in rows))


def _sections(user: str, limit: int | None = None) -> TextResult:
    """The headings shown in the slice, as a model would list them; `limit` stops early."""
    found = [(int(m.group(1)), m.group(2), m.group(3)) for m in re.finditer(r"^(\d+)\| ⟨H\+2⟩⟨B⟩ (\d+) (.*)$", user, re.M)]
    return TextResult(sections=[
        TextSection(start_line=i, number=num, title=title, title_from_text=True, level=1,
                    start_marker=f"{num} {title}", end_marker="")
        for i, num, title in found[:limit]
    ])


class Fake:
    """Answers the first reading of a window with `first` headings and a re-reading with `again`."""

    def __init__(self, first: int | None, again: int | None = None, fail_again: bool = False) -> None:
        self.first, self.again, self.fail_again = first, again, fail_again
        self.calls: list[dict] = []

    async def __call__(self, **kw) -> TextResult:
        self.calls.append(kw)
        # Counted as `structured` counts a call: in the total and under its step.
        kw["usage"].cost_usd += 0.001
        kw["usage"].by_step[kw["step"]] = kw["usage"].by_step.get(kw["step"], 0.0) + 0.001
        if kw["step"].startswith("re-read"):
            if self.fail_again:
                raise LlmCallFailed("model call failed after 2 attempts: APIConnectionError")
            return _sections(kw["user"], self.again)
        return _sections(kw["user"], self.first)


def _run(monkeypatch, fake: Fake, *, settings: Settings | None = None, usage: Usage | None = None,
         model: str = "fake", cap: float = 1.0):
    monkeypatch.setattr(llm_text, "structured", fake)
    ctx = Context(model=model, usage=usage or Usage(), cost_cap_usd=cap, settings=settings)
    return asyncio.run(LlmTextStrategy().run(_manual(), ctx)), ctx.usage


def test_a_complete_answer_is_not_read_again(monkeypatch):
    fake = Fake(first=None)
    found, usage = _run(monkeypatch, fake)
    assert len(found) == HEADINGS and len(fake.calls) == 1
    assert "coverage_retries" not in usage.summary()


def test_an_answer_that_stops_early_is_read_again_and_the_fuller_answer_kept(monkeypatch):
    fake = Fake(first=3, again=None)
    found, usage = _run(monkeypatch, fake)
    assert [s.number for s in found] == [str(n) for n in range(1, HEADINGS + 1)]
    first, again = fake.calls
    # Same prompt with a note at the end: the provider's prompt cache still covers the slice.
    assert again["user"] == first["user"] + COVERAGE_NOTE.format(a=0, b=3 * HEADINGS - 1)
    assert again["step"] == "re-read window 1/1 (coverage)"
    (note,) = usage.summary()["coverage_retries"]
    assert note["kept"] == "retry" and note["unlisted"] == HEADINGS - 3 and note["unlisted_retry"] == 0
    assert note["lines"] == [0, 3 * HEADINGS - 1] and note["cost_usd"] == 0.001


def test_an_empty_answer_is_read_again(monkeypatch):
    fake = Fake(first=0, again=None)
    found, usage = _run(monkeypatch, fake)
    assert len(found) == HEADINGS and usage.coverage_retries[0]["kept"] == "retry"


def test_a_retry_that_lists_no_more_is_not_kept(monkeypatch):
    fake = Fake(first=3, again=2)
    found, usage = _run(monkeypatch, fake)
    assert len(found) == 3 and len(fake.calls) == 2
    assert usage.coverage_retries[0]["kept"] == "first"


def test_a_failed_retry_keeps_the_first_answer(monkeypatch):
    fake = Fake(first=3, fail_again=True)
    found, usage = _run(monkeypatch, fake)
    assert len(found) == 3
    assert usage.coverage_retries[0]["skipped"] == "LlmCallFailed" and usage.coverage_retries[0]["kept"] == "first"


def test_no_retry_past_the_cost_cap(monkeypatch):
    # gpt-6-luna is priced, so the retry's up-front cost must fit in what is left of the cap.
    fake = Fake(first=3, again=None)
    found, usage = _run(monkeypatch, fake, model="gpt-6-luna", cap=0.0012, settings=Settings(api_key="sk-test"))
    assert len(found) == 3 and len(fake.calls) == 1
    assert usage.coverage_retries[0]["skipped"] == "cost cap"


def test_retry_within_the_cap(monkeypatch):
    fake = Fake(first=3, again=None)
    found, usage = _run(monkeypatch, fake, model="gpt-6-luna", cap=0.5, settings=Settings(api_key="sk-test"))
    assert len(found) == HEADINGS and len(fake.calls) == 2


def test_the_check_can_be_turned_off(monkeypatch):
    fake = Fake(first=3, again=None)
    found, usage = _run(monkeypatch, fake, settings=Settings(coverage_retry=False))
    assert len(found) == 3 and len(fake.calls) == 1 and not usage.coverage_retries


def test_a_few_unlisted_lines_are_not_enough(monkeypatch):
    # 22 of 30 listed: 8 left out is under the 10-line minimum.
    fake = Fake(first=22, again=None)
    found, _usage = _run(monkeypatch, fake)
    assert len(found) == 22 and len(fake.calls) == 1
