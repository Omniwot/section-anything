"""Extraction worker: ``python -m section_anything._worker PDF OUT MAX_PAGES MAX_CHARS MEMORY_MB``.

Started by `section_anything.isolate`. Writes the extraction to OUT as JSON and reports progress
and the outcome as JSON lines on its original stdout. Error messages carry only text written by
this package or an exception's type name, never document text.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _limit_memory(mb: int) -> None:
    """Cap the address space on Linux. macOS does not enforce RLIMIT_AS, so it is skipped there."""
    if mb <= 0 or not sys.platform.startswith("linux"):
        return
    try:
        import resource

        limit = mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, ValueError, OSError):
        pass


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    pdf, out, max_pages, max_chars, memory_mb = args[0], args[1], int(args[2]), int(args[3]), int(args[4])
    # Keep the protocol on the original stdout; anything else that prints goes to stderr.
    proto = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    def emit(msg: dict) -> None:
        proto.write(json.dumps(msg) + "\n")
        proto.flush()

    _limit_memory(memory_mb)
    from section_anything.errors import PdfError, PdfTooLarge, limit_hint
    from section_anything.extract import extract

    try:
        ext = extract(Path(pdf), lambda n, total: emit({"page": n, "total": total}),
                      max_pages=max_pages, max_chars=max_chars)
        ext.save(Path(out))
    except PdfTooLarge as exc:
        emit({"error": "too_large", "message": str(exc)})
        return 2
    except PdfError as exc:
        emit({"error": "pdf", "message": str(exc)})
        return 2
    except MemoryError:
        need = memory_mb * 2
        message = ("out of memory" if not memory_mb else f"out of memory: the extraction worker's limit is {memory_mb} MB "
                   + limit_hint("SECTIONANY_EXTRACT_MEMORY_MB", need, python=f"Settings(extract_memory_mb={need})"))
        emit({"error": "memory", "message": message})
        return 3
    except Exception as exc:  # noqa: BLE001 — reported by type only: messages may quote the PDF
        emit({"error": "internal", "message": type(exc).__name__})
        return 1
    emit({"done": True})
    return 0


if __name__ == "__main__":
    sys.exit(main())
