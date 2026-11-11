"""Standard runs a window's coverage re-read at the same time as the next window's first reading. The
real `structured` is used with a fake OpenAI-style client that waits before answering and records when
each call starts and ends, so cost counting, the cap and the call log are the library's own."""

from __future__ import annotations

import asyncio
import random
import re
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import section_anything.llm as llm
from section_anything.config import Settings
from section_anything.errors import CostCapExceeded, LlmCallFailed
from section_anything.extract import Extraction, Line, Page
from section_anything.strategies import llm_text
from section_anything.strategies.base import Context
from section_anything.strategies.llm_text import LlmTextStrategy, TextResult, TextSection

BODY = "Ordinary body text runs on for a while in the regular face at the body size of the page."
PER_PAGE = 50  # headings per page; one page (L lines, about 11,000 characters) per window below
L = 3 * PER_PAGE
DELAY = 0.03
PRICE = {"m": {"input": 0.10, "output": 0.50}}
SLICE = re.compile(r"DOCUMENT SLICE \(lines (\d+)–(\d+) of")
NUM = re.compile(r"window \d+/\d+")
HEADING = re.compile(r"^(\d+)\| ⟨H\+2⟩⟨B⟩ (\d+) (.*)$", re.M)


def _doc(pages: int) -> Extraction:
    """`pages` pages of numbered headings (12 pt bold), each followed by two body lines (10 pt)."""
    rows = []
    for p in range(1, pages + 1):
        for j in range(PER_PAGE):
            n = (p - 1) * PER_PAGE + j + 1
            rows += [(f"{n} Topic number {n}", 12.0, True, p), (BODY, 10.0, False, p), (BODY, 10.0, False, p)]
    lines, cursor = [], 0
    for i, (text, size, bold, page) in enumerate(rows):
        y0 = 3100 - 20 * (i % L) - 7 * page  # shifted per page: never read as running headers
        lines.append(Line(i=i, page=page, text=text, x0=72, y0=y0, x1=72 + 0.5 * size * len(text), y1=y0 + size,
                          size=size, bold=bold, start=cursor, end=cursor + len(text)))
        cursor += len(text) + 1
    pg = [Page(n=n, width=612, height=3150, origin_x=0, origin_y=0, rotation=0, has_text=True) for n in range(1, pages + 1)]
    return Extraction(pg, lines, "\n".join(r[0] for r in rows))


class Model:
    """Answers from the slice alone (never from PREVIOUS SECTIONS). `plan(window, reread, lines)` gives
    how many of the slice's headings to list, or "cut" for an answer cut off at the output limit, or
    an exception to raise."""

    def __init__(self, plan, delay: float = DELAY) -> None:
        self.plan, self.delay = plan, delay
        self.log: list[dict] = []  # one per request: window, reread, start, end
        self.requests: list[dict] = []

    def client(self, _model, _settings):
        model = self

        async def parse(**kw):
            user = kw["messages"][1]["content"]
            a, b = (int(x) for x in SLICE.search(user).groups())
            reread = "NOTE: an earlier reading" in user
            rec = {"window": (a, b), "reread": reread, "start": asyncio.get_running_loop().time(), "end": None,
                   "max": kw.get("max_completion_tokens"), "cancelled": False}
            model.log.append(rec)
            model.requests.append(kw)
            try:
                await asyncio.sleep(model.delay)
            except asyncio.CancelledError:
                rec["cancelled"] = True
                raise
            rec["end"] = asyncio.get_running_loop().time()
            what = model.plan((a, b), reread, b - a + 1)
            if isinstance(what, BaseException):
                raise what
            usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=500, prompt_tokens_details=None,
                                    completion_tokens_details=None)
            if what == "cut":
                msg = SimpleNamespace(refusal=None, parsed=None)
                return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=msg, finish_reason="length")])
            found = [(int(m.group(1)), m.group(2), m.group(3)) for m in HEADING.finditer(user)]
            secs = [TextSection(start_line=i, number=num, title=t, title_from_text=True, level=1,
                                start_marker=f"{num} {t}", end_marker="") for i, num, t in found[:what]]
            msg = SimpleNamespace(refusal=None, parsed=TextResult(sections=secs))
            return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=msg, finish_reason="stop")])

        async def close():
            return None

        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)), close=close)


