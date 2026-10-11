from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from litellm import acompletion

from app.core.config import settings

from app.core.prompts import FIX_MODE_SYSTEM_PROMPT, FIX_MODE_USER_TEMPLATE, SYSTEM_PROMPT


logger = logging.getLogger(__name__)

Validator = Callable[[str], str | None]


def _configure_provider_env() -> None:
    # Export whichever provider keys are configured; LiteLLM picks the one that
    # matches LLM_MODEL. Setting both is safe and lets a model swap be a
    # single env-var change rather than a code change.
    if settings.OPENAI_API_KEY:
        os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
    if settings.ANTHROPIC_API_KEY:
        os.environ["ANTHROPIC_API_KEY"] = settings.ANTHROPIC_API_KEY
    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
        os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
        os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST
        # LiteLLM native Langfuse integration
        os.environ.setdefault("LITELLM_CALLBACKS", "langfuse")


async def _chat(
    *,
    system: str,
    user: str,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    _configure_provider_env()
    kwargs: dict[str, Any] = {
        "model": model or settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "timeout": settings.LLM_TIMEOUT_SECONDS,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "temperature": settings.LLM_TEMPERATURE,
    }
    if metadata:
        kwargs["metadata"] = metadata
    try:
        response = await acompletion(**kwargs)
    except Exception:
        logger.exception("LLM completion failed model=%s", kwargs["model"])
        raise
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty model response")
    return content


async def complete(
    user_message: str,
    *,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    return await _chat(
        system=SYSTEM_PROMPT,
        user=user_message,
        model=model,
        metadata=metadata,
    )



async def complete_with_fix(
    user_message: str,
    *,
    validate: Validator,
    max_attempts: int = 3,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Generate, validate, and repair with a dedicated fix-mode system prompt."""
    result = await complete(user_message, model=model, metadata=metadata)
    issues = validate(result)
    attempt = 1
    while issues and attempt < max_attempts:
        logger.info("Fix mode attempt=%s issues=%s", attempt, issues)
        result = await _chat(
            system=FIX_MODE_SYSTEM_PROMPT,
            user=FIX_MODE_USER_TEMPLATE.format(issues=issues, previous=result),
            model=model,
            metadata={**(metadata or {}), "fix_attempt": attempt},
        )
        issues = validate(result)
        attempt += 1
    if issues:
        raise ValueError(f"Fix mode exhausted attempts: {issues}")
    return result

