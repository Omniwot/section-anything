"""Model calls with schema-validated output, cost accounting and a call log.

- Any OpenAI-compatible endpoint (`chat.completions.parse` with a JSON schema), or Anthropic's own
  API for Claude models (the `anthropic` extra: `messages.stream` with a JSON-schema
  `output_config.format` and `output_config.effort`). The provider follows the model id unless
  `Settings.provider` names one; see `Settings.api_key_for` for which key goes where.
- The client always gets an explicit `base_url` and `api_key` from `Settings`, so ambient
  ``OPENAI_BASE_URL`` / ``ANTHROPIC_BASE_URL`` settings of a host application never redirect these
  calls. Nothing is written to ``os.environ``.
- No hidden retries (`max_retries=0`): one retry on refusal or unparsable output, done here.
- Cost cap: checked before every attempt, and each call's output tokens are limited to what the
  remaining budget can pay for.
- Errors kept in logs and call records name the error type, HTTP status and error code, never
  prompt or response text (the prompt is the document). Prompt text is stored in call records
  only with `store_prompts`.
- Langfuse tracing only when `Settings.langfuse` is true and the `langfuse` extra is installed.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from section_anything.config import ANTHROPIC_EXTRA, BROWSER_PREFIX, CLAUDE_PREFIX, LOCAL_PREFIX, Price, Settings
from section_anything.errors import ConfigError, CostCapExceeded, LlmCallFailed, limit_hint

__all__ = ["BROWSER_PREFIX", "LOCAL_PREFIX", "CallSink", "CostCapExceeded", "LlmCallFailed", "Usage", "price_of",
           "structured"]

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

CallSink = Callable[[dict], Awaitable[None]]
CHARS_PER_TOKEN = 3.0  # conservative (English averages ~4): over- rather than under-estimates input cost
# Claude's tokenizer counts many more tokens on the line-numbered, tagged prompts: 1.86 characters per
# token on READoc arXiv 0905.3502 (70,700 characters, 38,019 tokens; gpt-6-luna counted 29,612).
CLAUDE_CHARS_PER_TOKEN = 1.5
MIN_OUTPUT_TOKENS = 256  # below this a structured answer cannot fit: stop instead of calling
MAX_OUTPUT_TOKENS = 32_000  # per call, thinking included; lowered further when the cap needs it

# Up-front estimates (`Strategy.estimate`, checked against the per-document cap before any call), in
# characters of document text per prompt token. OpenAI's 3.6 is unchanged. Claude counts many more tokens:
# on the 200 READoc development documents' Standard prompts, count_tokens gave 1.52 to 2.76 characters
# per token (median 2.24), so Claude's estimate uses 1.5, the same ratio as its per-call reserve above.
ESTIMATE_CHARS_PER_TOKEN = {"openai": 3.6, "anthropic": CLAUDE_CHARS_PER_TOKEN}
# Thinking Claude may add to a call's output, as a share of the call's prompt tokens, by the effort Claude
# is sent. Measured at "medium": Claude Haiku 5.5 thought 17,239 tokens on a 38,019-token prompt (0.45;
# Claude Sonnet 5.5 did not think on the same prompt). The other levels are not measured, only assumed to
# think more at each step up. No effort sent means the model's default, as much as "high" (Sonnet's).
# The allowance never takes a call's output past MAX_OUTPUT_TOKENS.
CLAUDE_THINKING_SHARE = {"low": 0.25, "medium": 0.5, "high": 1.0, "xhigh": 2.0, "max": 2.0}


@dataclass(frozen=True)
class TokenProfile:
    """How a model's prompts are counted in tokens, for up-front cost estimates."""

    chars_per_token: float
    thinking_share: float = 0.0  # output tokens of thinking per prompt token (Claude)

    def tokens(self, chars: float) -> int:
        return int(chars / self.chars_per_token)

    def per_call(self, openai_tokens: int) -> int:
        """A fixed per-call prompt allowance, given in tokens at OpenAI's ratio, at this ratio."""
        return round(openai_tokens * ESTIMATE_CHARS_PER_TOKEN["openai"] / self.chars_per_token)

    def output(self, answer_tokens: int, input_tokens: int, calls: int) -> int:
        """Output tokens for `calls` calls: the answers, plus thinking within each call's output limit."""
        if not self.thinking_share:
            return answer_tokens
        return min(answer_tokens + int(self.thinking_share * input_tokens), max(1, calls) * MAX_OUTPUT_TOKENS)