def _run(monkeypatch, model: Model, pages: int, *, overlap: bool = True, cap: float = 1.0, prices=PRICE):
    monkeypatch.setattr(llm, "_client", model.client)
    st = LlmTextStrategy()
    st.window_chars = 10_000  # one page per window
    st.overlap = overlap
    entries: list[dict] = []
    progress: list[tuple[float, str]] = []

    async def sink(entry: dict) -> None:
        entries.append(entry)

    usage = llm.Usage(sink=sink)
    ctx = Context(model="m", usage=usage, cost_cap_usd=cap, settings=Settings(api_key="k", prices=prices),
                  progress=lambda f, m: progress.append((f, m)))
    found = asyncio.run(st.run(_doc(pages), ctx))
    return found, usage, entries, progress


def _short_first(windows: set[int], listed: int = 2):
    """First readings of the given windows (by first line // lines per page) list `listed` headings."""
    def plan(win, reread, _n):
        return None if reread or win[0] // (L) not in windows else listed
    return plan


def _same(a, b) -> None:
    """Two runs gave the same result and the same records."""
    (fa, ua, ea, _), (fb, ub, eb, _) = a, b
    assert fa == fb
    assert ua.coverage_retries == ub.coverage_retries
    assert ua.window_splits == ub.window_splits
    assert ua.calls == ub.calls and ua.cost_usd == pytest.approx(ub.cost_usd)
    # A window read ahead keeps the number it had when it started; after a split the sequential path
    # numbers it one higher. And while it is in flight, the re-read's second attempt may start after it.
    steps = lambda es: [(NUM.sub("window", e["step"]), e["attempt"], e["status"])  # noqa: E731
                        for e in sorted(es, key=lambda e: e["seq"])]
    assert sorted(steps(ea)) == sorted(steps(eb))
    if not ua.window_splits:
        assert steps(ea) == steps(eb)
        assert list(ua.by_step) == list(ub.by_step)


def test_the_next_window_is_read_while_the_window_before_is_read_again(monkeypatch):
    model = Model(_short_first({0, 2}))
    found, usage, entries, progress = _run(monkeypatch, model, pages=4)
    assert len(found) == 4 * PER_PAGE
    reread0 = next(r for r in model.log if r["reread"] and r["window"][0] == 0)
    first1 = next(r for r in model.log if not r["reread"] and r["window"][0] == L)
    # Window 2's first reading starts before window 1's re-read ends, and after it starts.
    assert reread0["start"] <= first1["start"] < reread0["end"]
    assert [c["kept"] for c in usage.coverage_retries] == ["retry", "retry"]
    # Call log in start order: the re-read is numbered before the reading started beside it.
    assert [e["step"] for e in sorted(entries, key=lambda e: e["seq"])] == [
        "read window 1/4", "re-read window 1/4 (coverage)", "read window 2/4",
        "read window 3/4", "re-read window 3/4 (coverage)", "read window 4/4"]
    assert list(usage.by_step) == [e["step"] for e in sorted(entries, key=lambda e: e["seq"])]
    assert usage.reserved_usd == 0.0 and usage.in_flight == 0
    # Progress never goes back, and each window is announced once.
    assert [f for f, _ in progress] == sorted(f for f, _ in progress)
    assert sum(f"Reading lines {L}–{2 * L - 1} (2/4)" in m for _, m in progress) == 1


def test_overlap_saves_the_re_read_time(monkeypatch):
    seq = Model(_short_first({0, 1, 2}), delay=0.05)
    _run(monkeypatch, seq, pages=4, overlap=False)
    par = Model(_short_first({0, 1, 2}), delay=0.05)
    _run(monkeypatch, par, pages=4)
    span = lambda m: max(r["end"] for r in m.log) - min(r["start"] for r in m.log)  # noqa: E731
    assert len(seq.log) == len(par.log) == 7
    assert span(par) < span(seq) - 0.08  # three re-reads hidden behind first readings


@pytest.mark.parametrize("seed", range(12))
def test_results_match_the_sequential_path(monkeypatch, seed):
    # Answers that never depend on PREVIOUS SECTIONS: random first and re-read answer lengths per window,
    # including empty answers, re-reads that list fewer, and cut-off re-reads (window read as halves).
    rng = random.Random(seed)
    table: dict = {}

    def plan(win, reread, n):
        key = (win, reread)
        if key not in table:
            if n < L:  # a half: full answer
                table[key] = None
            elif reread:
                table[key] = rng.choice([None, None, 1, "cut"])
            else:
                table[key] = rng.choice([None, None, 0, 2, 25])
        return table[key]

    pages = rng.choice([2, 3, 5])
    a = _run(monkeypatch, Model(plan, delay=rng.choice([0.0, 0.002])), pages=pages, overlap=False)
    b = _run(monkeypatch, Model(plan, delay=rng.choice([0.0, 0.002])), pages=pages)
    _same(a, b)


