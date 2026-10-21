"""Settings: env prefix, no .env file, explicit arguments win, keys never follow a base_url
change, nothing written to os.environ, tracing only on request."""

from __future__ import annotations

import os

import section_anything
import section_anything.llm as llm
from section_anything import Settings
from section_anything.config import OPENAI_BASE_URL


def test_environment_and_explicit_arguments(monkeypatch):
    monkeypatch.setenv("SECTIONANY_MAX_USD_PER_DOC", "1.5")
    monkeypatch.setenv("SECTIONANY_PRICES", '{"my-model": {"input": 1, "output": 2}}')
    monkeypatch.setenv("SECTIONANY_MODE", "quick")  # read by the LightRAG plugin, ignored here
    s = Settings()
    assert s.max_usd_per_doc == 1.5
    assert s.price_for("my-model").output == 2 and s.price_for("gpt-6-luna") is not None
    assert Settings(max_usd_per_doc=0.2).max_usd_per_doc == 0.2
    assert s.with_overrides(max_usd_per_doc=0.3, prices={"other": {"input": 1, "output": 1}}).price_for("my-model")


def test_no_env_file_is_read(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("SECTIONANY_MAX_PAGES=3\nSECTIONANY_API_KEY=from-dotenv\n")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.max_pages == 500 and s.api_key is None


def test_openai_key_fallback_only_for_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    assert Settings().api_key.get_secret_value() == "sk-openai"
    assert Settings(base_url="https://llm.example.com/v1").api_key is None
    assert Settings().with_overrides(base_url="https://llm.example.com/v1").api_key is None
    assert Settings(api_key="sk-own", base_url="https://llm.example.com/v1").api_key.get_secret_value() == "sk-own"
    assert "sk-openai" not in repr(Settings())


class Capture:
    seen: dict = {}

    def __init__(self, **kwargs):
        Capture.seen = kwargs


def test_client_gets_explicit_base_url_and_key(monkeypatch):
    import openai

    monkeypatch.setenv("OPENAI_BASE_URL", "https://elsewhere.example.com/v1")
    monkeypatch.setattr(openai, "AsyncOpenAI", Capture)
    llm._client("gpt-6-luna", Settings(api_key="k"))
    seen = Capture.seen
    assert seen["base_url"] == OPENAI_BASE_URL and seen["api_key"] == "k" and seen["max_retries"] == 0
    assert seen["timeout"] == 300.0
    llm._client("ollama/qwen3:4b", Settings())
    assert Capture.seen["base_url"] == "http://localhost:11434/v1" and Capture.seen["api_key"] == "ollama"


def test_missing_key_is_a_config_error():
    import pytest

    with pytest.raises(section_anything.ConfigError, match="no API key"):
        llm._client("gpt-6-luna", Settings())


def test_langfuse_is_off_unless_requested(monkeypatch):
    import openai
    import pytest

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setattr(openai, "AsyncOpenAI", Capture)
    assert isinstance(llm._client("gpt-6-luna", Settings(api_key="k")), Capture)
    lf = pytest.importorskip("langfuse.openai")

    class LfCapture(Capture):
        pass

    monkeypatch.setattr(lf, "AsyncOpenAI", LfCapture)
    assert isinstance(llm._client("gpt-6-luna", Settings(api_key="k", langfuse=True)), LfCapture)


def test_environment_is_not_modified(paper_pdf):
    before = dict(os.environ)
    section_anything.section(paper_pdf, api_key="sk-test")
    assert dict(os.environ) == before