def token_profile(model: str = "", settings: Settings | None = None, effort: str | None = "low") -> TokenProfile:
    """The estimate profile for `model` called at a strategy's `effort`: Claude's tokenizer ratio and a
    thinking allowance for Claude models, OpenAI's ratio for every other model (or none given)."""
    if not model or model.startswith((LOCAL_PREFIX, BROWSER_PREFIX)):
        return TokenProfile(ESTIMATE_CHARS_PER_TOKEN["openai"])
    provider = settings.provider_for(model) if settings is not None else (
        "anthropic" if model.startswith(CLAUDE_PREFIX) else "openai")
    if provider != "anthropic":
        return TokenProfile(ESTIMATE_CHARS_PER_TOKEN["openai"])
    level = _claude_effort(effort) or "high"
    share = CLAUDE_THINKING_SHARE.get(level, max(CLAUDE_THINKING_SHARE.values()))
    return TokenProfile(ESTIMATE_CHARS_PER_TOKEN["anthropic"], share)


def price_of(model: str, inp: int, cached: int, out: int, settings: Settings | None = None) -> float | None:
    """USD for one call, or None when the model has no known price."""
    price = (settings or Settings()).price_for(model)
    return None if price is None else price.cost(inp, out, cached)


@dataclass
class Usage:
    """Running totals for one document. Every attempt is also handed to `sink` (an audit log, for
    example) as soon as it finishes."""

    calls: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    priced: bool = True
    sink: CallSink | None = None
    seq: int = 0
    bridge: Any | None = None  # BrowserBridge for "browser/<model>" runs
    by_step: dict[str, float] = field(default_factory=dict)

    def add(self, model: str, usage, price: Price | None = None) -> dict:
        tokens = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0}
        if usage is None:
            return tokens
        cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
        inp, out = usage.prompt_tokens or 0, usage.completion_tokens or 0
        cost = None if price is None else price.cost(inp, out, cached)
        return self._tally(inp, cached, out, reasoning, cost)

    def add_anthropic(self, model: str, usage, price: Price | None = None) -> dict:
        """`add` for an Anthropic `Usage`: the prompt counted here is uncached input plus cache reads
        and cache writes, each priced at its own rate."""
        if usage is None:
            return self.add(model, None, price)
        read = getattr(usage, "cache_read_input_tokens", 0) or 0
        write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        write_1h = getattr(getattr(usage, "cache_creation", None), "ephemeral_1h_input_tokens", 0) or 0
        write_1h = min(write_1h, write)
        inp = (getattr(usage, "input_tokens", 0) or 0) + read + write
        out = getattr(usage, "output_tokens", 0) or 0
        reasoning = getattr(getattr(usage, "output_tokens_details", None), "thinking_tokens", 0) or 0
        cost = None if price is None else price.cost(inp, out, read, write - write_1h, write_1h)
        return self._tally(inp, read, out, reasoning, cost)

    def _tally(self, inp: int, cached: int, out: int, reasoning: int, cost: float | None) -> dict:
        if cost is None:
            self.priced = False
        self.calls += 1
        self.input_tokens += inp
        self.cached_tokens += cached
        self.output_tokens += out
        self.reasoning_tokens += reasoning
        self.cost_usd += cost or 0.0
        return {
            "input_tokens": inp, "cached_tokens": cached, "output_tokens": out,
            "reasoning_tokens": reasoning, "cost_usd": None if cost is None else round(cost, 6),
        }

    async def record(self, entry: dict) -> None:
        self.seq += 1
        entry["seq"] = self.seq
        step = entry.get("step", "")
        self.by_step[step] = self.by_step.get(step, 0.0) + (entry.get("cost_usd") or 0.0)
        if self.sink:
            try:
                await self.sink(entry)
            except Exception as exc:  # noqa: BLE001 — logging must never fail a run
                # Type only: database errors can echo the record, which may hold document text.
                logger.warning("could not record LLM call: %s", type(exc).__name__)

    def summary(self) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "cached_tokens": self.cached_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cost_usd": round(self.cost_usd, 4) if self.priced else None,
            "cost_by_step": {k: round(v, 4) for k, v in self.by_step.items()},
        }


