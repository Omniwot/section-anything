"""Every model call has a total wall-clock deadline (`llm_timeout_seconds`, `local_timeout_seconds` for
local models), stream consumption included. The clients' own timeouts only limit each read: a Claude
stream that keeps sending pings never tripped them, and one call hung for 10+ minutes (research finding
F078). No network: Claude runs the real `anthropic` client over a mocked transport that streams slowly
or stalls; OpenAI-compatible calls use a fake client. Deadlines are fractions of a second."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import section_anything.llm as llm
from section_anything import LlmCallFailed, Settings

try:
    import anthropic
    import httpx2
except ImportError:  # the Claude tests skip without the extra
    anthropic = httpx2 = None
needs_sdk = pytest.mark.skipif(anthropic is None, reason="needs the anthropic extra")

HAIKU = "claude-haiku-5-5"
GUARD_S = 10.0  # a regression fails the test instead of hanging the suite


class Out(BaseModel):
    answer: str


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, GUARD_S))


def _call(settings: Settings, usage: llm.Usage, *, model: str = HAIKU):
    return _run(llm.structured(model=model, system="sys", user="doc", schema=Out, usage=usage, cost_cap_usd=1.0,
                               step="t", settings=settings))


def _sink(records: list[dict]):
    async def sink(entry):
        records.append(entry)

    return sink


# ── Claude: streamed answers ────────────────────────────────────────────────


def _events(text: str) -> list[bytes]:
    """A streamed Messages API answer, one SSE event per chunk."""
    import json

    usage = {"input_tokens": 1000, "output_tokens": 1, "cache_read_input_tokens": 0,
             "cache_creation_input_tokens": 0}
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_test", "type": "message", "role": "assistant", "content": [], "model": HAIKU,
            "stop_reason": None, "stop_sequence": None, "usage": usage}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                           "usage": {"output_tokens": 200}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return [f"event: {name}\ndata: {json.dumps(data)}\n\n".encode() for name, data in events]


PING = b'event: ping\ndata: {"type": "ping"}\n\n'


class Stream:
    """One streamed answer: `gap` seconds between events; with `stall`, pings forever after the
    first two events (the connection stays busy, so no per-read timeout fires)."""

    def __init__(self, text: str = '{"answer": "ok"}', *, gap: float = 0.0, stall: bool = False) -> None:
        self.text, self.gap, self.stall = text, gap, stall
        self.closed = False

    async def __aiter__(self):
        try:
            for i, event in enumerate(_events(self.text)):
                if self.stall and i == 2:
                    while True:
                        await asyncio.sleep(0.02)
                        yield PING
                await asyncio.sleep(self.gap)
                yield event
        finally:
            self.closed = True  # the stream was read to the end or the connection was closed


@pytest.fixture
def claude_streams(monkeypatch):
    """Install a fake Anthropic API that answers each request with the next queued `Stream`."""
    real = anthropic._client.AsyncAnthropic

    def install(*streams: Stream) -> list[Stream]:
        queue = list(streams)

        async def handler(request):
            return httpx2.Response(200, headers={"content-type": "text/event-stream", "request-id": "req_test"},
                                   content=queue.pop(0))

        def make(**kwargs):
            return real(**kwargs, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))

        monkeypatch.setattr(anthropic, "AsyncAnthropic", make)
        return list(streams)

    return install


@needs_sdk
def test_stalled_stream_is_cut_at_the_deadline_and_retried(claude_streams):
    stalled, good = claude_streams(Stream(stall=True), Stream())
    records: list[dict] = []
    usage = llm.Usage(sink=_sink(records))
    t0 = time.monotonic()
    out = _call(Settings(api_key="sk-ant-k", llm_timeout_seconds=0.3), usage)
    assert out.answer == "ok" and time.monotonic() - t0 < 2.0
    assert stalled.closed  # the stalled stream's connection was closed
    assert [r["status"] for r in records] == ["error", "ok"]
    assert records[0]["error"] == "APITimeoutError"  # logged as any client timeout
    assert 300 <= records[0]["latency_ms"] < 1500
    # The cut attempt reported no usage, so like any failed call it adds no tokens or cost.
    assert usage.calls == 1 and usage.input_tokens == 1000 and usage.output_tokens == 200
    assert "cost_usd" not in records[0] and usage.by_step == {"t": records[1]["cost_usd"]}


@needs_sdk
def test_stream_that_stalls_every_attempt_fails_as_a_timeout(claude_streams):
    streams = claude_streams(Stream(stall=True), Stream(stall=True))
    records: list[dict] = []
    usage = llm.Usage(sink=_sink(records))
    with pytest.raises(LlmCallFailed, match="after 2 attempts: APITimeoutError"):
        _call(Settings(api_key="sk-ant-k", llm_timeout_seconds=0.2), usage)
    assert all(s.closed for s in streams)
    assert [r["error"] for r in records] == ["APITimeoutError", "APITimeoutError"]
    assert usage.calls == 0 and usage.cost_usd == 0.0


@needs_sdk
def test_slow_but_steady_stream_within_the_deadline_completes(claude_streams):
    # 6 events 0.05 s apart: 0.3 s in all, under a 1 s deadline.
    claude_streams(Stream(gap=0.05))
    records: list[dict] = []
    usage = llm.Usage(sink=_sink(records))
    assert _call(Settings(api_key="sk-ant-k", llm_timeout_seconds=1.0), usage).answer == "ok"
    assert [r["status"] for r in records] == ["ok"] and records[0]["latency_ms"] >= 250


@needs_sdk
def test_deadline_is_per_attempt(claude_streams):
    # Each attempt gets the full deadline: the retry starts fresh after the first attempt used all of
    # it, so a steady 0.3 s answer still completes under a 0.4 s deadline (0.7 s after the call began).
    claude_streams(Stream(stall=True), Stream(gap=0.05))
    records: list[dict] = []
    assert _call(Settings(api_key="sk-ant-k", llm_timeout_seconds=0.4), llm.Usage(sink=_sink(records))).answer == "ok"
    assert [r["status"] for r in records] == ["error", "ok"]


# ── OpenAI-compatible and local: one response, not streamed ─────────────────


class FakeClient:
    """Stands in for AsyncOpenAI: each `parse` waits the next queued delay (None: forever), then answers."""

    def __init__(self, *delays: float | None) -> None:
        self.delays = list(delays)
        self.requests = 0
        self.cancelled = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))

    async def _parse(self, **kwargs):
        self.requests += 1
        delay = self.delays.pop(0)
        try:
            await asyncio.sleep(3600 if delay is None else delay)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=10, prompt_tokens_details=None,
                                completion_tokens_details=None)
        msg = SimpleNamespace(refusal=None, parsed=Out(answer="ok"))
        return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=msg, finish_reason="stop")])

    async def close(self) -> None:
        pass


def test_non_streaming_call_completes(monkeypatch):
    fake = FakeClient(0.05)
    monkeypatch.setattr(llm, "_client", lambda model, s: fake)
    usage = llm.Usage()
    assert _call(Settings(api_key="k", llm_timeout_seconds=1.0), usage, model="gpt-6-luna").answer == "ok"
    assert fake.requests == 1 and usage.calls == 1


def test_non_streaming_call_past_the_deadline_is_retried_then_fails(monkeypatch):
    fake = FakeClient(None, None)
    monkeypatch.setattr(llm, "_client", lambda model, s: fake)
    records: list[dict] = []
    with pytest.raises(LlmCallFailed, match="APITimeoutError"):
        _call(Settings(api_key="k", llm_timeout_seconds=0.2), llm.Usage(sink=_sink(records)), model="gpt-6-luna")
    assert fake.requests == 2 and fake.cancelled == 2
    assert [r["error"] for r in records] == ["APITimeoutError", "APITimeoutError"]


def test_local_models_use_the_local_deadline(monkeypatch):
    # Local generation is slow: local models keep their own, longer `local_timeout_seconds`.
    fake = FakeClient(0.3)
    monkeypatch.setattr(llm, "_client", lambda model, s: fake)
    s = Settings(llm_timeout_seconds=0.1, local_timeout_seconds=1.0)
    assert _call(s, llm.Usage(), model="ollama/qwen3:4b").answer == "ok"
    assert llm._deadline_seconds("ollama/qwen3:4b", s) == 1.0 and llm._deadline_seconds(HAIKU, s) == 0.1


def test_deadline_works_from_a_worker_thread_loop(monkeypatch):
    # `section()` called inside a running loop runs `asyncio.run` on a worker thread (api.section); the
    # deadline needs no particular loop. `section()` without a loop is covered by test_modes.
    import concurrent.futures

    fake = FakeClient(2.0, 0.01)  # bounded, so a regression fails instead of blocking the thread
    monkeypatch.setattr(llm, "_client", lambda model, s: fake)

    async def inside_a_loop():
        coro = llm.structured(model="gpt-6-luna", system="s", user="u", schema=Out, usage=llm.Usage(),
                              cost_cap_usd=1.0, step="t", settings=Settings(api_key="k", llm_timeout_seconds=0.2))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()

    assert _run(inside_a_loop()).answer == "ok" and fake.cancelled == 1
