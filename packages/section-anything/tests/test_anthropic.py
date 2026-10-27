"""Claude models on Anthropic's own API: provider selection, which key goes where, the request
shape, refusals, cut-off answers, cost accounting and the optional extra. No network: the real
`anthropic` client runs over a mocked HTTP transport that answers with recorded-style SSE events."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import pytest
from pydantic import BaseModel

import section_anything
import section_anything.api as api
import section_anything.llm as llm
from section_anything import ConfigError, LlmCallFailed, Settings, UnpricedModelError
from section_anything.config import ANTHROPIC_BASE_URL, DEFAULT_PRICES, OPENAI_BASE_URL, Price

try:
    import anthropic
    import httpx2
except ImportError:  # tests marked needs_sdk skip; the others run without the extra
    anthropic = httpx2 = None
needs_sdk = pytest.mark.skipif(anthropic is None, reason="needs the anthropic extra")

HAIKU = "claude-haiku-5-5"


class Out(BaseModel):
    answer: str


def sse(text: str, *, stop_reason: str = "end_turn", input_tokens: int = 1000, output_tokens: int = 200,
        cache_read: int = 0, cache_write: int = 0, model: str = HAIKU) -> bytes:
    """A streamed Messages API answer, as the API sends it."""
    usage = {"input_tokens": input_tokens, "output_tokens": 1, "cache_read_input_tokens": cache_read,
             "cache_creation_input_tokens": cache_write}
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_test", "type": "message", "role": "assistant", "content": [], "model": model,
            "stop_reason": None, "stop_sequence": None, "usage": usage}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("ping", {"type": "ping"}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                           "usage": {"output_tokens": output_tokens}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


class Api:
    """Stands in for api.anthropic.com: records each request and replays the queued answers."""

    def __init__(self, *answers: bytes) -> None:
        self.answers = list(answers)
        self.requests: list[httpx2.Request] = []
        self.client_kwargs: list[dict] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        body = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return httpx2.Response(200, headers={"content-type": "text/event-stream", "request-id": "req_test"},
                               content=body)

    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]


@pytest.fixture
def claude_api(monkeypatch):
    """Install a fake Anthropic API; returns a function that queues its answers."""
    real = anthropic._client.AsyncAnthropic

    def install(*answers: bytes) -> Api:
        fake = Api(*answers)

        def make(**kwargs):
            fake.client_kwargs.append(kwargs)
            return real(**kwargs, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(fake.handler)))

        monkeypatch.setattr(anthropic, "AsyncAnthropic", make)
        return fake

    return install


def _call(settings: Settings, usage: llm.Usage | None = None, *, model: str = HAIKU, cap: float = 1.0,
          effort: str | None = "low"):
    return asyncio.run(llm.structured(model=model, system="sys", user="doc", schema=Out, usage=usage or llm.Usage(),
                                      cost_cap_usd=cap, step="t", effort=effort, settings=settings))


# ── Provider selection ──────────────────────────────────────────────────────


def test_provider_follows_the_model_unless_set(monkeypatch):
    s = Settings()
    assert s.provider is None
    assert s.provider_for("gpt-6-luna") == "openai" and s.provider_for(HAIKU) == "anthropic"
    assert Settings(provider="openai").provider_for(HAIKU) == "openai"  # e.g. an OpenAI-compatible gateway
    assert Settings(provider="anthropic").provider_for("my-claude-alias") == "anthropic"
    monkeypatch.setenv("SECTIONANY_PROVIDER", "Anthropic")
    assert Settings().provider == "anthropic"
    monkeypatch.setenv("SECTIONANY_PROVIDER", "")
    assert Settings().provider is None
    monkeypatch.setenv("SECTIONANY_PROVIDER", "gemini")
    with pytest.raises(ValueError):
        Settings()


def test_local_and_browser_models_never_go_to_anthropic():
    s = Settings(provider="anthropic")
    assert not llm._is_anthropic("ollama/qwen3:4b", s) and not llm._is_anthropic("browser/x", s)
    assert llm._is_anthropic(HAIKU, Settings())


def test_defaults_stay_openai():
    s = Settings()
    assert s.quick_model == s.standard_model == "gpt-6-luna" and s.base_url == OPENAI_BASE_URL
    assert s.base_url_for("gpt-6-luna") == OPENAI_BASE_URL
    assert s.base_url_for(HAIKU) == ANTHROPIC_BASE_URL


def test_provider_argument_reaches_settings(paper_pdf, monkeypatch):
    seen = {}

    def stop(mode, model, settings):
        seen["provider"] = settings.provider_for(model)
        raise ConfigError("stop")

    monkeypatch.setattr(api, "_require_price", stop)
    with pytest.raises(ConfigError):
        section_anything.section(paper_pdf, "quick", model=HAIKU, provider="openai", api_key="k")
    assert seen["provider"] == "openai"
    from section_anything.cli import build_parser

    assert build_parser().parse_args(["x.pdf", "--provider", "anthropic"]).provider == "anthropic"


# ── Keys ────────────────────────────────────────────────────────────────────


def test_key_precedence_for_claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    assert Settings().api_key_for(HAIKU).get_secret_value() == "sk-ant-env"
    monkeypatch.setenv("SECTIONANY_API_KEY", "sk-ant-sectionany")
    assert Settings().api_key_for(HAIKU).get_secret_value() == "sk-ant-sectionany"
    assert Settings(api_key="sk-ant-arg").api_key_for(HAIKU).get_secret_value() == "sk-ant-arg"


def test_keys_never_cross_providers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    assert Settings().api_key_for("gpt-6-luna").get_secret_value() == "sk-openai"
    assert Settings().api_key_for(HAIKU) is None  # OPENAI_API_KEY is never sent to Anthropic
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    assert Settings().api_key_for("gpt-6-luna") is None  # nor ANTHROPIC_API_KEY to OpenAI
    assert Settings().api_key is None


def test_provider_env_keys_stay_with_their_own_endpoint(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    relay = Settings(base_url="http://127.0.0.1:8788")
    assert relay.base_url_for(HAIKU) == "http://127.0.0.1:8788"
    assert relay.api_key_for(HAIKU) is None  # a relay or gateway gets only a key given for it
    assert Settings(base_url="http://127.0.0.1:8788", api_key="any").api_key_for(HAIKU).get_secret_value() == "any"


def test_a_plainly_foreign_key_is_refused_not_sent(monkeypatch):
    with pytest.raises(ConfigError, match="looks like an OpenAI key") as err:
        Settings(api_key="sk-proj-openai-secret").api_key_for(HAIKU)
    assert "openai-secret" not in str(err.value)
    with pytest.raises(ConfigError, match="looks like an Anthropic key") as err:
        Settings(api_key="sk-ant-secret").api_key_for("gpt-6-luna")
    assert "sk-ant-secret" not in str(err.value)
    # Behind a relay or gateway the key is whatever that endpoint expects.
    assert Settings(api_key="sk-local", base_url="http://127.0.0.1:8788").api_key_for(HAIKU) is not None


class Capture:
    seen: dict = {}

    def __init__(self, **kwargs):
        Capture.seen = kwargs


@needs_sdk
def test_client_gets_explicit_endpoint_key_and_no_retries(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://elsewhere.example.com")
    monkeypatch.setattr(anthropic, "AsyncAnthropic", Capture)
    llm._client(HAIKU, Settings(api_key="sk-ant-k"))
    assert Capture.seen == {"api_key": "sk-ant-k", "base_url": ANTHROPIC_BASE_URL, "timeout": 300.0,
                            "max_retries": 0}
    monkeypatch.setenv("SECTIONANY_BASE_URL", "http://127.0.0.1:8788")
    llm._client(HAIKU, Settings(api_key="relay"))
    assert Capture.seen["base_url"] == "http://127.0.0.1:8788"


@needs_sdk
def test_missing_claude_key_is_refused_before_reading(paper_pdf, monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("the PDF was read")

    monkeypatch.setattr(api, "extract_pdf", refuse)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    with pytest.raises(ConfigError, match="needs an Anthropic API key"):
        section_anything.section(paper_pdf, "standard", model=HAIKU)
    with pytest.raises(ConfigError, match="no API key for Claude"):
        llm._client(HAIKU, Settings())


# ── Optional extra ──────────────────────────────────────────────────────────


def test_missing_extra_is_a_clear_config_error(paper_pdf, monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)  # as if not installed

    def refuse(*_a, **_k):
        raise AssertionError("the PDF was read")

    monkeypatch.setattr(api, "extract_pdf", refuse)
    with pytest.raises(ConfigError, match=r"pip install 'section-anything\[anthropic\]'"):
        section_anything.section(paper_pdf, "quick", model=HAIKU, api_key="sk-ant-k")
    with pytest.raises(ConfigError, match=r"section-anything\[anthropic\]"):
        llm._client(HAIKU, Settings(api_key="sk-ant-k"))
    # OpenAI models do not need it.
    assert api._require_price("quick", "gpt-6-luna", Settings(api_key="k")) is not None


def test_importing_the_library_does_not_import_anthropic():
    code = "import sys, section_anything; section_anything.Settings; print(int('anthropic' in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "0"


# ── Request shape ───────────────────────────────────────────────────────────


@needs_sdk
def test_request_shape(claude_api):
    fake = claude_api(sse('{"answer": "ok"}'))
    out = _call(Settings(api_key="sk-ant-k"))
    assert out.answer == "ok"
    (req,) = fake.requests
    assert str(req.url) == "https://api.anthropic.com/v1/messages"
    assert "sk-ant-k" in (req.headers.get("authorization", "") + req.headers.get("x-api-key", ""))
    body = json.loads(req.content)
    assert body["model"] == HAIKU and body["stream"] is True
    assert body["system"] == "sys" and body["messages"] == [{"role": "user", "content": "doc"}]
    assert body["max_tokens"] == 32_000
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"] == {"type": "json_schema", "schema": anthropic.transform_schema(Out)}
    for absent in ("temperature", "top_p", "top_k", "thinking", "response_format", "reasoning_effort",
                   "max_completion_tokens"):
        assert absent not in body
    assert fake.client_kwargs[0]["max_retries"] == 0


@needs_sdk
def test_effort_mapping(claude_api):
    fake = claude_api(sse('{"answer": "ok"}'))
    _call(Settings(api_key="sk-ant-k"), effort=None)
    _call(Settings(api_key="sk-ant-k"), effort="none")
    _call(Settings(api_key="sk-ant-k"), effort="medium")
    efforts = [b["output_config"].get("effort") for b in fake.bodies()]
    assert efforts == [None, "low", "medium"]
    assert all("thinking" not in b for b in fake.bodies())


@needs_sdk
def test_output_is_limited_to_the_remaining_budget(claude_api):
    fake = claude_api(sse('{"answer": "ok"}'))
    s = Settings(api_key="sk-ant-k", prices={HAIKU: {"input": 1.0, "output": 100.0}})
    _call(s, cap=0.5)
    assert 4_900 <= fake.bodies()[0]["max_tokens"] <= 5_000


# ── Refusals and cut-off answers ────────────────────────────────────────────


def _records(usage_list: list[dict]):
    async def sink(entry):
        usage_list.append(entry)

    return sink


@needs_sdk
def test_refusal_is_retried_then_fails_and_is_still_counted(claude_api, caplog):
    fake = claude_api(sse("I can't help with that SECRET", stop_reason="refusal", output_tokens=20))
    records: list[dict] = []
    usage = llm.Usage(sink=_records(records))
    with pytest.raises(LlmCallFailed, match="model refused"):
        _call(Settings(api_key="sk-ant-k"), usage)
    assert len(fake.requests) == 2 and [r["status"] for r in records] == ["refused", "refused"]
    assert usage.calls == 2 and usage.cost_usd > 0  # refused answers are billed, so they count
    assert "SECRET" not in caplog.text and all("SECRET" not in (r["error"] or "") for r in records)
    assert all(r["response"] is None for r in records)  # nothing stored without store_prompts


@needs_sdk
def test_max_tokens_cut_off_is_a_clear_error_and_still_counted(claude_api):
    claude_api(sse('{"answer": "trunc', stop_reason="max_tokens", output_tokens=32_000))
    records: list[dict] = []
    usage = llm.Usage(sink=_records(records))
    with pytest.raises(LlmCallFailed, match="cut off at max_tokens=32000"):
        _call(Settings(api_key="sk-ant-k"), usage)
    assert [r["status"] for r in records] == ["invalid", "invalid"]
    assert usage.output_tokens == 64_000 and usage.cost_usd == pytest.approx(2 * (1000 * 0.10 + 32_000 * 0.50) / 1e6)


@needs_sdk
def test_schema_violation_is_retried(claude_api):
    claude_api(sse('{"wrong": 1}'), sse('{"answer": "second"}'))
    records: list[dict] = []
    assert _call(Settings(api_key="sk-ant-k"), llm.Usage(sink=_records(records))).answer == "second"
    assert [r["status"] for r in records] == ["invalid", "ok"]
    assert set(records[0]) == set(records[1])  # same record keys as the OpenAI path


@needs_sdk
def test_call_records_have_the_openai_paths_keys(claude_api, monkeypatch):
    claude_api(sse('{"answer": "ok"}'))
    claude_records: list[dict] = []
    _call(Settings(api_key="sk-ant-k"), llm.Usage(sink=_records(claude_records)))

    from test_costs import FakeClient

    fake = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda model, s: fake)
    openai_records: list[dict] = []
    _call(Settings(api_key="k"), llm.Usage(sink=_records(openai_records)), model="gpt-6-luna")
    assert set(claude_records[0]) == set(openai_records[0])  # the app stores records as table rows


# ── Costs ───────────────────────────────────────────────────────────────────


@needs_sdk
def test_cost_counts_cache_reads_and_writes(claude_api):
    claude_api(sse('{"answer": "ok"}', model="claude-sonnet-5-5", input_tokens=1000, cache_read=4000,
                   cache_write=2000, output_tokens=500))
    usage = llm.Usage()
    _call(Settings(api_key="sk-ant-k"), usage, model="claude-sonnet-5-5")
    # Sonnet 5.5: $2 input, $0.10 cache reads, $2.50 5-minute cache writes, $10 output per 1M tokens.
    assert usage.cost_usd == pytest.approx((1000 * 2.0 + 4000 * 0.10 + 2000 * 2.50 + 500 * 10.0) / 1e6)
    assert usage.input_tokens == 7000 and usage.cached_tokens == 4000 and usage.output_tokens == 500


def test_one_hour_cache_writes_use_their_price():
    usage = llm.Usage()
    cc = type("CC", (), {"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 300})()
    u = type("U", (), {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                       "cache_creation_input_tokens": 400, "cache_creation": cc})()
    usage.add_anthropic("claude-opus-5-5", u, DEFAULT_PRICES["claude-opus-5-5"])
    assert usage.cost_usd == pytest.approx((100 * 5.0 + 300 * 8.0) / 1e6)


def test_haiku_long_prompts_cost_more():
    haiku = DEFAULT_PRICES[HAIKU]
    assert haiku.cost(100_000, 1_000) == pytest.approx((100_000 * 0.10 + 1_000 * 0.50) / 1e6)
    assert haiku.cost(100_001, 1_000) == pytest.approx((100_001 * 0.50 + 1_000 * 2.50) / 1e6)
    # The threshold counts cache reads: they are part of the prompt.
    assert haiku.cost(150_000, 0, cached_tokens=120_000) == pytest.approx((30_000 * 0.50 + 120_000 * 0.05) / 1e6)
    # A document estimate is priced per request, not on the document's total.
    assert haiku.estimate(300_000, 3_000, calls=10) == pytest.approx(10 * haiku.cost(30_000, 300))
    assert DEFAULT_PRICES["gpt-6-luna"].estimate(300_000, 3_000, 10) == DEFAULT_PRICES["gpt-6-luna"].cost(300_000, 3_000)


def test_long_prompt_tier_is_validated_and_accepted_from_settings(monkeypatch):
    with pytest.raises(ValueError):
        Price(input=1, output=1, long_prompt_tokens=10)
    monkeypatch.setenv("SECTIONANY_PRICES", json.dumps({"claude-x": {
        "input": 1, "output": 2, "long_prompt_tokens": 10, "long_prompt": {"input": 3, "output": 4}}}))
    assert Settings().price_for("claude-x").cost(11, 0) == pytest.approx(33 / 1e6)


def test_listed_claude_prices():
    expect = {HAIKU: (0.10, 0.01, 0.50), "claude-sonnet-5-5": (2.00, 0.10, 10.00),
              "claude-opus-5-5": (4.00, 0.20, 20.00), "claude-fable-5-1": (10.00, 0.25, 50.00)}
    for model, (inp, cached, out) in expect.items():
        p = DEFAULT_PRICES[model]
        assert (p.input, p.cached, p.output) == (inp, cached, out)


def test_unpriced_claude_model_is_refused(paper_pdf):
    with pytest.raises(UnpricedModelError, match="claude-haiku-4-5"):
        section_anything.section(paper_pdf, "quick", model="claude-haiku-4-5", api_key="sk-ant-k")


# ── Whole runs ──────────────────────────────────────────────────────────────


@needs_sdk
def test_quick_run_on_claude(paper_pdf, claude_api, monkeypatch):
    fake = claude_api(sse('{"items": []}', input_tokens=800, output_tokens=60))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    monkeypatch.setenv("SECTIONANY_QUICK_MODEL", HAIKU)
    tree = section_anything.section(paper_pdf, "quick")
    assert tree.mode == "quick" and tree.model == HAIKU and tree.usage["calls"] == len(fake.requests) == 1
    assert tree.cost_usd == pytest.approx(round((800 * 0.10 + 60 * 0.50) / 1e6, 4))
    assert fake.client_kwargs[0]["api_key"] == "sk-ant-env"


@needs_sdk
def test_downgrade_skips_a_mode_whose_provider_has_no_key(paper_pdf, monkeypatch):
    # standard on Claude (key present), quick on OpenAI (no key): over the cap, go straight to free.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    tree = section_anything.section(paper_pdf, "standard", model=HAIKU, max_usd=0.0000001)
    assert tree.mode == "free"
    assert tree.downgraded[0].startswith("standard:") and tree.downgraded[1].startswith("quick: skipped")


def test_extraction_worker_gets_no_anthropic_key(paper_pdf, monkeypatch):
    from section_anything import isolate

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    script = ("import os, json; print(json.dumps({'error': 'internal', "
              "'message': ' '.join(sorted(k for k in os.environ if 'ANTHROPIC' in k.upper())) or 'none'}))")
    monkeypatch.setattr(isolate, "_worker_argv", lambda: [sys.executable, "-c", script])
    with pytest.raises(section_anything.ExtractionFailed, match=r"\(none\)"):
        isolate.extract_pdf(paper_pdf)