class _BadOutput(Exception):
    """A response we reject. The message is ours and never quotes the response."""


def describe_error(exc: BaseException) -> str:
    """Error text safe to log or store: type, HTTP status and error code, never prompt or output
    text (provider and validation messages can quote either)."""
    from section_anything.bridge import BridgeError

    if isinstance(exc, _BadOutput | CostCapExceeded | ConfigError | BridgeError):
        return f"{type(exc).__name__}: {exc}"
    if isinstance(exc, ValidationError):
        return f"ValidationError: {exc.error_count()} error(s)"
    parts = [type(exc).__name__]
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        parts.append(f"HTTP {status}")
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.replace("_", "").isalnum() and len(code) <= 64:
        parts.append(code)
    return " ".join(parts)


def _is_anthropic(model: str, settings: Settings) -> bool:
    return not model.startswith((LOCAL_PREFIX, BROWSER_PREFIX)) and settings.provider_for(model) == "anthropic"


_langfuse_warned = False


def _anthropic_client(model: str, settings: Settings):
    global _langfuse_warned
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        raise ConfigError(ANTHROPIC_EXTRA) from None
    key = settings.api_key_for(model)
    if key is None:
        raise ConfigError("no API key for Claude models: set ANTHROPIC_API_KEY or SECTIONANY_API_KEY, or pass api_key=")
    if settings.langfuse and not _langfuse_warned:
        _langfuse_warned = True
        logger.warning("Langfuse tracing covers OpenAI-client calls only; Claude model calls are not traced")
    # max_retries=0: our own loop retries; the SDK's hidden retries would spend past the cap.
    return AsyncAnthropic(api_key=key.get_secret_value(), base_url=settings.base_url_for(model),
                          timeout=settings.llm_timeout_seconds, max_retries=0)


def _client(model: str, settings: Settings):
    if model.startswith(LOCAL_PREFIX):
        # Local models through Ollama's OpenAI-compatible endpoint: free, slower.
        from openai import AsyncOpenAI

        return AsyncOpenAI(base_url=settings.ollama_base_url, api_key="ollama",
                           timeout=settings.local_timeout_seconds, max_retries=0)
    if _is_anthropic(model, settings):
        return _anthropic_client(model, settings)
    if settings.langfuse:
        try:
            from langfuse.openai import AsyncOpenAI
        except ImportError:
            raise ConfigError("langfuse=True needs the extra: pip install 'section-anything[langfuse]'") from None
    else:
        from openai import AsyncOpenAI
    key = settings.api_key_for(model)
    if key is None:
        raise ConfigError("no API key: set SECTIONANY_API_KEY or pass api_key=")
    # max_retries=0: our own loop retries; the SDK's hidden retries would spend past the cap.
    return AsyncOpenAI(api_key=key.get_secret_value(), base_url=settings.base_url,
                       timeout=settings.llm_timeout_seconds, max_retries=0)


def _is_free(price: Price | None) -> bool:
    return price is not None and price.input == 0 and price.output == 0 and not price.cached