def test_without_the_coverage_check_nothing_changes(monkeypatch):
    s = Settings(api_key="k", prices=PRICE, coverage_retry=False)
    model = Model(_short_first({0}))
    monkeypatch.setattr(llm, "_client", model.client)
    st = LlmTextStrategy()
    st.window_chars = 10_000
    ctx = Context(model="m", usage=llm.Usage(), cost_cap_usd=1.0, settings=s)
    found = asyncio.run(st.run(_doc(3), ctx))
    assert len(found) == 2 + 2 * PER_PAGE and len(model.log) == 3
    assert all(r["start"] >= p["end"] for p, r in zip(model.log, model.log[1:], strict=False))


def test_a_cut_off_re_read_is_read_as_halves_while_the_next_window_is_in_flight(monkeypatch):
    def plan(win, reread, n):
        if n < L:
            return None  # halves: full answers
        if win[0] == 0:
            return "cut" if reread else 1
        return None

    model = Model(plan)
    found, usage, entries, _ = _run(monkeypatch, model, pages=3)
    assert [int(s.number) for s in found] == list(range(1, 3 * PER_PAGE + 1))
    assert usage.coverage_retries[0]["kept"] == "halves"
    assert usage.window_splits == [{"lines": [0, L - 1], "halves": [[0, L // 2 - 1], [L // 2, L - 1]]}]
    # Window 2 was read once, beside the re-read, and its answer used after the two halves.
    assert sum(1 for r in model.log if r["window"] == (L, 2 * L - 1)) == 1
    steps = [e["step"] for e in sorted(entries, key=lambda e: e["seq"])]
    assert steps == ["read window 1/3", "re-read window 1/3 (coverage)", "read window 2/3",
                     "re-read window 1/3 (coverage)", "read window 1/4", "read window 2/4", "read window 4/4"]


def test_a_window_read_ahead_that_is_cut_off_is_split_in_turn(monkeypatch):
    def plan(win, reread, n):
        if n < L:
            return None
        if win[0] == 0:
            return None if reread else 2
        if win[0] == L and not reread:
            return "cut"
        return None

    model = Model(plan)
    found, usage, _, _ = _run(monkeypatch, model, pages=3)
    assert [int(s.number) for s in found] == list(range(1, 3 * PER_PAGE + 1))
    assert usage.window_splits == [{"lines": [L, 2 * L - 1], "halves": [[L, L + L // 2 - 1], [L + L // 2, 2 * L - 1]]}]
    _same((found, usage, *_run(monkeypatch, Model(plan), pages=3)[2:]),
          _run(monkeypatch, Model(plan), pages=3, overlap=False))


def test_a_failed_first_reading_stops_the_run_and_the_reading_ahead(monkeypatch):
    def plan(win, reread, _n):
        if win[0] == 0:
            return None if reread else 2
        return RuntimeError("connection reset")

    model = Model(plan)
    with pytest.raises(LlmCallFailed):
        _run(monkeypatch, model, pages=3)


def test_an_unexpected_error_in_the_re_read_cancels_the_reading_ahead(monkeypatch):
    class Boom(Exception):
        pass

    async def read(self, ctx, user, a, b, step):
        if step.startswith("re-read"):
            await asyncio.sleep(0.005)
            raise Boom
        return await orig(self, ctx, user, a, b, step)

    orig = LlmTextStrategy._read
    monkeypatch.setattr(LlmTextStrategy, "_read", read)
    model = Model(_short_first({0}), delay=0.2)
    with pytest.raises(Boom):
        _run(monkeypatch, model, pages=3)
    ahead = next(r for r in model.log if r["window"][0] == L)
    assert ahead["cancelled"] and ahead["end"] is None


# ── Cost cap with calls in flight ────────────────────────────────────────────


class Out(BaseModel):
    answer: str


def test_calls_in_flight_cannot_together_pass_the_cap(monkeypatch):
    # $0.50 cap, output at $100 per 1M tokens: one call alone may use about 5,000 output tokens. Two calls
    # started together used to get 5,000 each (up to $1.00 together); now the second sees the first's
    # worst case held and is refused before sending anything.
    sent: list[int] = []

    async def parse(**kw):
        sent.append(kw["max_completion_tokens"])
        await asyncio.sleep(0.01)
        msg = SimpleNamespace(refusal=None, parsed=Out(answer="ok"))
        u = SimpleNamespace(prompt_tokens=10, completion_tokens=kw["max_completion_tokens"],
                            prompt_tokens_details=None, completion_tokens_details=None)
        return SimpleNamespace(usage=u, choices=[SimpleNamespace(message=msg, finish_reason="stop")])

    async def close():
        return None

    monkeypatch.setattr(llm, "_client", lambda m, s: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)), close=close))
    s = Settings(api_key="k", prices={"m": {"input": 1.0, "output": 100.0}})
    usage = llm.Usage()

    async def both():
        call = lambda step: llm.structured(model="m", system="s", user="doc", schema=Out, usage=usage,  # noqa: E731
                                           cost_cap_usd=0.5, step=step, settings=s)
        return await asyncio.gather(call("one"), call("two"), return_exceptions=True)

    one, two = asyncio.run(both())
    assert one.answer == "ok" and isinstance(two, CostCapExceeded)
    assert len(sent) == 1 and 4_900 <= sent[0] <= 5_000
    assert usage.cost_usd <= 0.5 and usage.reserved_usd == 0.0 and usage.in_flight == 0


def test_two_calls_that_both_fit_get_their_full_output_limit(monkeypatch):
    sent: list[int] = []

    async def parse(**kw):
        sent.append(kw["max_completion_tokens"])
        await asyncio.sleep(0.01)
        msg = SimpleNamespace(refusal=None, parsed=Out(answer="ok"))
        u = SimpleNamespace(prompt_tokens=10, completion_tokens=10, prompt_tokens_details=None,
                            completion_tokens_details=None)
        return SimpleNamespace(usage=u, choices=[SimpleNamespace(message=msg, finish_reason="stop")])

    async def close():
        return None

    monkeypatch.setattr(llm, "_client", lambda m, s: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)), close=close))
    s = Settings(api_key="k", prices={"m": {"input": 1.0, "output": 1.0}})
    usage = llm.Usage()
    assert llm.fits_together(usage, 1.0, "m", [3, 3], s)

    async def both():
        call = lambda step: llm.structured(model="m", system="s", user="doc", schema=Out, usage=usage,  # noqa: E731
                                           cost_cap_usd=1.0, step=step, settings=s)
        return await asyncio.gather(call("one"), call("two"))

    asyncio.run(both())
    assert sent == [llm.MAX_OUTPUT_TOKENS, llm.MAX_OUTPUT_TOKENS]


def test_no_reading_ahead_when_the_cap_could_not_pay_for_both(monkeypatch):
    # Output at $10 per 1M tokens: a full call's worst case is about $0.32, so a $0.50 cap leaves room for
    # the re-read but not for both it and the next window at full length: the run stays sequential.
    prices = {"m": {"input": 0.10, "output": 10.0}}
    model = Model(_short_first({0}))
    found, usage, _, _ = _run(monkeypatch, model, pages=3, cap=0.50, prices=prices)
    assert len(found) == 3 * PER_PAGE and usage.coverage_retries[0]["kept"] == "retry"
    assert all(r["start"] >= p["end"] for p, r in zip(model.log, model.log[1:], strict=False))
    assert all(r["max"] == llm.MAX_OUTPUT_TOKENS for r in model.log)
    _same((found, usage, *_run(monkeypatch, Model(_short_first({0})), pages=3, cap=0.50, prices=prices)[2:]),
          _run(monkeypatch, Model(_short_first({0})), pages=3, cap=0.50, prices=prices, overlap=False))


def test_a_reading_ahead_refused_at_the_cap_is_read_after_the_re_read(monkeypatch):
    # Force the reading ahead past the room check: it finds the re-read's worst case held and is refused
    # before sending; the window is then read once the re-read is done, as the sequential path reads it.
    monkeypatch.setattr(llm_text, "fits_together", lambda *a, **k: True)
    prices = {"m": {"input": 0.10, "output": 10.0}}
    model = Model(_short_first({0}))
    found, usage, entries, _ = _run(monkeypatch, model, pages=3, cap=0.20, prices=prices)
    assert len(found) == 3 * PER_PAGE
    assert [r["window"][0] for r in model.log] == [0, 0, L, 2 * L]
    assert all(r["start"] >= p["end"] for p, r in zip(model.log, model.log[1:], strict=False))
    steps = [e["step"] for e in sorted(entries, key=lambda e: e["seq"])]
    assert steps == ["read window 1/3", "re-read window 1/3 (coverage)", "read window 2/3", "read window 3/3"]
    assert usage.cost_usd <= 0.20 and usage.reserved_usd == 0.0
