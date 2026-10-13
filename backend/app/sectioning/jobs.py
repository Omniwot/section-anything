"""Background work for one local process: extraction and strategy runs.

Progress lives in memory (fine for a single local server) and final state in
Postgres. Tasks open their own DB sessions; request sessions end with the
request. Every extraction, run and model call is written to the audit log as
it happens.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

from app import audit
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Document, LlmCall, Run
from app.sectioning import pipeline
from app.sectioning.evaluate import score
from app.sectioning.extract import EXTRACTOR_VERSION, Extraction, extract
from app.sectioning.llm import CostCapExceeded, Usage

logger = logging.getLogger(__name__)

PROGRESS: dict[str, dict] = {}  # "doc:<id>" / "run:<id>" -> {"fraction", "message", ...}
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


def save_raw(doc_id: int, run_id: int, strategy: str, raw: list) -> None:
    """Keep a run's unresolved proposals, so resolver changes can be replayed
    against them without new model calls (scripts/evaluate_corpus.py)."""
    d = doc_dir(doc_id) / "runs"
    d.mkdir(exist_ok=True)
    payload = {"strategy": strategy, "raw": [asdict(r) for r in raw]}
    (d / f"{run_id}.raw.json").write_text(json.dumps(payload, separators=(",", ":")))


def is_stale(doc: Document) -> bool:
    return doc.status == "ready" and (doc.extractor_version or 1) < EXTRACTOR_VERSION


async def refresh_if_stale(db, doc: Document) -> None:
    """Re-extract a document saved by an older extractor. Its old runs keep
    their sections; they record which extraction their offsets refer to."""
    if not is_stale(doc):
        return
    old = doc.extractor_version or 1
    doc.status = "extracting"
    audit.record(db, "reextract_started", user_id=doc.user_id, document_id=doc.id,
                 from_version=old, to_version=EXTRACTOR_VERSION)
    await db.commit()
    start_extraction(doc.id)


def start_extraction(doc_id: int) -> None:
    async def work() -> None:
        key = f"doc:{doc_id}"

        def on_page(n: int, total: int) -> None:
            PROGRESS[key] = {"fraction": n / total, "message": f"Reading page {n} of {total}"}

        t0 = time.monotonic()
        try:
            path = doc_dir(doc_id) / "original.pdf"
            ext = await asyncio.to_thread(extract, path, on_page)
            ext.save(doc_dir(doc_id) / "extraction.json")
            _EXTRACTIONS[doc_id] = ext
            async with SessionLocal() as db:
                doc = await db.get(Document, doc_id)
                doc.n_chars = len(ext.text)
                doc.pages_without_text = sum(not p.has_text for p in ext.pages)
                doc.extractor_version = ext.version
                doc.status, doc.error = "ready", None
                audit.record(
                    db, "extraction_done", user_id=doc.user_id, document_id=doc_id,
                    pages=len(ext.pages), lines=len(ext.lines), chars=len(ext.text),
                    pages_without_text=doc.pages_without_text, extractor_version=ext.version,
                    seconds=round(time.monotonic() - t0, 2),
                )
                await db.commit()
        except Exception as exc:  # noqa: BLE001 — recorded on the document
            logger.exception("extraction failed doc=%s", doc_id)
            async with SessionLocal() as db:
                doc = await db.get(Document, doc_id)
                doc.status, doc.error = "failed", f"{type(exc).__name__}: {exc}"[:2000]
                audit.record(db, "extraction_failed", user_id=doc.user_id, document_id=doc_id, error=doc.error)
                await db.commit()
        finally:
            PROGRESS.pop(key, None)

    _spawn(work())


def start_run(run_id: int) -> None:
    async def work() -> None:
        key = f"run:{run_id}"
        PROGRESS[key] = {"fraction": 0.0, "message": "Starting", "cost_usd": 0.0, "calls": 0}

        async with SessionLocal() as db:
            run = await db.get(Run, run_id)
            doc = await db.get(Document, run.document_id)
            user_id, doc_id = run.user_id, doc.id
            run.status = "running"
            await db.commit()

            async def sink(entry: dict) -> None:
                async with SessionLocal() as log_db:
                    log_db.add(LlmCall(user_id=user_id, document_id=doc_id, run_id=run_id, **entry))
                    await log_db.commit()
                PROGRESS[key] = {**PROGRESS.get(key, {}), "cost_usd": round(usage.cost_usd, 4), "calls": usage.seq}

            usage = Usage(sink=sink)

            def progress(fraction: float, message: str) -> None:
                PROGRESS[key] = {**PROGRESS.get(key, {}), "fraction": fraction, "message": message}

            try:
                ext = load_extraction(doc_id)
                run.extractor_version = ext.version
                raw, sections, metrics = await pipeline.run(
                    ext, run.strategy, run.model, settings.RUN_COST_CAP_USD, progress, usage=usage
                )
                save_raw(doc_id, run_id, run.strategy, raw)
                gold = corpus_gold(doc.sha256)
                run.sections, run.metrics = sections, metrics
                run.accuracy = score(gold, sections) if gold else None
                run.status = "done"
                audit.record(
                    db, "run_finished", user_id=user_id, document_id=doc_id, run_id=run_id,
                    strategy=run.strategy, model=run.model, sections=len(sections),
                    cost_usd=metrics.get("cost_usd"), calls=metrics.get("calls"), seconds=metrics.get("seconds"),
                    f1=(run.accuracy or {}).get("f1"),
                )
            except Exception as exc:  # noqa: BLE001 — recorded on the run
                logger.exception("run failed run=%s", run_id)
                run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"[:2000]
                run.metrics = {**usage.summary(), "partial": True}
                kind = "run_stopped_cost_cap" if isinstance(exc, CostCapExceeded) else "run_failed"
                audit.record(
                    db, kind, user_id=user_id, document_id=doc_id, run_id=run_id,
                    strategy=run.strategy, model=run.model, error=run.error,
                    cost_usd=usage.summary()["cost_usd"], calls=usage.seq,
                )
            await db.commit()
        PROGRESS.pop(key, None)

    _spawn(work())
