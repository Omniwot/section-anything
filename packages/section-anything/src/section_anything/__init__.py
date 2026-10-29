"""Section Anything: find the sections of a PDF, with a cost/accuracy dial.

    >>> import section_anything
    >>> tree = section_anything.section("paper.pdf", mode="free")
    >>> print(tree.to_markdown())

Pre-release: the API may change before 1.0. Names load lazily, so importing the package is cheap.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__version__ = "0.1.5"

_EXPORTS = {
    "section": "section_anything.api",
    "asection": "section_anything.api",
    "SectionTree": "section_anything.api",
    "resolve_mode": "section_anything.api",
    "Settings": "section_anything.config",
    "Price": "section_anything.config",
    "DEFAULT_PRICES": "section_anything.config",
    "extract_pdf": "section_anything.isolate",
    "check_pdf": "section_anything.isolate",
    "Extraction": "section_anything.extract",
    "SectionAnythingError": "section_anything.errors",
    "ConfigError": "section_anything.errors",
    "UnpricedModelError": "section_anything.errors",
    "CostCapExceeded": "section_anything.errors",
    "LlmCallFailed": "section_anything.errors",
    "PdfError": "section_anything.errors",
    "PdfTooLarge": "section_anything.errors",
    "ExtractionTimeout": "section_anything.errors",
    "ExtractionFailed": "section_anything.errors",
}

__all__ = [
    "DEFAULT_PRICES",
    "ConfigError",
    "CostCapExceeded",
    "Extraction",
    "ExtractionFailed",
    "ExtractionTimeout",
    "LlmCallFailed",
    "PdfError",
    "PdfTooLarge",
    "Price",
    "SectionAnythingError",
    "SectionTree",
    "Settings",
    "UnpricedModelError",
    "__version__",
    "asection",
    "check_pdf",
    "extract_pdf",
    "resolve_mode",
    "section",
]

if TYPE_CHECKING:
    from section_anything.api import SectionTree, asection, resolve_mode, section
    from section_anything.config import DEFAULT_PRICES, Price, Settings
    from section_anything.errors import (
        ConfigError,
        CostCapExceeded,
        ExtractionFailed,
        ExtractionTimeout,
        LlmCallFailed,
        PdfError,
        PdfTooLarge,
        SectionAnythingError,
        UnpricedModelError,
    )
    from section_anything.extract import Extraction
    from section_anything.isolate import check_pdf, extract_pdf


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module 'section_anything' has no attribute {name!r}")
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
