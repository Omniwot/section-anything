from __future__ import annotations

from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.logging import (
    RequestIdMiddleware,
    setup_logging,
    unhandled_exception_handler,
)
from app.db.session import ping_db
from app.schemas import HealthResponse, ReadyResponse


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging(debug=settings.DEBUG)
    settings.validate_for_runtime()
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            send_default_pii=False,
        )
    yield


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.add_middleware(RequestIdMiddleware)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(api_router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.APP_NAME)


@app.get("/ready", response_model=ReadyResponse)
async def ready(response: Response) -> ReadyResponse:
    try:
        await ping_db()
    except Exception as exc:
        response.status_code = 503
        return ReadyResponse(
            status="not_ready",
            database=f"error: {exc.__class__.__name__}",
        )
    return ReadyResponse(status="ok", database="ok")