def _over_cap(usage: Usage, cap: float, price: Price | None) -> bool:
    return usage.priced and usage.cost_usd >= cap and not _is_free(price)


def _cap_reached(usage: Usage, cap: float) -> CostCapExceeded:
    more = f"{max(cap * 2, 0.5):.2f}"
    return CostCapExceeded(
        f"Run stopped at ${usage.cost_usd:.2f}: the next call would pass the ${cap:.2f} per-document cap "
        + limit_hint("SECTIONANY_MAX_USD_PER_DOC", more, flag="--max-usd", python=f"max_usd={more}")
    )


def _affordable_output(price: Price | None, prompt_chars: int, usage: Usage, cap: float, wanted: int,
                       chars_per_token: float = CHARS_PER_TOKEN) -> int:
    """Output tokens this call may use so that its worst case stays within the cap."""
    if price is None or not usage.priced or _is_free(price):
        return wanted
    price = price.for_prompt(prompt_chars / chars_per_token)
    left = cap - usage.cost_usd
    input_cost = prompt_chars / chars_per_token * price.input / 1e6
    if price.output <= 0:
        if left - input_cost < 0:
            raise _cap_reached(usage, cap)
        return wanted
    afford = int((left - input_cost) * 1e6 / price.output)
    if afford < MIN_OUTPUT_TOKENS:
        raise _cap_reached(usage, cap)
    return min(wanted, afford)


async def structured(
    *,
    model: str,
    system: str,
    user: str,
    schema: type[T],
    usage: Usage,
    cost_cap_usd: float,
    step: str,
    effort: str | None = "low",
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
    attempts: int = 2,
    images: list[str] | None = None,
    settings: Settings | None = None,
) -> T:
    """One schema-constrained completion. Retries once on refusal or an unparsable response;
    raises CostCapExceeded before spending past the cap."""
    s = settings or Settings()
    if model.startswith(BROWSER_PREFIX):
        return await _structured_browser(model=model, system=system, user=user, schema=schema, usage=usage,
                                         step=step, max_output_tokens=max_output_tokens, attempts=attempts,
                                         settings=s)
    price = s.price_for(model)
    if _over_cap(usage, cost_cap_usd, price):
        raise _cap_reached(usage, cost_cap_usd)
    if _is_anthropic(model, s):
        return await _structured_anthropic(model=model, system=system, user=user, schema=schema, usage=usage,
                                           cost_cap_usd=cost_cap_usd, step=step, effort=effort,
                                           max_output_tokens=max_output_tokens, attempts=attempts, images=images,
                                           settings=s, price=price)
    content: list[dict] | str = user
    if images:
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": url, "detail": "high"}} for url in images
        ]
    local = model.startswith(LOCAL_PREFIX)
    max_key = "max_tokens" if local else "max_completion_tokens"
    kwargs: dict[str, Any] = {
        "model": model.removeprefix(LOCAL_PREFIX),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        "response_format": schema,
    }
    if local:
        # Local models think by default on Ollama's OpenAI endpoint; that costs minutes per call on a laptop.
        kwargs["temperature"] = 0
        kwargs["reasoning_effort"] = "none"
    elif effort:
        kwargs["reasoning_effort"] = effort
    prompt = f"{system}\n\n{user}"
    base = {
        "step": step,
        "model": model,
        "reasoning_effort": effort,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "prompt_chars": len(prompt),
        "images": len(images or []),
        "prompt_text": prompt if s.store_prompts else None,
    }
    client = _client(model, s)
    last: BaseException | None = None
    try:
        for attempt in range(1, attempts + 1):
            if _over_cap(usage, cost_cap_usd, price):  # re-checked before every paid attempt
                raise _cap_reached(usage, cost_cap_usd)
            kwargs[max_key] = _affordable_output(price, len(prompt), usage, cost_cap_usd, max_output_tokens)
            t0 = time.monotonic()
            entry = {**base, "attempt": attempt, "status": "error", "error": None, "response": None}
            try:
                resp = await client.chat.completions.parse(**kwargs)
                entry.update(usage.add(model, resp.usage, price))
                msg = resp.choices[0].message
                if msg.refusal:
                    entry["status"] = "refused"
                    if s.store_prompts:
                        entry["response"] = {"refusal": msg.refusal[:500]}
                    raise _BadOutput("model refused")
                if msg.parsed is None:
                    entry["status"] = "invalid"
                    raise _BadOutput(f"unparsable response (finish={resp.choices[0].finish_reason})")
                entry["status"], entry["response"] = "ok", msg.parsed.model_dump()
                return msg.parsed
            except Exception as exc:  # noqa: BLE001 — retried, then surfaced
                last = exc
                entry["error"] = describe_error(exc)
                logger.warning("sectioning model call attempt %s failed: %s", attempt, entry["error"])
            finally:
                entry["latency_ms"] = int((time.monotonic() - t0) * 1000)
                await usage.record(entry)
    finally:
        await client.close()
    raise LlmCallFailed(f"model call failed after {attempts} attempts: {describe_error(last) if last else 'unknown'}")


