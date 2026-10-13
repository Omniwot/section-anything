"""Append-only audit events. Callers own the session and the commit, except
`record_now`, which commits on its own (for background tasks and for events
that must survive a request that is about to fail)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models import AuditEvent


def record(
    db: AsyncSession,
    kind: str,
    *,
    user_id: int | None,
    document_id: int | None = None,
    run_id: int | None = None,
    **details,
) -> None:
    db.add(AuditEvent(kind=kind, user_id=user_id, document_id=document_id, run_id=run_id, details=details))


async def record_now(kind: str, **kwargs) -> None:
    async with SessionLocal() as db:
        record(db, kind, **kwargs)
        await db.commit()
