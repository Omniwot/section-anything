"""Background work for one local process: extraction and strategy runs.

Progress lives in memory (fine for a single local server) and final state in
Postgres. Tasks open their own DB sessions; request sessions end with the
request.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Document, Run
from app.sectioning import pipeline
from app.sectioning.evaluate import score
from app.sectioning.extract import Extraction, extract

logger = logging.getLogger(__name__)

PROGRESS: dict[str, dict] = {}  # "doc:<id>" / "run:<id>" -> {"fraction", "message"}
_TASKS: set[asyncio.Task] = set()
_EXTRACTIONS: dict[int, Extraction] = {}  # small LRU-ish cache of parsed docs


def doc_dir(doc_id: int) -> Path:
    d = Path(settings.DATA_DIR) / "docs" / str(doc_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_extraction(doc_id: int) -> Extraction:
    if doc_id not in _EXTRACTIONS:
        if len(_EXTRACTIONS) > 8:
            _EXTRACTIONS.pop(next(iter(_EXTRACTIONS)))
        _EXTRACTIONS[doc_id] = Extraction.load(doc_dir(doc_id) / "extraction.json")
    return _EXTRACTIONS[doc_id]


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


def corpus_gold(sha256: str) -> list[dict] | None:
    """Gold annotation for a golden-corpus document, matched by file hash."""
    manifest = Path(settings.CORPUS_DIR) / "manifest.json"
    if not manifest.exists():
        return None
    for entry in json.loads(manifest.read_text()).get("documents", []):
        if entry.get("sha256") == sha256 and entry.get("gold"):
            path = manifest.parent / entry["gold"]
            return json.loads(path.read_text()) if path.exists() else None
    return None


def start_extraction(doc_id: int) -> None:
    async def work() -> None:
        key = f"doc:{doc_id}"

        def on_page(n: int, total: int) -> None:
            PROGRESS[key] = {"fraction": n / total, "message": f"Reading page {n} of {total}"}

        try:
            path = doc_dir(doc_id) / "original.pdf"
            ext = await asyncio.to_thread(extract, path, on_page)
            ext.save(doc_dir(doc_id) / "extraction.json")
            _EXTRACTIONS[doc_id] = ext
            async with SessionLocal() as db:
                doc = await db.get(Document, doc_id)
                doc.n_chars = len(ext.text)
                doc.pages_without_text = sum(not p.has_text for p in ext.pages)
                doc.status = "ready"
                await db.commit()
        except Exception as exc:  # noqa: BLE001 — recorded on the document
            logger.exception("extraction failed doc=%s", doc_id)
            async with SessionLocal() as db:
                doc = await db.get(Document, doc_id)
                doc.status, doc.error = "failed", f"{type(exc).__name__}: {exc}"[:2000]
                await db.commit()
        finally:
            PROGRESS.pop(key, None)

    _spawn(work())


def start_run(run_id: int) -> None:
    async def work() -> None:
        key = f"run:{run_id}"
        PROGRESS[key] = {"fraction": 0.0, "message": "Starting"}

        def progress(fraction: float, message: str) -> None:
            PROGRESS[key] = {"fraction": fraction, "message": message}

        async with SessionLocal() as db:
            run = await db.get(Run, run_id)
            doc = await db.get(Document, run.document_id)
            run.status = "running"
            await db.commit()
            try:
                ext = load_extraction(doc.id)
                sections, metrics = await pipeline.run(
                    ext, run.strategy, run.model, settings.RUN_COST_CAP_USD, progress
                )
                gold = corpus_gold(doc.sha256)
                run.sections, run.metrics = sections, metrics
                run.accuracy = score(gold, sections) if gold else None
                run.status = "done"
            except Exception as exc:  # noqa: BLE001 — recorded on the run
                logger.exception("run failed run=%s", run_id)
                run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"[:2000]
            await db.commit()
        PROGRESS.pop(key, None)

    _spawn(work())