# The strategies ask for OpenAI's "low", which still reasons (gpt-6-luna: 416 reasoning tokens on READoc
# arXiv 0905.3502, 21 of 21 headings). Claude Haiku 5.5 at "low" did not think at all on the same prompt
# and returned only the title (1 of 21, two runs); at "medium", its default, 20 of 21. So Claude gets
# "medium" for the OpenAI levels at or below "low"; higher levels pass through.
_CLAUDE_EFFORT = {"none": "medium", "minimal": "medium", "low": "medium"}


def _claude_effort(effort: str | None) -> str | None:
    """The `output_config.effort` sent to Claude for a strategy's (OpenAI-style) effort."""
    return _CLAUDE_EFFORT.get(effort, effort) if effort else None


def _claude_image(url: str) -> dict:
    if url.startswith("data:"):
        header, _, data = url.partition(",")
        return {"type": "image", "source": {"type": "base64", "media_type": header[5:].split(";")[0], "data": data}}
    return {"type": "image", "source": {"type": "url", "url": url}}


async def _structured_anthropic(
    *, model: str, system: str, user: str, schema: type[T], usage: Usage, cost_cap_usd: float, step: str,
    effort: str | None, max_output_tokens: int, attempts: int, images: list[str] | None, settings: Settings,
    price: Price | None,
) -> T:
    """`structured` for a Claude model on Anthropic's own API.

    The request streams (`messages.stream` + `get_final_message`), so large `max_tokens` values do not
    hit HTTP timeouts. The schema goes in `output_config.format` as a JSON schema prepared by the
    SDK's `transform_schema` (constraints the API does not support move into descriptions) and the
    answer is validated here against the full Pydantic model, after `stop_reason` and `usage` are
    read: a refused or cut-off answer is still counted against the cap. No `temperature`, `top_p`,
    `top_k` or `thinking` is sent; `effort` maps to `output_config.effort`."""
    try:
        from anthropic import transform_schema
    except ImportError:
        raise ConfigError(ANTHROPIC_EXTRA) from None

    content: list[dict] | str = user
    if images:
        content = [_claude_image(url) for url in images] + [{"type": "text", "text": user}]
    output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": transform_schema(schema)}}
    claude_effort = _claude_effort(effort)
    if claude_effort:
        output_config["effort"] = claude_effort
    kwargs: dict[str, Any] = {
        "model": model,
        "system": system,
        "messages": [{"role": "user", "content": content}],
        "output_config": output_config,
    }
    prompt = f"{system}\n\n{user}"
    base = {
        "step": step,
        "model": model,
        "reasoning_effort": claude_effort,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "prompt_chars": len(prompt),
        "images": len(images or []),
        "prompt_text": prompt if settings.store_prompts else None,
    }
    client = _client(model, settings)
    last: BaseException | None = None
    try:
        for attempt in range(1, attempts + 1):
            if _over_cap(usage, cost_cap_usd, price):  # re-checked before every paid attempt
                raise _cap_reached(usage, cost_cap_usd)
            kwargs["max_tokens"] = _affordable_output(price, len(prompt), usage, cost_cap_usd, max_output_tokens,
                                                     CLAUDE_CHARS_PER_TOKEN)
            t0 = time.monotonic()
            entry = {**base, "attempt": attempt, "status": "error", "error": None, "response": None}
            try:
                async with client.messages.stream(**kwargs) as stream:
                    msg = await stream.get_final_message()
                entry.update(usage.add_anthropic(model, msg.usage, price))
                if msg.stop_reason == "refusal":
                    entry["status"] = "refused"
                    if settings.store_prompts:
                        details = getattr(msg, "stop_details", None)
                        entry["response"] = {"refusal": str(getattr(details, "category", None) or "")[:500]}
                    raise _BadOutput("model refused")
                if msg.stop_reason != "end_turn":
                    entry["status"] = "invalid"
                    if msg.stop_reason == "max_tokens":
                        raise _BadOutput(f"answer cut off at max_tokens={kwargs['max_tokens']}")
                    raise _BadOutput(f"unparsable response (stop_reason={msg.stop_reason})")
                text = "".join(b.text for b in msg.content if b.type == "text")
                try:
                    parsed = schema.model_validate_json(text)
                except ValidationError:
                    entry["status"] = "invalid"
                    raise _BadOutput("unparsable response (stop_reason=end_turn)") from None
                entry["status"], entry["response"] = "ok", parsed.model_dump()
                return parsed
            except Exception as exc:  # noqa: BLE001 — retried, then surfaced
                last = exc
                entry["error"] = describe_error(exc)
                logger.warning("sectioning model call attempt %s failed: %s", attempt, entry["error"])
            finally:
                entry["latency_ms"] = int((time.monotonic() - t0) * 1000)
                await usage.record(entry)
    finally:
        await client.close()
    raise LlmCallFailed(f"model call failed after {attempts} attempts: {describe_error(last) if last else 'unknown'}")


