
from __future__ import annotations

import hmac
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Failed logins per email and per IP in the last 10 minutes (in memory, per process).
_FAILED: dict[str, list[float]] = {}


def _too_many(*keys: str) -> bool:
    now = time.monotonic()
    for k in keys:
        _FAILED[k] = [t for t in _FAILED.get(k, []) if now - t < 600]
    return any(len(_FAILED[k]) >= settings.LOGIN_MAX_ATTEMPTS for k in keys)


def _note_failure(*keys: str) -> None:
    for k in keys:
        _FAILED.setdefault(k, []).append(time.monotonic())


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    if not settings.ALLOW_REGISTRATION:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration is closed")
    code = settings.REGISTRATION_INVITE_CODE
    if code and not hmac.compare_digest((body.invite_code or "").encode(), code.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A valid invite code is required")
    existing = await db.scalar(select(User).where(User.email == body.email.lower()))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user = User(
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    keys = (f"email:{body.email.lower()}", f"ip:{request.client.host if request.client else '?'}")
    if _too_many(*keys):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Too many failed sign-ins; try again in 10 minutes")
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.hashed_password):
        _note_failure(*keys)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user

