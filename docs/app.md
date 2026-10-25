# Section Anything demo app

The web app in `backend/` and `frontend/` (upload a PDF, pick a setting, see the sections highlighted).
The sectioning itself is the library in `packages/section-anything`.

## Stack

| Layer | Tech |
|-------|------|
| API | FastAPI, Pydantic v2, JWT auth (enabled) |
| LLM | LiteLLM (`gpt-5.5`), optional fix-mode retries |
| DB | PostgreSQL via asyncpg + SQLAlchemy 2 + Alembic |
| Observability | Sentry + Langfuse (via LiteLLM callbacks) |
| Frontend | Vite + React + TypeScript |
| Deploy | Backend Dockerfile (Render web; build from the repo root: `docker build -f backend/Dockerfile .`); frontend static `dist/` |

## Quick start (local)

```bash
# 1. Conda env (from hustles bootstrap) or:
conda create -y -n section-anything python=3.11
conda activate section-anything
pip install -r backend/requirements.txt -e packages/section-anything

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
backend/app/                      FastAPI application (backend/app/sectioning re-exports the library)
backend/alembic/                  Migrations
frontend/src/                     React UI
packages/section-anything/        The sectioning library (Apache-2.0): section(pdf, mode), CLI
packages/lightrag-section-anything/  LightRAG parser plugin built on the library
site/                             Static project website and benchmark data
.github/workflows/                CI (lint + tests + build)
```

The sectioning core lives in `packages/section-anything`. The app maps its own settings onto the
library's (`Settings.sectioning_settings()` in `backend/app/core/config.py`); PDF extraction runs
in a separate process with a time limit (`EXTRACT_TIMEOUT_SECONDS`, default 300) and page,
character and size caps (`MAX_PAGES`, `MAX_CHARS`, `MAX_UPLOAD_MB`).

Licence: Apache-2.0 (`LICENSE`, `NOTICE`).

## Public demo: accounts and visitors' own models

Settings (env vars, see `backend/app/core/config.py`):

| Setting | Default | Use |
|---|---|---|
| `PAID_MODELS_FOR` | `all` | `all`, or comma-separated emails allowed to run server-side (paid) models. Everyone else gets Free and their own local model. |
| `ALLOW_REGISTRATION` | `true` | Close sign-up. |
| `REGISTRATION_INVITE_CODE` | empty | Require this code at sign-up. |
| `LOGIN_MAX_ATTEMPTS` | `10` | Failed sign-ins per email or IP per 10 minutes. |
| `BROWSER_LLM_TIMEOUT_SECONDS` | `900` | How long a run waits for each reply from a visitor's model. |

**Visitors' own models.** A run whose model is `browser/<name>` never calls a model from the
server. Each prompt is queued for the signed-in browser that owns the run, which sends it to the
visitor's Ollama (`/api/chat` with the JSON schema) or OpenAI-compatible local server (LM Studio)
and posts the reply back; the server validates it like any model output. Prompts never reach a
paid provider; the PDF is still uploaded so its text can be read. The queue is in memory: run the
API with **one worker** for these runs. Visitors start Ollama with `OLLAMA_ORIGINS=<demo origin>`.

End-to-end check without a real model: `hustles/.tmp/e2e-local/` (`fake_ollama.py` answers in
the requested schema; `e2e_local.py` plays the browser against a running API).