async def _structured_browser(
    *, model: str, system: str, user: str, schema: type[T], usage: Usage, step: str, max_output_tokens: int,
    attempts: int, settings: Settings,
) -> T:
    """A model reached through a BrowserBridge (see bridge.py). Free; validated like any output."""
    if usage.bridge is None:
        raise ConfigError("browser model used without a browser bridge")
    payload = {"model": model.removeprefix(BROWSER_PREFIX), "system": system, "user": user,
               "schema": schema.model_json_schema(), "max_output_tokens": max_output_tokens}
    prompt = f"{system}\n\n{user}"
    base = {"step": step, "model": model, "reasoning_effort": None,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "prompt_chars": len(prompt), "images": 0,
            "prompt_text": prompt if settings.store_prompts else None}
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        t0 = time.monotonic()
        entry = {**base, "attempt": attempt, "status": "error", "error": None, "response": None,
                 "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0}
        try:
            text = await usage.bridge.call(payload)
            usage.calls += 1
            text = text.strip()
            if text.startswith("```"):  # some local models wrap JSON in a code fence
                text = text.strip("`").removeprefix("json").strip()
            parsed = schema.model_validate_json(text)
            entry["status"], entry["response"] = "ok", parsed.model_dump()
            return parsed
        except Exception as exc:  # noqa: BLE001 - retried, then surfaced
            last = exc
            entry["error"] = describe_error(exc)
            logger.warning("browser model attempt %s failed: %s", attempt, entry["error"])
        finally:
            entry["latency_ms"] = int((time.monotonic() - t0) * 1000)
            await usage.record(entry)
    raise LlmCallFailed(f"local model call failed after {attempts} attempts: {describe_error(last) if last else 'unknown'}")
