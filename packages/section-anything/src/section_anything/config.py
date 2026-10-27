"""Library settings.

Values come from, in order of precedence: arguments passed in code, then environment variables
named ``SECTIONANY_<FIELD>`` (for example ``SECTIONANY_MAX_USD_PER_DOC``), then the defaults
below. No ``.env`` file is read and nothing is ever written to ``os.environ``.

The provider follows the model: ``claude-*`` models go to Anthropic's own API (the optional
``anthropic`` extra), everything else to an OpenAI-compatible endpoint, unless ``provider`` names one.

API keys never cross providers. For OpenAI-compatible models the key falls back to
``OPENAI_API_KEY`` only while ``base_url`` is OpenAI's own endpoint; for Claude models it falls back
to ``ANTHROPIC_API_KEY`` only while the requests go to Anthropic's own endpoint.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from section_anything.errors import ConfigError

OPENAI_BASE_URL = "https://api.openai.com/v1"
ANTHROPIC_BASE_URL = "https://api.anthropic.com"
LOCAL_PREFIX = "ollama/"  # model ids for local models served by Ollama
BROWSER_PREFIX = "browser/"  # model ids answered through a BrowserBridge
CLAUDE_PREFIX = "claude-"  # model ids sent to Anthropic's own API unless `provider` says otherwise
ANTHROPIC_EXTRA = "Claude models need the anthropic extra: pip install 'section-anything[anthropic]'"

Provider = Literal["openai", "anthropic"]


class Price(BaseModel):
    """USD per 1M tokens.

    ``cached`` (cache reads) defaults to the input price. ``cache_write`` and ``cache_write_1h``
    (Anthropic's 5-minute and 1-hour prompt-cache writes) default to 1.25 and 2 times the input
    price. A request whose prompt (cache reads and writes included) is over ``long_prompt_tokens``
    tokens is priced at ``long_prompt`` instead, as Claude Haiku 5.5 is."""

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cached: float | None = Field(default=None, ge=0)
    cache_write: float | None = Field(default=None, ge=0)
    cache_write_1h: float | None = Field(default=None, ge=0)
    long_prompt_tokens: int | None = Field(default=None, ge=0)
    long_prompt: Price | None = None

    @model_validator(mode="after")
    def _long_prompt_pair(self) -> Price:
        if (self.long_prompt_tokens is None) != (self.long_prompt is None):
            raise ValueError("long_prompt_tokens and long_prompt go together")
        return self

    def for_prompt(self, prompt_tokens: float) -> Price:
        """The prices that apply to a request with this many prompt tokens."""
        if self.long_prompt is not None and self.long_prompt_tokens is not None and prompt_tokens > self.long_prompt_tokens:
            return self.long_prompt
        return self

    def cost(self, input_tokens: int, output_tokens: int, cached_tokens: int = 0, cache_write_tokens: int = 0,
             cache_write_1h_tokens: int = 0) -> float:
        """USD for one request. `input_tokens` counts the whole prompt, cache reads and writes included."""
        p = self.for_prompt(input_tokens)
        cached_price = p.input if p.cached is None else p.cached
        fresh = max(0, input_tokens - cached_tokens - cache_write_tokens - cache_write_1h_tokens)
        cost = fresh * p.input + cached_tokens * cached_price + output_tokens * p.output
        if cache_write_tokens or cache_write_1h_tokens:
            write = p.input * 1.25 if p.cache_write is None else p.cache_write
            write_1h = p.input * 2 if p.cache_write_1h is None else p.cache_write_1h
            cost += cache_write_tokens * write + cache_write_1h_tokens * write_1h
        return cost / 1e6

    def estimate(self, input_tokens: int, output_tokens: int, calls: int) -> float:
        """USD for `calls` requests sharing these totals; a long-prompt price is chosen per request."""
        if self.long_prompt is None or calls <= 1:
            return self.cost(input_tokens, output_tokens)
        return calls * self.cost(-(-input_tokens // calls), -(-output_tokens // calls))


Price.model_rebuild()

FREE = Price(input=0.0, output=0.0, cached=0.0)

# Built-in list prices (USD per 1M tokens, October 2026). Check your provider's current prices;
# add or override entries with SECTIONANY_PRICES or the `prices` argument.
DEFAULT_PRICES: dict[str, Price] = {
    "gpt-6.1-sol": Price(input=2.00, cached=0.10, output=10.00),
    "gpt-6-luna": Price(input=0.10, cached=0.01, output=0.50),
    "gpt-5.5": Price(input=5.00, cached=0.50, output=30.00),
    "gpt-5": Price(input=1.25, cached=0.125, output=10.00),
    # Anthropic list prices (platform.claude.com/docs/en/about-claude/pricing, checked 27 Oct 2026).
    # Claude Haiku 5.5 costs more per token for prompts over 100,000 tokens.
    "claude-haiku-5-5": Price(
        input=0.10, cached=0.01, cache_write=0.125, cache_write_1h=0.20, output=0.50,
        long_prompt_tokens=100_000,
        long_prompt=Price(input=0.50, cached=0.05, cache_write=0.625, cache_write_1h=1.00, output=2.50),
    ),
    "claude-sonnet-5-5": Price(input=2.00, cached=0.10, cache_write=2.50, cache_write_1h=4.00, output=10.00),
    "claude-opus-5-5": Price(input=4.00, cached=0.20, cache_write=5.00, cache_write_1h=8.00, output=20.00),
    "claude-fable-5-1": Price(input=10.00, cached=0.25, cache_write=12.50, cache_write_1h=20.00, output=50.00),
}


def _foreign_key(provider: Provider, base_url: str, key: str) -> bool:
    """True when a key that is plainly another provider's would go to this provider's own endpoint."""
    url = base_url.rstrip("/")
    if provider == "anthropic" and url == ANTHROPIC_BASE_URL:
        return key.startswith("sk-") and not key.startswith("sk-ant-")
    if provider == "openai" and url == OPENAI_BASE_URL:
        return key.startswith("sk-ant-")
    return False


class Settings(BaseSettings):
    """Settings for sectioning runs. Every field can be set as ``SECTIONANY_<NAME>``."""

    model_config = SettingsConfigDict(
        env_prefix="SECTIONANY_",
        env_file=None,
        extra="forbid",
        validate_default=True,
    )

    # Model provider: any OpenAI-compatible endpoint with JSON-schema outputs, or Anthropic's own API.
    # `provider` None: from the model id (claude-* -> anthropic, anything else -> openai).
    provider: Provider | None = None
    api_key: SecretStr | None = None
    # Used for whichever provider the model goes to. Left at OpenAI's endpoint, Claude models go to
    # Anthropic's (https://api.anthropic.com); set it to put a gateway or a local relay in front.
    base_url: str = OPENAI_BASE_URL
    # Both defaults are the model the published READoc scores and costs of quick and standard were
    # measured on. gpt-6.1-sol stays priced and can be chosen with SECTIONANY_STANDARD_MODEL or
    # `model=` (about 18x the cost; better on development READMEs only, not tested on held-out).
    quick_model: str = "gpt-6-luna"
    standard_model: str = "gpt-6-luna"
    local_model: str = ""  # Ollama model tag for mode "local"
    ollama_base_url: str = "http://localhost:11434/v1"
    # Extra or overriding prices; merged over DEFAULT_PRICES. Env: JSON object.
    prices: dict[str, Price] = Field(default_factory=dict)

    # Cost caps.
    max_usd_per_doc: float = Field(default=0.50, ge=0)
    over_budget: Literal["downgrade", "fail"] = "downgrade"

    # Input caps, checked before full parsing.
    max_pages: int = Field(default=500, ge=1)
    max_chars: int = Field(default=5_000_000, ge=1)
    max_mb: float = Field(default=100.0, gt=0)

    # Extraction runs in a separate process with a time limit (and, on Linux, a memory limit).
    isolate_extraction: bool = True
    extract_timeout_seconds: float = Field(default=120.0, gt=0)
    extract_memory_mb: int = Field(default=4096, ge=0)  # 0: no limit

    # Outline check: in these modes, drop sections the PDF's bookmarks do not list when the
    # outline looks complete (`section_anything.outline_check`). "quick" also covers local mode.
    # Env: JSON list, e.g. SECTIONANY_DEMOTE_UNLISTED_HEADINGS='[]' to turn it off. On for "free" by
    # default: held-out READoc +3.5 TEDS on papers and +6.1 on READMEs (research finding F012); for
    # quick and standard the gain was nil or marginal.
    demote_unlisted_headings: list[Literal["free", "quick", "standard"]] = Field(
        default_factory=lambda: ["free"]
    )

    # Model calls.
    llm_timeout_seconds: float = Field(default=300.0, gt=0)
    local_timeout_seconds: float = Field(default=600.0, gt=0)
    store_prompts: bool = False  # keep full prompt text in call records handed to a sink
    langfuse: bool = False  # trace calls with Langfuse (needs the `langfuse` extra)

    _key_from_openai_env: bool = PrivateAttr(default=False)

    @field_validator("provider", mode="before")
    @classmethod
    def _provider_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower() or None
        return value

    @model_validator(mode="after")
    def _key_fallback(self) -> Settings:
        if self.api_key is not None and not self.api_key.get_secret_value():
            self.api_key = None
        if self.api_key is None and self.base_url.rstrip("/") == OPENAI_BASE_URL:
            key = os.environ.get("OPENAI_API_KEY", "")
            if key:
                self.api_key = SecretStr(key)
                self._key_from_openai_env = True
        return self

    def provider_for(self, model: str) -> Provider:
        """Which API a cloud model's requests go to: `provider` if set, else from the model id."""
        if self.provider is not None:
            return self.provider
        return "anthropic" if model.startswith(CLAUDE_PREFIX) else "openai"

    def base_url_for(self, model: str) -> str:
        """The endpoint for a cloud model. Claude models go to Anthropic's own endpoint unless
        `base_url` was changed from OpenAI's (a gateway or relay in front of Anthropic)."""
        if self.provider_for(model) == "anthropic" and self.base_url.rstrip("/") == OPENAI_BASE_URL:
            return ANTHROPIC_BASE_URL
        return self.base_url

    def api_key_for(self, model: str) -> SecretStr | None:
        """The key sent with a cloud model's requests, or None.

        In order: the `api_key` argument or ``SECTIONANY_API_KEY``, then the provider's own variable
        (``OPENAI_API_KEY`` or ``ANTHROPIC_API_KEY``), which is read only while requests go to that
        provider's own endpoint. A key that is plainly the other provider's ("sk-ant-..." for OpenAI,
        "sk-..." for Anthropic) is refused rather than sent."""
        provider = self.provider_for(model)
        if provider == "anthropic":
            key = None if self._key_from_openai_env else self.api_key
            if key is None and self.base_url_for(model).rstrip("/") == ANTHROPIC_BASE_URL:
                env_key = os.environ.get("ANTHROPIC_API_KEY", "")
                key = SecretStr(env_key) if env_key else None
        else:
            key = self.api_key
        if key is not None and _foreign_key(provider, self.base_url_for(model), key.get_secret_value()):
            own, other = ("Anthropic", "OpenAI") if provider == "anthropic" else ("OpenAI", "Anthropic")
            raise ConfigError(
                f"the API key for {model!r} looks like an {other} key, so it was not sent to {own}. Pass the "
                f"{own} key with api_key=, or set {own.upper()}_API_KEY and leave SECTIONANY_API_KEY unset")
        return key

    def price_for(self, model: str) -> Price | None:
        """The model's price, $0 for local and browser models, or None when unknown."""
        if model.startswith((LOCAL_PREFIX, BROWSER_PREFIX)):
            return FREE
        return self.prices.get(model) or DEFAULT_PRICES.get(model)

    def all_prices(self) -> dict[str, Price]:
        return {**DEFAULT_PRICES, **self.prices}

    def with_overrides(self, **overrides: object) -> Settings:
        """A copy with the given fields replaced (None values are ignored). `prices` is merged."""
        changes = {k: v for k, v in overrides.items() if v is not None}
        if not changes:
            return self
        data = self.model_dump()
        if self._key_from_openai_env and "api_key" not in changes:
            data["api_key"] = None  # re-derived below, and only for OpenAI's own endpoint
        if "prices" in changes:
            changes["prices"] = {**data["prices"], **dict(changes["prices"])}  # type: ignore[arg-type]
        data.update(changes)
        return type(self)(**data)
