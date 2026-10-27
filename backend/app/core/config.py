from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    import section_anything


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "section-anything"
    ENVIRONMENT: str = Field(default="development", description="development|staging|production")
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/app"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h
    ALGORITHM: str = "HS256"

    LLM_MODEL: str = "gpt-6.1-sol"
    LLM_TIMEOUT_SECONDS: int = 90
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.2
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    ALLOWED_ORIGINS: str = "http://localhost:5173"
    MAX_PROMPT_CHARS: int = 20_000

    # Sectioning
    DATA_DIR: str = "data"
    CORPUS_DIR: str = "../corpus"
    MAX_UPLOAD_MB: int = 100
    MAX_PAGES: int = 500
    MAX_CHARS: int = 5_000_000
    RUN_COST_CAP_USD: float = 5.0
    # PDF text extraction runs in a separate process, stopped after this many seconds.
    EXTRACT_TIMEOUT_SECONDS: float = 300.0
    EXTRACT_MEMORY_MB: int = 4096  # Linux only; 0: no limit
    # Local models: LLM model ids "ollama/<name>" go to this OpenAI-compatible endpoint.
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    SECTIONING_LOCAL_TIMEOUT_SECONDS: float = 1800.0
    # Visitors' own models: a run with model "browser/<name>" sends each prompt to the signed-in
    # browser, which calls the visitor's local model (Ollama / LM Studio). Seconds to wait per call.
    BROWSER_LLM_TIMEOUT_SECONDS: float = 900.0
    # Public demo controls. PAID_MODELS_FOR: "all", or comma-separated emails allowed to run paid
    # (server-side) models; everyone can use Free and their own local model.
    PAID_MODELS_FOR: str = "all"
    ALLOW_REGISTRATION: bool = True
    REGISTRATION_INVITE_CODE: str = ""
    LOGIN_MAX_ATTEMPTS: int = 10  # failed logins per email or IP per 10 minutes
    # Store full prompt text in the LLM call log. Off by default: the prompt
    # is the document text; the log keeps a SHA-256 and length instead.
    AUDIT_STORE_PROMPTS: bool = False
    SECTIONING_LLM_TIMEOUT_SECONDS: int = 300
    ALLOWED_MODELS: str = "gpt-6.1-sol,gpt-6-luna,gpt-5.5,gpt-5"
    # Default model per stop (owner, 19 Oct): Quick check on the cheap model, Standard on Sol.
    # The UI preselects these; a run can still pick any allowed model.
    STRATEGY_MODELS_JSON: str = '{"llm_review": "gpt-6-luna", "llm_text": "gpt-6-luna"}'
    # USD per 1M tokens. Keep in config so cost readouts track price changes.
    MODEL_PRICES_JSON: str = (
        '{"gpt-5.5": {"input": 5.00, "cached": 0.50, "output": 30.00},'
        ' "gpt-5": {"input": 1.25, "cached": 0.125, "output": 10.00},'
        ' "gpt-6.1-sol": {"input": 2.00, "cached": 0.10, "output": 10.00},'
        ' "gpt-6-luna": {"input": 0.10, "cached": 0.01, "output": 0.50}}'
    )

    @property
    def strategy_models(self) -> dict[str, str]:
        import json

        return json.loads(self.STRATEGY_MODELS_JSON)

    def model_for(self, strategy_id: str) -> str:
        """The default model for a stop, falling back to LLM_MODEL."""
        return self.strategy_models.get(strategy_id, self.LLM_MODEL)

    @property
    def model_prices(self) -> dict[str, dict[str, float]]:
        import json

        return json.loads(self.MODEL_PRICES_JSON)

    def sectioning_settings(self) -> section_anything.Settings:
        """The sectioning library's settings, mapped from the app's. Built per call so tests and
        config changes take effect; cheap next to a run."""
        from section_anything import Settings as SectioningSettings

        return SectioningSettings(
            api_key=self.OPENAI_API_KEY or None,
            prices=self.model_prices,
            quick_model=self.model_for("llm_review"),
            standard_model=self.model_for("llm_text"),
            ollama_base_url=self.OLLAMA_BASE_URL,
            max_usd_per_doc=self.RUN_COST_CAP_USD,
            over_budget="fail",  # the app blocks over-cap runs before they start
            max_pages=self.MAX_PAGES,
            max_chars=self.MAX_CHARS,
            max_mb=self.MAX_UPLOAD_MB,
            extract_timeout_seconds=self.EXTRACT_TIMEOUT_SECONDS,
            extract_memory_mb=self.EXTRACT_MEMORY_MB,
            llm_timeout_seconds=self.SECTIONING_LLM_TIMEOUT_SECONDS,
            local_timeout_seconds=self.SECTIONING_LOCAL_TIMEOUT_SECONDS,
            store_prompts=self.AUDIT_STORE_PROMPTS,
            # Tracing is opt-in in the library; the app opts in when Langfuse keys are configured.
            langfuse=bool(self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY),
        )

    def may_use_paid_models(self, email: str) -> bool:
        allowed = self.PAID_MODELS_FOR.strip()
        return allowed == "all" or email.lower() in {e.strip().lower() for e in allowed.split(",") if e.strip()}

    @property
    def allowed_models_list(self) -> list[str]:
        return [m.strip() for m in self.ALLOWED_MODELS.split(",") if m.strip()]

    @field_validator("DATABASE_URL")
    @classmethod
    def require_asyncpg(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must be postgresql+asyncpg://…")
        return v

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def llm_provider(self) -> str:
        """Infer the provider from LLM_MODEL so the key check follows the model.

        LiteLLM accepts both `anthropic/claude-…` and a bare `claude-…`.
        """
        model = self.LLM_MODEL.lower()
        if model.startswith("anthropic/") or model.startswith("claude"):
            return "anthropic"
        return "openai"

    @property
    def llm_api_key(self) -> str:
        return (
            self.ANTHROPIC_API_KEY
            if self.llm_provider == "anthropic"
            else self.OPENAI_API_KEY
        )

    def validate_for_runtime(self) -> None:
        """Fail fast on unsafe production config."""
        if not self.is_production:
            return
        if self.SECRET_KEY in {"change-me", "change-me-in-production", ""}:
            raise RuntimeError("SECRET_KEY must be set to a strong random value in production")
        if "*" in self.allowed_origins_list:
            raise RuntimeError("ALLOWED_ORIGINS must not contain '*' in production")
        if not self.llm_api_key:
            key = "ANTHROPIC_API_KEY" if self.llm_provider == "anthropic" else "OPENAI_API_KEY"
            raise RuntimeError(f"{key} is required in production for LLM_MODEL={self.LLM_MODEL}")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
