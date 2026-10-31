"""Exceptions raised by Section Anything.

Messages never quote document text, so they are safe to log.
"""

from __future__ import annotations


class SectionAnythingError(Exception):
    """Base class for every error this library raises on purpose."""


class ConfigError(SectionAnythingError, ValueError):
    """Bad or missing configuration: unknown mode, no API key, no local model."""


class UnpricedModelError(ConfigError):
    """A cloud model has no known price, so no cost cap could be enforced."""


class CostCapExceeded(SectionAnythingError, RuntimeError):
    """A run would spend, or has spent, up to its per-document cost cap."""


class LlmCallFailed(SectionAnythingError, RuntimeError):
    """A model call failed after its retries."""


class PdfError(SectionAnythingError, ValueError):
    """The PDF cannot be read: damaged, encrypted, empty, or without a text layer."""


class PdfTooLarge(PdfError):
    """The PDF is over a size, page or character cap."""


class ExtractionTimeout(SectionAnythingError, TimeoutError):
    """Text extraction took longer than its time limit and was stopped."""


class ExtractionFailed(SectionAnythingError, RuntimeError):
    """The extraction worker crashed or stopped without a result."""


def limit_hint(env: str, value: object, *, flag: str | None = None, python: str | None = None) -> str:
    """The end of a cap's error message: says it is a safety limit and how to raise it, from the
    command line (`flag`), Python (`python`: a keyword of `section` or a `Settings` field) and the
    environment (`env`), each set to `value`."""
    ways = [f"{flag} {value}"] if flag else []
    if python:
        ways.append(f"{python} in Python")
    ways.append(f"{env}={value}")
    head = ", ".join(ways[:-1])
    return f"(a safety limit; to allow more, use {head + ', or ' if head else ''}{ways[-1]})"


def too_many_pages(n: int, limit: int) -> PdfTooLarge:
    return PdfTooLarge(
        f"PDF has {n} pages; the limit is {limit} "
        + limit_hint("SECTIONANY_MAX_PAGES", n, flag="--max-pages", python=f"max_pages={n}")
    )


def too_much_text(limit: int, needed: int) -> PdfTooLarge:
    """`needed`: a cap that should fit the whole text, estimated from the pages read so far."""
    return PdfTooLarge(
        f"PDF has more than {limit:,} characters of text "
        + limit_hint("SECTIONANY_MAX_CHARS", needed, python=f"Settings(max_chars={needed})")
    )
