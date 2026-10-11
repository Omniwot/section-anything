from __future__ import annotations

import hashlib

import pypdfium2 as pdfium
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import Document, Run, User
from app.sectioning import jobs, pipeline

router = APIRouter(tags=["documents"])


def _doc_out(doc: Document) -> dict:
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
        "accuracy": {k: v for k, v in (run.accuracy or {}).items() if full or k not in ("missed", "extra")} or None,
        "progress": jobs.PROGRESS.get(f"run:{run.id}"),
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    if full:
        out["sections"] = run.sections
    return out


async def _own_doc(doc_id: int, db: AsyncSession, user: User) -> Document:
    doc = await db.get(Document, doc_id)
    if doc is None or doc.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.get("/catalog")
async def catalog(_user: User = Depends(get_current_user)) -> dict:
    """Strategies in slider order and the models a run may use."""
    return {
        "strategies": [
            {"id": s.id, "label": s.label, "description": s.description, "uses_llm": s.uses_llm}
            for s in pipeline.STRATEGIES
        ],
        "models": [m for m in settings.allowed_models_list if m in settings.model_prices],
        "limits": {"max_pages": settings.MAX_PAGES, "max_upload_mb": settings.MAX_UPLOAD_MB, "run_cost_cap_usd": settings.RUN_COST_CAP_USD},
    }


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds {settings.MAX_UPLOAD_MB} MB")
    # Trust the bytes, not the filename or Content-Type.
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Not a PDF file")
    try:
        pdf = pdfium.PdfDocument(data)
        n_pages = len(pdf)
        pdf.close()
    except pdfium.PdfiumError as exc:
        msg = "PDF is password-protected" if "password" in str(exc).lower() else "PDF could not be opened"
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg) from exc
    if n_pages == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "PDF has no pages")
    if n_pages > settings.MAX_PAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"PDF has {n_pages} pages; the limit is {settings.MAX_PAGES}")

    doc = Document(
        user_id=user.id,
        filename=(file.filename or "document.pdf")[:255],
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        n_pages=n_pages,
        status="extracting",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    (jobs.doc_dir(doc.id) / "original.pdf").write_bytes(data)
    jobs.start_extraction(doc.id)
    return _doc_out(doc)


@router.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    rows = await db.scalars(select(Document).where(Document.user_id == user.id).order_by(Document.id.desc()))
    return [_doc_out(d) for d in rows]


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return _doc_out(await _own_doc(doc_id, db, user))


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
) -> list[list[float]]:
    """Line boxes for one page: [line index, char start, x0, y0, x1, y1] in PDF user space."""
    doc = await _own_doc(doc_id, db, user)
    if doc.status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is not ready")
    ext = jobs.load_extraction(doc_id)
    return [[ln.i, ln.start, ln.x0, ln.y0, ln.x1, ln.y1] for ln in ext.lines if ln.page == page]


@router.get("/documents/{doc_id}/estimates")
async def get_estimates(doc_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    doc = await _own_doc(doc_id, db, user)
    if doc.status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is not ready")
    prices = {m: p for m, p in settings.model_prices.items() if m in settings.allowed_models_list}
    return pipeline.estimates(jobs.load_extraction(doc_id), prices)


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
    if body.model not in settings.allowed_models_list or body.model not in settings.model_prices:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Model not allowed")
    run = Run(document_id=doc.id, user_id=user.id, strategy=body.strategy, model=body.model, status="queued")
    db.add(run)
    await db.commit()
    await db.refresh(run)
    jobs.start_run(run.id)
    return _run_out(run, full=False)


@router.get("/documents/{doc_id}/runs")
async def list_runs(doc_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    await _own_doc(doc_id, db, user)
    rows = await db.scalars(select(Run).where(Run.document_id == doc_id).order_by(Run.id.desc()))
    return [_run_out(r, full=False) for r in rows]


@router.get("/runs/{run_id}")
async def get_run(run_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    run = await db.get(Run, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return _run_out(run, full=True)
