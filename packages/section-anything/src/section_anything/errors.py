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
