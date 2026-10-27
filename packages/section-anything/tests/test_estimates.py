"""Up-front cost estimates by provider: OpenAI-compatible models keep 3.6 characters per token and no
thinking allowance; Claude models are counted at 1.5 characters per token (Claude's token counter gave
1.52 to 2.76 on the 200 READoc development prompts) plus thinking at the effort Claude is sent, within
each call's output limit. No network."""

from __future__ import annotations

import pytest

import section_anything
import section_anything.llm as llm
from section_anything import CostCapExceeded, Settings
from section_anything.config import DEFAULT_PRICES
from section_anything.extract import Extraction, Line, Page
from section_anything.pipeline import estimates
from section_anything.strategies.llm_text import LlmReviewStrategy, LlmTextStrategy, _tagged, _windows

HAIKU, SONNET, LUNA = "claude-haiku-5-5", "claude-sonnet-5-5", "gpt-6-luna"
TEXT = "Ordinary body text runs on for a while in the regular face at the body size of the page."


def _ext(n_lines: int, heading_every: int = 20, text: str = TEXT) -> Extraction:
    """`n_lines` lines, 40 to a page, with a bold numbered heading every `heading_every` lines."""
    lines, cursor = [], 0
    for i in range(n_lines):
        heading = i % heading_every == 0
        t = f"{i // heading_every + 1} Heading number {i // heading_every + 1}" if heading else text
        page, k = i // 40 + 1, i % 40
        lines.append(Line(i=i, page=page, text=t, x0=72, y0=700 - k * 15, x1=500, y1=710 - k * 15,
                          size=14.0 if heading else 10.0, bold=heading, start=cursor, end=cursor + len(t)))
        cursor += len(t) + 1
    pages = [Page(n=p, width=612, height=792, origin_x=0, origin_y=0, rotation=0, has_text=True)
             for p in range(1, lines[-1].page + 1)]
    return Extraction(pages, lines, "\n".join(ln.text for ln in lines))


def _old_text_estimate(ext: Extraction) -> tuple[int, int, int]:
    """The 0.1.3 formula, kept here to show OpenAI estimates did not move."""
    rows = _tagged(ext)
    n = len(_windows(ext, rows, LlmTextStrategy.window_chars))
    chars = sum(len(r) + 1 for r in rows)
    return int(chars / 3.6) + n * 900, int(len(ext.lines) / 18) * 90, n


def test_profiles_follow_the_provider():
    assert llm.token_profile(LUNA) == llm.TokenProfile(3.6, 0.0)
    assert llm.token_profile() == llm.TokenProfile(3.6, 0.0)  # no model: OpenAI's
    assert llm.token_profile("ollama/qwen3:8b") == llm.TokenProfile(3.6, 0.0)
    assert llm.token_profile(HAIKU) == llm.TokenProfile(1.5, 0.5)  # strategies' "low" is sent as "medium"
    assert llm.token_profile(SONNET, effort="medium") == llm.TokenProfile(1.5, 0.5)
    assert llm.token_profile(SONNET, effort="high").thinking_share == 1.0
    assert llm.token_profile(SONNET, effort=None).thinking_share == 1.0  # no effort sent: Sonnet's default, high
    # The provider setting wins over the model id, as it does for the requests.
    assert llm.token_profile(HAIKU, Settings(provider="openai")) == llm.TokenProfile(3.6, 0.0)
    assert llm.token_profile("my-claude", Settings(provider="anthropic")) == llm.TokenProfile(1.5, 0.5)


