from __future__ import annotations

import section_anything.extract
import section_anything.pipeline

from app.core.config import settings
from app.sectioning import extract, pipeline


def test_app_settings_map_onto_the_library(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-app")
    monkeypatch.setattr(settings, "RUN_COST_CAP_USD", 2.5)
    monkeypatch.setattr(settings, "MAX_PAGES", 123)
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "")
    s = settings.sectioning_settings()
    assert s.api_key.get_secret_value() == "sk-app"
    assert s.max_usd_per_doc == 2.5 and s.max_pages == 123
    assert s.price_for("gpt-6-luna").input == settings.model_prices["gpt-6-luna"]["input"]
    assert s.quick_model == settings.model_for("llm_review") and s.standard_model == settings.model_for("llm_text")
    assert s.store_prompts is False and s.langfuse is False and s.isolate_extraction is True


def test_app_modules_are_the_library() -> None:
    assert extract.PDFIUM_LOCK is section_anything.extract.PDFIUM_LOCK
    assert extract.Extraction is section_anything.extract.Extraction
    assert pipeline.STRATEGIES is section_anything.pipeline.STRATEGIES
