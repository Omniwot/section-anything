"""Cost caps: refusals happen before anything is read or sent, and calls stay within the cap."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import section_anything
import section_anything.api as api
import section_anything.llm as llm
from section_anything import ConfigError, CostCapExceeded, Settings, UnpricedModelError


@pytest.fixture
def no_extraction(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("the PDF was read")

    monkeypatch.setattr(api, "extract_pdf", refuse)


def test_unpriced_cloud_model_is_refused_before_reading(paper_pdf, no_extraction):
    with pytest.raises(UnpricedModelError, match="no price for model 'no-such-model'"):
        section_anything.section(paper_pdf, "quick", model="no-such-model", api_key="sk-test")
    assert issubclass(UnpricedModelError, ValueError)


def test_unpriced_model_from_environment_is_refused(paper_pdf, no_extraction, monkeypatch):
    monkeypatch.setenv("SECTIONANY_STANDARD_MODEL", "mystery-model")
    with pytest.raises(UnpricedModelError):
        section_anything.section(paper_pdf, "standard", api_key="sk-test")


def test_cloud_mode_without_key_is_refused_before_reading(paper_pdf, no_extraction):
    with pytest.raises(ConfigError, match="needs an API key"):
        section_anything.section(paper_pdf, "quick")


def test_estimate_over_cap_fails_without_any_call(paper_pdf):
    with pytest.raises(CostCapExceeded, match="per-document cap"):
        section_anything.section(paper_pdf, "standard", api_key="sk-test", max_usd=0.000001, over_budget="fail")


def test_passed_price_is_used_and_capped(paper_pdf):
    # An unknown model with a price passed in is accepted, then held to the cap.
    with pytest.raises(CostCapExceeded):
        section_anything.section(paper_pdf, "quick", model="my-model", api_key="sk-test", max_usd=0.0001,
                                 prices={"my-model": {"input": 1000.0, "output": 1000.0}}, over_budget="fail")


def test_estimate_over_cap_downgrades_to_free(paper_pdf):
    tree = section_anything.section(paper_pdf, "standard", api_key="sk-test", max_usd=0.000001)
    assert tree.mode == "free" and tree.model is None
    assert [d.split(":")[0] for d in tree.downgraded] == ["standard", "quick"]
    assert tree.usage["calls"] == 0 and tree.cost_usd == 0.0
    assert len(tree.sections) == 5


class Out(BaseModel):
    answer: str


class FakeClient:
    """Stands in for AsyncOpenAI: records the request, answers with fixed usage."""

    def __init__(self, prompt_tokens: int = 1000, completion_tokens: int = 1000) -> None:
        self.requests: list[dict] = []
        self.usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                                     prompt_tokens_details=None, completion_tokens_details=None)
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))
        self.closed = False

    async def _parse(self, **kwargs):
        self.requests.append(kwargs)
        msg = SimpleNamespace(refusal=None, parsed=Out(answer="ok"))
        return SimpleNamespace(usage=self.usage, choices=[SimpleNamespace(message=msg, finish_reason="stop")])

    async def close(self) -> None:
        self.closed = True


def _call(settings: Settings, usage: llm.Usage, cap: float, user: str = "doc"):
    return asyncio.run(llm.structured(model="m", system="s", user=user, schema=Out, usage=usage,
                                      cost_cap_usd=cap, step="t", settings=settings))


def test_call_output_is_limited_to_the_remaining_budget(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda model, s: fake)
    s = Settings(api_key="k", prices={"m": {"input": 1.0, "output": 100.0}})
    usage = llm.Usage()
    assert _call(s, usage, cap=0.5).answer == "ok"
    # $0.50 left, output at $100 per 1M tokens: at most ~5,000 output tokens, not the default 32,000.
    assert 4_900 <= fake.requests[0]["max_completion_tokens"] <= 5_000
    assert fake.closed
    assert usage.calls == 1 and usage.cost_usd == pytest.approx((1000 * 1.0 + 1000 * 100.0) / 1e6)


def test_call_is_refused_when_the_budget_cannot_pay_for_an_answer(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda model, s: fake)
    s = Settings(api_key="k", prices={"m": {"input": 1.0, "output": 1000.0}})
    with pytest.raises(CostCapExceeded):
        _call(s, llm.Usage(), cap=0.1)  # 100 output tokens affordable: below the minimum
    assert fake.requests == []


def test_spent_budget_stops_the_next_call(monkeypatch):
    fake = FakeClient(prompt_tokens=100_000, completion_tokens=10_000)
    monkeypatch.setattr(llm, "_client", lambda model, s: fake)
    s = Settings(api_key="k", prices={"m": {"input": 2.0, "output": 10.0}})
    usage = llm.Usage()
    _call(s, usage, cap=0.30)  # spends $0.30
    with pytest.raises(CostCapExceeded):
        _call(s, usage, cap=0.30)
    assert len(fake.requests) == 1


def test_local_models_are_free_and_never_capped(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda model, s: fake)
    usage = llm.Usage()
    out = asyncio.run(llm.structured(model="ollama/qwen3:4b", system="s", user="u", schema=Out, usage=usage,
                                     cost_cap_usd=0.0, step="t", settings=Settings()))
    assert out.answer == "ok" and usage.cost_usd == 0.0
    assert fake.requests[0]["model"] == "qwen3:4b" and fake.requests[0]["max_tokens"] == 32_000


def test_failed_calls_never_echo_response_text(monkeypatch, caplog):
    class Leaky(FakeClient):
        async def _parse(self, **kwargs):
            raise ValueError("SECRET DOCUMENT TEXT")

    leaky = Leaky()
    leaky.chat = SimpleNamespace(completions=SimpleNamespace(parse=leaky._parse))
    monkeypatch.setattr(llm, "_client", lambda model, s: leaky)
    records: list[dict] = []

    async def sink(entry):
        records.append(entry)

    usage = llm.Usage(sink=sink)
    with pytest.raises(section_anything.LlmCallFailed) as err:
        _call(Settings(api_key="k"), usage, cap=1.0)
    assert "SECRET" not in str(err.value)
    assert all("SECRET" not in (r["error"] or "") for r in records) and len(records) == 2
    assert "SECRET" not in caplog.text
    assert all(r["prompt_text"] is None for r in records)  # prompts are stored only on request
