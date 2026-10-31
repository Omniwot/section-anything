"""Extract untrusted PDFs safely: caps first, then layout analysis in a separate process.

Order of checks:

1. File size (`max_mb`), before the file is opened.
2. Page count from the PDF's page tree with PDFium (`max_pages`), in this process, under
   `PDFIUM_LOCK`. No page content is parsed.
3. In a worker process: the text size counted with PDFium (`max_chars`), then pdfminer's layout
   analysis with the same caps re-checked as it goes.

The worker is a fresh Python interpreter (`python -m section_anything._worker`). It is killed
when `extract_timeout_seconds` pass, gets a memory limit on Linux (`extract_memory_mb`), runs in
an empty temporary directory, and inherits no API keys: its environment holds only what Python
needs to start. It returns the extraction as JSON, never as a pickle.
"""

from __future__ import annotations

import json
import math
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from section_anything.config import Settings
from section_anything.errors import (
    ExtractionFailed,
    ExtractionTimeout,
    PdfError,
    PdfTooLarge,
    limit_hint,
    too_many_pages,
)
from section_anything.extract import Extraction, count_pages, extract

MB = 1024 * 1024
# Environment variables the worker may inherit: enough to start Python, nothing else.
_ENV_KEEP = ("PATH", "SYSTEMROOT", "WINDIR", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "LC_CTYPE", "HOME")


def check_pdf(path: Path, settings: Settings) -> int:
    """Size and page caps, checked without parsing any page content. Returns the page count."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError:
        raise PdfError(f"cannot read {path.name}") from None
    if not path.is_file():
        raise PdfError(f"not a file: {path}")
    if size > settings.max_mb * MB:
        need = math.ceil(size / MB)
        raise PdfTooLarge(
            f"{path.name} is {size / MB:.1f} MB; the limit is {settings.max_mb:g} MB "
            + limit_hint("SECTIONANY_MAX_MB", need, python=f"Settings(max_mb={need})")
        )
    n = count_pages(path)
    if n == 0:
        raise PdfError("PDF has no pages")
    if n > settings.max_pages:
        raise too_many_pages(n, settings.max_pages)
    return n


def _timeout_needed(limit: float, page: int, pages: int) -> int:
    """A time limit that should fit the whole extraction: the pace so far with a 25% margin (four
    times the limit before the first page), rounded up to a minute."""
    est = limit * pages / page * 1.25 if page and pages else limit * 4
    return math.ceil(est / 60) * 60


def extract_pdf(
    path: str | os.PathLike[str],
    *,
    settings: Settings | None = None,
    on_page: Callable[[int, int], None] | None = None,
) -> Extraction:
    """Check the caps, then extract `path` (in a worker process unless `isolate_extraction` is
    off). Raises PdfError / PdfTooLarge / ExtractionTimeout / ExtractionFailed."""
    s = settings or Settings()
    src = Path(path).resolve()
    check_pdf(src, s)
    if not s.isolate_extraction:
        return extract(src, on_page, max_pages=s.max_pages, max_chars=s.max_chars)
    return _extract_in_worker(src, s, on_page)


def _worker_argv() -> list[str]:
    return [sys.executable, "-m", "section_anything._worker"]


def _worker_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}
    # The worker must import this package and its dependencies from the same places we do.
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _extract_in_worker(src: Path, s: Settings, on_page: Callable[[int, int], None] | None) -> Extraction:
    if not sys.executable:
        raise ExtractionFailed("no Python executable to run the extraction worker; set isolate_extraction=False")
    with tempfile.TemporaryDirectory(prefix="section-anything-") as tmp:
        out = Path(tmp) / "extraction.json"
        argv = [*_worker_argv(), str(src), str(out), str(s.max_pages), str(s.max_chars), str(s.extract_memory_mb)]
        proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            argv, cwd=tmp, env=_worker_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
        )
        messages: queue.Queue[str | None] = queue.Queue()

        def pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                messages.put(line)
            messages.put(None)

        threading.Thread(target=pump, name="section-anything-extract", daemon=True).start()
        deadline = time.monotonic() + s.extract_timeout_seconds
        result: dict | None = None
        reached = (0, 0)  # the last page the worker reported, and the page count
        try:
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    need = _timeout_needed(s.extract_timeout_seconds, *reached)
                    raise ExtractionTimeout(
                        f"PDF extraction took longer than {s.extract_timeout_seconds:g} s and was stopped "
                        + limit_hint("SECTIONANY_EXTRACT_TIMEOUT_SECONDS", need, flag="--timeout",
                                     python=f"extract_timeout={need}")
                    )
                try:
                    line = messages.get(timeout=left)
                except queue.Empty:
                    continue
                if line is None:
                    break
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                if "page" in msg:
                    reached = (int(msg["page"]), int(msg["total"]))
                    if on_page:
                        on_page(*reached)
                elif "done" in msg or "error" in msg:
                    result = msg
                    break
        finally:
            if proc.poll() is None:
                if result is None:
                    proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        if result is None:
            raise ExtractionFailed(f"extraction worker stopped without a result (exit code {proc.returncode})")
        if "error" in result:
            kind, message = result.get("error"), str(result.get("message", ""))[:300]
            if kind == "too_large":
                raise PdfTooLarge(message)
            if kind == "pdf":
                raise PdfError(message)
            if kind == "memory":
                raise ExtractionFailed(message)
            raise ExtractionFailed(f"extraction failed ({message or kind})")
        try:
            return Extraction.load(out)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ExtractionFailed(f"extraction result unreadable ({type(exc).__name__})") from None
