"""Experimental `heading_guidance`: appended to Quick check's and Standard's instructions; without it the
instructions are byte-identical to the shipped ones. Fake model only."""

from __future__ import annotations

import asyncio

from section_anything.config import Settings
from section_anything.extract import Extraction, Line, Page
from section_anything.llm import Usage
from section_anything.strategies import llm_text
from section_anything.strategies.base import Context
from section_anything.strategies.llm_text import (
    GUIDANCE_HEADER,
    REVIEW_SYSTEM,
    TEXT_SYSTEM,
    LlmReviewStrategy,
    LlmTextStrategy,
    ReviewResult,
    TextResult,
)

BODY = "Ordinary body text runs on for a while in the regular face at the body size of the page."


def _doc() -> Extraction:
    rows = []
    for n in range(1, 4):
        rows += [(f"{n} Topic number {n}", 12.0, True), (BODY, 10.0, False), (BODY, 10.0, False)]
    lines, cursor = [], 0
    for i, (text, size, bold) in enumerate(rows):
        y0 = 700 - 20 * i
        lines.append(Line(i=i, page=1, text=text, x0=72, y0=y0, x1=72 + 0.5 * size * len(text), y1=y0 + size,
                          size=size, bold=bold, start=cursor, end=cursor + len(text)))
        cursor += len(text) + 1
    page = Page(n=1, width=612, height=792, origin_x=0, origin_y=0, rotation=0, has_text=True)
    return Extraction([page], lines, "\n".join(r[0] for r in rows))


def _systems(monkeypatch, settings: Settings) -> list[str]:
    seen: list[str] = []

    async def fake(**kw):
        seen.append(kw["system"])
        return TextResult(sections=[]) if kw["schema"] is TextResult else ReviewResult(items=[])

    monkeypatch.setattr(llm_text, "structured", fake)
    for strategy in (LlmTextStrategy(), LlmReviewStrategy()):
        ctx = Context(model="gpt-6-luna", usage=Usage(), cost_cap_usd=1.0, settings=settings)
        asyncio.run(strategy.run(_doc(), ctx))
    return seen


def test_no_guidance_keeps_the_instructions(monkeypatch):
    seen = _systems(monkeypatch, Settings(coverage_retry=False))
    assert seen == [TEXT_SYSTEM, REVIEW_SYSTEM]
    assert seen[0] is TEXT_SYSTEM and seen[1] is REVIEW_SYSTEM
    assert _systems(monkeypatch, Settings(coverage_retry=False, heading_guidance="  \n ")) == [TEXT_SYSTEM, REVIEW_SYSTEM]


def test_guidance_is_appended_to_both_modes(monkeypatch):
    sheet = "Numbered clauses such as 4.2 are headings at level 2."
    seen = _systems(monkeypatch, Settings(coverage_retry=False, heading_guidance=sheet + "\n"))
    assert seen == [TEXT_SYSTEM + GUIDANCE_HEADER + sheet, REVIEW_SYSTEM + GUIDANCE_HEADER + sheet]


def test_guidance_from_the_environment(monkeypatch):
    monkeypatch.setenv("SECTIONANY_HEADING_GUIDANCE", "Rule one.")
    assert Settings().heading_guidance == "Rule one."


def test_estimates_count_the_guidance():
    sheet = "Numbered clauses such as 4.2 are headings at level 2. " * 40
    for strategy in (LlmTextStrategy(), LlmReviewStrategy()):
        plain = strategy.estimate(_doc(), "gpt-6-luna", Settings())
        assert strategy.estimate(_doc(), "gpt-6-luna", Settings(heading_guidance="  ")) == plain
        guided = strategy.estimate(_doc(), "gpt-6-luna", Settings(heading_guidance=sheet))
        extra = int((len(GUIDANCE_HEADER) + len(sheet.strip())) / 4) * plain.calls
        assert guided.input_tokens - plain.input_tokens >= extra - plain.calls
