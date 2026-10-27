"""Library settings.

Values come from, in order of precedence: arguments passed in code, then environment variables
named ``SECTIONANY_<FIELD>`` (for example ``SECTIONANY_MAX_USD_PER_DOC``), then the defaults
below. No ``.env`` file is read and nothing is ever written to ``os.environ``.

The API key falls back to ``OPENAI_API_KEY`` only while ``base_url`` is OpenAI's own endpoint,
so a key meant for OpenAI is never sent to another server.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

OPENAI_BASE_URL = "https://api.openai.com/v1"
LOCAL_PREFIX = "ollama/"  # model ids for local models served by Ollama
BROWSER_PREFIX = "browser/"  # model ids answered through a BrowserBridge


class Price(BaseModel):
    """USD per 1M tokens. ``cached`` (cached input) defaults to the input price."""

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cached: float | None = Field(default=None, ge=0)

    def cost(self, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
        cached_price = self.input if self.cached is None else self.cached
        fresh = max(0, input_tokens - cached_tokens)
        return (fresh * self.input + cached_tokens * cached_price + output_tokens * self.output) / 1e6


FREE = Price(input=0.0, output=0.0, cached=0.0)

# Built-in list prices (USD per 1M tokens, October 2026). Check your provider's current prices;
# add or override entries with SECTIONANY_PRICES or the `prices` argument.
DEFAULT_PRICES: dict[str, Price] = {
    "gpt-6.1-sol": Price(input=2.00, cached=0.10, output=10.00),
    "gpt-6-luna": Price(input=0.10, cached=0.01, output=0.50),
    "gpt-5.5": Price(input=5.00, cached=0.50, output=30.00),
    "gpt-5": Price(input=1.25, cached=0.125, output=10.00),
}


class Settings(BaseSettings):
    """Settings for sectioning runs. Every field can be set as ``SECTIONANY_<NAME>``."""

    model_config = SettingsConfigDict(
        env_prefix="SECTIONANY_",
        env_file=None,
        extra="forbid",
        validate_default=True,
    )

    # Model provider (any OpenAI-compatible endpoint with JSON-schema outputs).
    api_key: SecretStr | None = None
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
