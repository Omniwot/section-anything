# section-anything

Production-oriented AI app scaffold (FastAPI + Vite React + LiteLLM).

## Stack

| Layer | Tech |
|-------|------|
| API | FastAPI, Pydantic v2, JWT auth (enabled) |
| LLM | LiteLLM (`gpt-5.5`), optional fix-mode retries |
| DB | PostgreSQL via asyncpg + SQLAlchemy 2 + Alembic |
| Observability | Sentry + Langfuse (via LiteLLM callbacks) |
| Frontend | Vite + React + TypeScript |
| Deploy | Backend Dockerfile (Render web); frontend static `dist/` |

## Quick start (local)

```bash
# 1. Conda env (from hustles bootstrap) or:
conda create -y -n section-anything python=3.11
conda activate section-anything
pip install -r backend/requirements.txt

# 2. Env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
# fill DATABASE_URL, SECRET_KEY, OPENAI_API_KEY, …

# 3. Migrate + run API
cd backend
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 4. Frontend
cd frontend
npm ci
npm run dev
```

## Production checklist

- [ ] `SECRET_KEY` is a long random value (never `change-me`)
- [ ] `DATABASE_URL` uses `postgresql+asyncpg://` and Neon SSL params as required
- [ ] `OPENAI_API_KEY` (or provider keys) set on Render
- [ ] Langfuse + Sentry keys set
- [ ] `ALLOWED_ORIGINS` is your frontend origin only (no `*`)
- [ ] Migrations run (`alembic upgrade head`) before traffic
- [ ] Auth required on `/api/v1/generate` — keep it that way

## API

- `GET /health` — liveness (process up)
- `GET /ready` — readiness (DB ping)
- `POST /api/v1/auth/register` / `login` / `GET /me`
- `POST /api/v1/generate` — LLM generation (Bearer token required)

## Layout

```
backend/app/          FastAPI application
backend/alembic/      Migrations
frontend/src/         React UI
.github/workflows/    CI (lint + tests + build)
```
