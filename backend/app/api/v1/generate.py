from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.llm import complete_with_fix
from app.db.session import get_db
from app.models import Job
from app.models import User
from app.schemas import GenerateRequest, GenerateResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),

    user: User = Depends(get_current_user),

) -> GenerateResponse:
    if len(body.prompt) > settings.MAX_PROMPT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Prompt exceeds {settings.MAX_PROMPT_CHARS} characters",
        )

    job = Job(
        prompt=body.prompt,
        status="running",

        user_id=user.id,

    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    try:

        def _validate(text: str) -> str | None:
            if not text or not text.strip():
                return "Empty model response"
            return None

        result = await complete_with_fix(
            body.prompt,
            validate=_validate,
            metadata={"job_id": job.id, "route": "generate"},
        )

    except Exception as exc:
        logger.exception("Generation failed job_id=%s", job.id)
        job.status = "failed"
        job.error = str(exc)[:2000]
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Generation failed",
        ) from exc

    job.result = result
    job.status = "done"
    job.error = None
    await db.commit()
    return GenerateResponse(result=result, job_id=job.id)
