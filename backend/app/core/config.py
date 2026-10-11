from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    LLM_MODEL: str = "gpt-5.5"
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