def test_openai_estimates_are_unchanged():
    for ext in (_ext(300), _ext(9_000)):
        old_in, old_out, old_n = _old_text_estimate(ext)
        for est in (LlmTextStrategy().estimate(ext), LlmTextStrategy().estimate(ext, LUNA)):
            assert (est.input_tokens, est.output_tokens, est.calls) == (old_in, old_out, old_n)
        rows = LlmReviewStrategy()._rows(ext)
        n = max(1, -(-len(rows) // LlmReviewStrategy.batch))
        quick = LlmReviewStrategy().estimate(ext, LUNA)
        assert (quick.input_tokens, quick.output_tokens, quick.calls) == (
            int(sum(len(r) for _, r in rows) / 3.6) + n * 700, len(rows) * 30 + n * 800, n)


def test_claude_counts_more_input_and_adds_thinking():
    ext = _ext(300)
    rows = _tagged(ext)
    chars = sum(len(r) + 1 for r in rows)
    est = LlmTextStrategy().estimate(ext, HAIKU)
    assert est.calls == 1
    assert est.input_tokens == int(chars / 1.5) + 2_160  # 900 tokens a call at 3.6 is 2,160 at 1.5
    answer = int(len(ext.lines) / 18) * 90
    assert est.output_tokens == answer + int(0.5 * est.input_tokens)
    luna = LlmTextStrategy().estimate(ext, LUNA)
    assert est.input_tokens > 2 * luna.input_tokens and est.output_tokens > luna.output_tokens


def test_thinking_allowance_stops_at_each_calls_output_limit():
    ext = _ext(1_000)  # one window of about 91,000 tagged characters: 0.5 x 62,000 prompt tokens > 32,000
    est = LlmTextStrategy().estimate(ext, HAIKU)
    assert est.calls == 1 and est.input_tokens > 60_000 and est.output_tokens == llm.MAX_OUTPUT_TOKENS
    est = LlmTextStrategy().estimate(_ext(2_000), SONNET)
    assert est.calls == 2 and est.output_tokens == 2 * llm.MAX_OUTPUT_TOKENS


def test_measured_paper_is_not_underestimated():
    # READoc arXiv 0905.3502 (F021): 67,579 characters of tagged text, 1,665 lines, one window. Claude
    # Haiku 5.5 at "medium" used 38,019 prompt tokens and 19,788 output tokens ($0.0137); the old
    # estimate assumed 19,671 prompt tokens and 8,280 output tokens.
    prof = llm.token_profile(HAIKU)
    inp = prof.tokens(67_579) + prof.per_call(900)
    out = prof.output(int(1_665 / 18) * 90, inp, 1)
    assert inp >= 38_019 and out >= 19_788
    assert DEFAULT_PRICES[HAIKU].estimate(inp, out, 1) >= 0.0137


def test_claude_estimate_drives_the_per_document_cap(paper_pdf, monkeypatch):
    # A cap above the OpenAI-style estimate but below Claude's: the Claude run must not start.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    from section_anything import api

    ext = api.extract_pdf(paper_pdf, settings=Settings())
    price = DEFAULT_PRICES[SONNET]
    old, new = LlmTextStrategy().estimate(ext), LlmTextStrategy().estimate(ext, SONNET)
    old_usd = price.estimate(old.input_tokens, old.output_tokens, old.calls)
    new_usd = price.estimate(new.input_tokens, new.output_tokens, new.calls)
    cap = (old_usd + new_usd) / 2
    assert old_usd < cap < new_usd
    with pytest.raises(CostCapExceeded, match="per-document cap"):
        section_anything.section(paper_pdf, "standard", model=SONNET, max_usd=cap, over_budget="fail")


def test_estimates_table_prices_each_model_with_its_own_profile():
    ext = _ext(300)
    rows = {r["strategy"]: r for r in estimates(ext, {LUNA: DEFAULT_PRICES[LUNA], HAIKU: DEFAULT_PRICES[HAIKU]}, 1.0)}
    text = rows["llm_text"]
    luna, haiku = LlmTextStrategy().estimate(ext, LUNA), LlmTextStrategy().estimate(ext, HAIKU)
    assert (text["input_tokens"], text["output_tokens"]) == (luna.input_tokens, luna.output_tokens)
    assert text["cost_usd"][LUNA] == round((luna.input_tokens * 0.10 + luna.output_tokens * 0.50) / 1e6, 4)
    assert text["cost_usd"][HAIKU] == round((haiku.input_tokens * 0.10 + haiku.output_tokens * 0.50) / 1e6, 4)
    assert rows["rules"]["cost_usd"][HAIKU] == 0.0
