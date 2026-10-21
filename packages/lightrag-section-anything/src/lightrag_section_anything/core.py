"""Section a PDF with the `section-anything` library, inside LightRAG's parser thread.

Settings come from the library (``SECTIONANY_*`` environment variables: API key, models, prices,
``SECTIONANY_MAX_USD_PER_DOC``, ``SECTIONANY_OVER_BUDGET``, page/size caps, extraction time limit).
The plugin adds ``SECTIONANY_MODE`` for the ``sectionany`` engine. Nothing is written to the
process environment, so LightRAG's own model settings are never touched.
"""

from __future__ import annotations

import os
from pathlib import Path

from section_anything import SectionTree, Settings, section


def resolve_mode(mode: str | None) -> str:
    """The engine's mode, or ``SECTIONANY_MODE`` (default free). Validated by the library."""
    return (mode or os.getenv("SECTIONANY_MODE") or "free").strip()


def section_pdf(path: Path, mode: str | None = None, *, settings: Settings | None = None) -> SectionTree:
    """Section one PDF. Over-budget runs downgrade (standard -> quick -> free) unless
    ``SECTIONANY_OVER_BUDGET=fail``; unpriced cloud models are refused before the PDF is read."""
    tree = section(path, resolve_mode(mode), settings=settings)
    if not tree.text.strip():  # pragma: no cover - the library refuses text-less PDFs first
        raise ValueError("no text layer; re-upload with an OCR engine, e.g. name.[mineru-P].pdf")
    return tree
