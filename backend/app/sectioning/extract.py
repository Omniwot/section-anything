"""Re-export of `section_anything.extract` plus the isolated `extract_pdf`."""

from section_anything.extract import (
    EXTRACTOR_VERSION,
    LAPARAMS,
    PDFIUM_LOCK,
    TEXT_COMPATIBLE_SINCE,
    Extraction,
    Line,
    OutlineItem,
    Page,
    count_pages,
    extract,
    read_outline,
)
from section_anything.isolate import check_pdf, extract_pdf

__all__ = [
    "EXTRACTOR_VERSION",
    "LAPARAMS",
    "PDFIUM_LOCK",
    "TEXT_COMPATIBLE_SINCE",
    "Extraction",
    "Line",
    "OutlineItem",
    "Page",
    "check_pdf",
    "count_pages",
    "extract",
    "extract_pdf",
    "read_outline",
]
