from __future__ import annotations

import hashlib
import re

import pypdfium2 as pdfium
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import AuditEvent, Document, LlmCall, Run, User
from app.sectioning import jobs, pipeline
from app.sectioning.bridge import BRIDGES, BROWSER_PREFIX
from app.sectioning.extract import PDFIUM_LOCK, TEXT_COMPATIBLE_SINCE

router = APIRouter(tags=["documents"])


def _doc_out(doc: Document, spent: dict | None = None) -> dict:
    p = jobs.PROGRESS.get(f"doc:{doc.id}")
    return {
        "id": doc.id,
        "filename": doc.filename,
        "n_pages": doc.n_pages,
        "n_chars": doc.n_chars,
        "pages_without_text": doc.pages_without_text,
        "status": doc.status,
        "error": doc.error,
        "progress": p,
        "has_gold": jobs.corpus_gold(doc.sha256) is not None,
        "extractor_version": doc.extractor_version,
        "spent_usd": round((spent or {}).get("cost", 0.0), 4),
        "llm_calls": (spent or {}).get("calls", 0),
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


def _run_out(run: Run, full: bool) -> dict:
    out = {
        "id": run.id,
        "document_id": run.document_id,
        "strategy": run.strategy,
        "model": run.model,
        "status": run.status,
        "error": run.error,
        "metrics": run.metrics,
        "estimate": run.estimate,
        "extractor_version": run.extractor_version,
        "stale": (run.extractor_version or 1) < TEXT_COMPATIBLE_SINCE,
        "accuracy": {k: v for k, v in (run.accuracy or {}).items() if full or k not in ("missed", "extra")} or None,
        "progress": jobs.PROGRESS.get(f"run:{run.id}"),
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    if full:
        out["sections"] = run.sections
    return out


def _event_out(e: AuditEvent) -> dict:
    return {
        "id": e.id,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "kind": e.kind,
        "document_id": e.document_id,
        "run_id": e.run_id,
        "details": e.details,
    }


def _call_out(c: LlmCall) -> dict:
    return {
        "id": c.id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "run_id": c.run_id,
        "seq": c.seq,
        "step": c.step,
        "attempt": c.attempt,
        "model": c.model,
        "reasoning_effort": c.reasoning_effort,
        "status": c.status,
        "error": c.error,
        "input_tokens": c.input_tokens,
        "cached_tokens": c.cached_tokens,
        "output_tokens": c.output_tokens,
        "reasoning_tokens": c.reasoning_tokens,
        "cost_usd": c.cost_usd,
        "latency_ms": c.latency_ms,
        "prompt_sha256": c.prompt_sha256,
        "prompt_chars": c.prompt_chars,
        "images": c.images,
    }


# Spend comes from each run's metrics (failed runs store partial metrics), so
# runs from before the call log existed still count.
_RUN_COST = func.coalesce(func.sum(Run.metrics["cost_usd"].as_float()), 0.0)
_RUN_CALLS = func.coalesce(func.sum(Run.metrics["calls"].as_integer()), 0)


async def _spent_by_doc(db: AsyncSession, user_id: int, doc_ids: list[int]) -> dict[int, dict]:
    if not doc_ids:
        return {}
    rows = await db.execute(
        select(Run.document_id, _RUN_COST, _RUN_CALLS)
        .where(Run.user_id == user_id, Run.document_id.in_(doc_ids))
        .group_by(Run.document_id)
    )
    return {d: {"cost": float(c), "calls": int(n)} for d, c, n in rows}


async def _own_doc(doc_id: int, db: AsyncSession, user: User) -> Document:
    doc = await db.get(Document, doc_id)
    if doc is None or doc.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


async def _own_run(run_id: int, db: AsyncSession, user: User) -> Run:
    run = await db.get(Run, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return run


LOCAL_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,119}")


@router.get("/catalog")
async def catalog(user: User = Depends(get_current_user)) -> dict:
    """Strategies in slider order and the models a run may use."""
    paid = settings.may_use_paid_models(user.email)
    return {
        "paid_models": paid,
        "local_models": {"prefix": BROWSER_PREFIX,
                         "strategies": [s.id for s in pipeline.STRATEGIES if s.uses_llm]},
        "strategies": [
            {"id": s.id, "label": s.label, "description": s.description, "uses_llm": s.uses_llm,
             "default_model": settings.model_for(s.id) if s.uses_llm else None}
            for s in pipeline.STRATEGIES
        ],
        "models": [m for m in settings.allowed_models_list if m in settings.model_prices] if paid else [],
        "limits": {"max_pages": settings.MAX_PAGES, "max_upload_mb": settings.MAX_UPLOAD_MB, "run_cost_cap_usd": settings.RUN_COST_CAP_USD},
    }


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    filename = (file.filename or "document.pdf")[:255]
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    data = await file.read(limit + 1)

    async def reject(code: int, reason: str, **details) -> HTTPException:
        await audit.record_now("upload_rejected", user_id=user.id, filename=filename,
                               size_bytes=len(data), reason=reason, **details)
        return HTTPException(code, reason)

    if len(data) > limit:
        raise await reject(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds {settings.MAX_UPLOAD_MB} MB")
    # Trust the bytes, not the filename or Content-Type.
    if not data.startswith(b"%PDF-"):
        raise await reject(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Not a PDF file")
    try:
        with PDFIUM_LOCK:
            pdf = pdfium.PdfDocument(data)
            n_pages = len(pdf)
            pdf.close()
    except pdfium.PdfiumError as exc:
        msg = "PDF is password-protected" if "password" in str(exc).lower() else "PDF could not be opened"
        raise await reject(status.HTTP_422_UNPROCESSABLE_ENTITY, msg) from exc
    if n_pages == 0:
        raise await reject(status.HTTP_422_UNPROCESSABLE_ENTITY, "PDF has no pages")
    if n_pages > settings.MAX_PAGES:
        raise await reject(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"PDF has {n_pages} pages; the limit is {settings.MAX_PAGES}",
            pages=n_pages,
        )

    sha = hashlib.sha256(data).hexdigest()
    doc = Document(user_id=user.id, filename=filename, sha256=sha, size_bytes=len(data), n_pages=n_pages, status="extracting")
    db.add(doc)
    await db.flush()
    audit.record(db, "upload", user_id=user.id, document_id=doc.id, filename=filename,
                 sha256=sha, size_bytes=len(data), pages=n_pages)
    await db.commit()
    await db.refresh(doc)
    (jobs.doc_dir(doc.id) / "original.pdf").write_bytes(data)
    jobs.start_extraction(doc.id)
    return _doc_out(doc)


@router.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    docs = list(await db.scalars(select(Document).where(Document.user_id == user.id).order_by(Document.id.desc())))
    for d in docs:
        await jobs.refresh_if_stale(db, d)
    spent = await _spent_by_doc(db, user.id, [d.id for d in docs])
    return [_doc_out(d, spent.get(d.id)) for d in docs]


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    doc = await _own_doc(doc_id, db, user)
    await jobs.refresh_if_stale(db, doc)
    spent = await _spent_by_doc(db, user.id, [doc.id])
    return _doc_out(doc, spent.get(doc.id))


@router.get("/documents/{doc_id}/file")
async def get_file(doc_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> FileResponse:
    await _own_doc(doc_id, db, user)
    return FileResponse(jobs.doc_dir(doc_id) / "original.pdf", media_type="application/pdf")


@router.get("/documents/{doc_id}/lines")
async def get_lines(
    doc_id: int,
    page: int = Query(ge=1),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[list]:
    """Line boxes for one page, in PDF user space:
    [line index, char start, char end, x0, y0, x1, y1, words], where words is
    flat [start, end, x0, x1, ...] with offsets relative to the line start."""
    doc = await _own_doc(doc_id, db, user)
    if doc.status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is not ready")
    ext = jobs.load_extraction(doc_id)
    return [[ln.i, ln.start, ln.end, ln.x0, ln.y0, ln.x1, ln.y1, ln.words] for ln in ext.lines if ln.page == page]


def _prices() -> dict[str, dict[str, float]]:
    return {m: p for m, p in settings.model_prices.items() if m in settings.allowed_models_list}


@router.get("/documents/{doc_id}/estimates")
async def get_estimates(doc_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    doc = await _own_doc(doc_id, db, user)
    if doc.status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is not ready")
    return pipeline.estimates(jobs.load_extraction(doc_id), _prices(), settings.RUN_COST_CAP_USD)


class RunRequest(BaseModel):
    strategy: str
    model: str


@router.post("/documents/{doc_id}/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    doc_id: int, body: RunRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    doc = await _own_doc(doc_id, db, user)
    if doc.status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is not ready")
    if body.strategy not in pipeline.BY_ID:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown strategy")
    local = body.model.startswith(BROWSER_PREFIX)
    if local:
        # The visitor's own model, reached through their browser: free for us, nothing sent to a provider.
        if not LOCAL_MODEL_NAME.fullmatch(body.model.removeprefix(BROWSER_PREFIX)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid local model name")
        if not pipeline.BY_ID[body.strategy].uses_llm:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This setting does not use a model")
    elif pipeline.BY_ID[body.strategy].uses_llm and not settings.may_use_paid_models(user.email):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Paid models are not enabled for this account: use Free or your own local model")
    elif pipeline.BY_ID[body.strategy].uses_llm and (
        body.model not in settings.allowed_models_list or body.model not in settings.model_prices
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Model not allowed")
    est = next(e for e in pipeline.estimates(jobs.load_extraction(doc_id), _prices(), settings.RUN_COST_CAP_USD)
               if e["strategy"] == body.strategy)
    cost = 0.0 if local or not pipeline.BY_ID[body.strategy].uses_llm else est["cost_usd"].get(body.model, 0.0)
    estimate = {k: est[k] for k in ("calls", "input_tokens", "output_tokens")} | {"cost_usd": cost}
    if not local and est["blocked"].get(body.model, False):
        await audit.record_now("run_blocked_cost_cap", user_id=user.id, document_id=doc.id, strategy=body.strategy,
                               model=body.model, estimate_usd=estimate["cost_usd"], cap_usd=settings.RUN_COST_CAP_USD)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Estimated ${estimate['cost_usd']:.2f} is over the ${settings.RUN_COST_CAP_USD:.2f} run cap",
        )
    run = Run(document_id=doc.id, user_id=user.id, strategy=body.strategy, model=body.model, status="queued",
              estimate=estimate)
    db.add(run)
    await db.flush()
    audit.record(db, "run_started", user_id=user.id, document_id=doc.id, run_id=run.id,
                 strategy=body.strategy, model=body.model, estimate_usd=estimate["cost_usd"])
    await db.commit()
    await db.refresh(run)
    jobs.start_run(run.id)
    return _run_out(run, full=False)


class BridgeReply(BaseModel):
    content: str | None = Field(default=None, max_length=400_000)
    error: str | None = Field(default=None, max_length=2_000)


@router.get("/runs/{run_id}/bridge/next")
async def bridge_next(run_id: int, wait: float = Query(default=10.0, ge=0, le=15),
                      db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Long-poll: the next prompt for the visitor's local model, or null. Only the run's owner."""
    run = await _own_run(run_id, db, user)
    bridge = BRIDGES.get(run_id)
    if bridge is None:
        return {"status": run.status, "request": None}
    return {"status": "running", "request": await bridge.next(wait)}


@router.post("/runs/{run_id}/bridge/{request_id}")
async def bridge_reply(run_id: int, request_id: str, body: BridgeReply,
                       db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """The local model's reply (or an error) for one prompt; validated against its schema by the run."""
    await _own_run(run_id, db, user)
    bridge = BRIDGES.get(run_id)
    if bridge is None or not bridge.resolve(request_id, body.content, body.error):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such pending prompt")
    return {"ok": True}


@router.get("/documents/{doc_id}/runs")
async def list_runs(doc_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    await _own_doc(doc_id, db, user)
    rows = await db.scalars(select(Run).where(Run.document_id == doc_id).order_by(Run.id.desc()))
    return [_run_out(r, full=False) for r in rows]


@router.get("/runs/{run_id}")
async def get_run(run_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return _run_out(await _own_run(run_id, db, user), full=True)


@router.get("/runs/{run_id}/calls")
async def get_run_calls(run_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    """Every model request the run made, in order, including retries."""
    await _own_run(run_id, db, user)
    rows = await db.scalars(select(LlmCall).where(LlmCall.run_id == run_id).order_by(LlmCall.seq))
    return [_call_out(c) for c in rows]


@router.get("/documents/{doc_id}/audit")
async def get_document_audit(doc_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    await _own_doc(doc_id, db, user)
    rows = await db.scalars(
        select(AuditEvent)
        .where(AuditEvent.user_id == user.id, AuditEvent.document_id == doc_id)
        .order_by(AuditEvent.id.desc())
    )
    return [_event_out(e) for e in rows]


@router.get("/audit")
async def get_audit(
    limit: int = Query(200, ge=1, le=2000),
    kind: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """The caller's own events, newest first. Includes rejected uploads, which
    have no document."""
    q = select(AuditEvent).where(AuditEvent.user_id == user.id)
    if kind:
        q = q.where(or_(*[AuditEvent.kind == k for k in kind.split(",")]))
    rows = await db.scalars(q.order_by(AuditEvent.id.desc()).limit(limit))
    return [_event_out(e) for e in rows]


@router.get("/usage")
async def get_usage(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Total model spend for the caller, all documents and runs."""
    cost, calls, runs = (
        await db.execute(select(_RUN_COST, _RUN_CALLS, func.count(Run.id)).where(Run.user_id == user.id))
    ).one()
    return {"spent_usd": round(float(cost), 4), "llm_calls": int(calls), "runs": runs}
