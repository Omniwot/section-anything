"""Extract untrusted PDFs safely: caps first, then layout analysis in a separate process.

Order of checks:

1. File size (`max_mb`), before the file is opened. A PDF passed as bytes or a stream is measured
   before anything is written to disk, checked for a ``%PDF-`` header, then written to a private
   temporary file (removed afterwards) so the rest runs as for a path.
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

import contextlib
import json
import math
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol

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
# PDFium (like Acrobat) accepts the %PDF- header anywhere in the first 1024 bytes, after a BOM,
# whitespace or other junk; pdfminer does not look for it at all.
HEADER_WINDOW = 1024
# Environment variables the worker may inherit: enough to start Python, nothing else.
_ENV_KEEP = ("PATH", "SYSTEMROOT", "WINDIR", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "LC_CTYPE", "HOME")


class Readable(Protocol):
    """A binary file-like object: an open file, `io.BytesIO`, an upload or download stream."""

    def read(self, size: int = -1, /) -> bytes: ...


# A path, or the PDF itself: bytes, a bytearray, a memoryview or a binary file-like object.
PdfInput = str | os.PathLike[str] | bytes | bytearray | memoryview | Readable


def check_pdf(path: Path, settings: Settings) -> int:
    """Size and page caps, checked without parsing any page content. Returns the page count."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError:
        raise PdfError(f"cannot read {path.name}") from None
    if not path.is_file():
        raise PdfError(f"not a file: {path}")
    _check_size(size, settings, path.name)
    return _check_pages(path, settings)


def _check_size(size: int, settings: Settings, name: str, *, exact: bool = True) -> None:
    """`exact` False: `size` is only how far a stream was read before it passed the cap."""
    if size > settings.max_mb * MB:
        need = math.ceil(size / MB) * (1 if exact else 2)
        raise PdfTooLarge(
            f"{name} is {'' if exact else 'more than '}{size / MB:.1f} MB; the limit is {settings.max_mb:g} MB "
            + limit_hint("SECTIONANY_MAX_MB", need, python=f"Settings(max_mb={need})")
        )


def _check_pages(path: Path, settings: Settings) -> int:
    n = count_pages(path)
    if n == 0:
        raise PdfError("PDF has no pages")
    if n > settings.max_pages:
        raise too_many_pages(n, settings.max_pages)
    return n


def _remaining(f: Readable) -> int | None:
    """Bytes left in a seekable stream, measured without reading it; None if it cannot seek."""
    try:
        if not f.seekable():  # type: ignore[attr-defined]
            return None
        pos = f.tell()  # type: ignore[attr-defined]
        end = f.seek(0, os.SEEK_END)  # type: ignore[attr-defined]
        f.seek(pos)  # type: ignore[attr-defined]
        return end - pos
    except (AttributeError, OSError, ValueError):
        return None


def _read_stream(f: Readable, limit: float) -> tuple[bytearray, int, bool]:
    """Read `f` once, stopping as soon as it passes `limit` bytes, so an endless or huge upload is
    refused early and costs no more memory than the cap. A seekable stream over the cap is not read
    at all. Returns the data (empty when over), the size, and whether that size is exact."""
    left = _remaining(f)
    if left is not None and left > limit:
        return bytearray(), left, True
    buf = bytearray()
    while chunk := f.read(MB):
        if isinstance(chunk, str):
            raise TypeError("the file is open in text mode: open it with 'rb'")
        buf += chunk
        if len(buf) > limit:
            return bytearray(), len(buf), False
    return buf, len(buf), True


def _pdf_bytes(pdf: bytes | bytearray | memoryview | Readable, settings: Settings) -> bytes | bytearray | memoryview:
    """The PDF's bytes, checked against the size cap and for a header, before anything is written."""
    if isinstance(pdf, (bytes, bytearray, memoryview)):
        data, size, exact = pdf, memoryview(pdf).nbytes, True
    elif callable(getattr(pdf, "read", None)):
        data, size, exact = _read_stream(pdf, settings.max_mb * MB)
    else:
        raise TypeError(f"expected a path, bytes or a binary file object, not {type(pdf).__name__}")
    _check_size(size, settings, "PDF", exact=exact)
    if b"%PDF-" not in bytes(data[:HEADER_WINDOW]):
        raise PdfError(f"not a PDF: no %PDF- header in the first {HEADER_WINDOW} bytes")
    return data


@contextlib.contextmanager
def _private_copy(data: bytes | bytearray | memoryview) -> Iterator[Path]:
    """`data` in a file only this user can read (mkstemp: mode 0600), in a new temporary directory
    (mode 0700) that is removed on the way out, after an error or a timeout too."""
    with tempfile.TemporaryDirectory(prefix="section-anything-") as tmp:
        fd, name = tempfile.mkstemp(suffix=".pdf", dir=tmp)
        with open(fd, "wb") as f:
            f.write(data)
        yield Path(name)


def _timeout_needed(limit: float, page: int, pages: int) -> int:
    """A time limit that should fit the whole extraction: the pace so far with a 25% margin (four
    times the limit before the first page), rounded up to a minute."""
    est = limit * pages / page * 1.25 if page and pages else limit * 4
    return math.ceil(est / 60) * 60


def extract_pdf(
    path: PdfInput,
    *,
    settings: Settings | None = None,
    on_page: Callable[[int, int], None] | None = None,
) -> Extraction:
    """Check the caps, then extract the PDF (in a worker process unless `isolate_extraction` is
    off). `path` is a path, or the PDF itself as bytes, a bytearray, a memoryview or a binary
    file-like object (read to the end once and left open). Raises PdfError / PdfTooLarge /
    ExtractionTimeout / ExtractionFailed, and TypeError for any other kind of `path`."""
    s = settings or Settings()
    if isinstance(path, (str, os.PathLike)):
        src = Path(path).resolve()
        check_pdf(src, s)
        return _extract(src, s, on_page)
    data = _pdf_bytes(path, s)  # size and header first: a refused PDF never reaches the disk
    with _private_copy(data) as src:
        _check_pages(src, s)
        return _extract(src, s, on_page)


def _extract(src: Path, s: Settings, on_page: Callable[[int, int], None] | None) -> Extraction:
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
