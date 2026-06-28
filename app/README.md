# PaperPulse app (Phase 1 skeleton)

FastAPI + SQLite + Google OAuth. Runs independently of the daily pipeline in `api/`.

## Local setup

```
cd app
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Edit .env: paste GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, SESSION_SECRET
```

Generate a session secret:

```
openssl rand -hex 32
```

## Run

From the repo root (so `app.*` imports resolve):

```
PYTHONPATH=. app/.venv/bin/uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 and click "Sign in with Google".

## Files

- `main.py` — FastAPI app factory, session middleware, startup hook
- `config.py` — loads `app/.env`, exposes typed settings
- `db.py` — SQLite connection helper (WAL + FK on), schema bootstrap
- `schema.sql` — users / categories / user_categories / daily_runs
- `auth.py` — Authlib Google OAuth, login / callback / logout, user upsert
- `routes.py` — `/` (placeholder), `/healthz`
- `templates/` — Jinja2 SSR templates

## Test

From the repo root:

```
PYTHONPATH=. app/.venv/bin/pytest app/tests
```

Tests use a tmpdir SQLite DB and dummy OAuth env vars (set in `app/tests/conftest.py`).
No real network calls.

## `/goal` mode

Acceptance criteria for each phase 1 chunk live in `docs/PHASE1_CHUNKS.md`.
Autonomy boundary for `/goal` runs is in `docs/GOAL_AUTONOMY.md`.

## What this skeleton does NOT do yet

- Category picker
- Feed page
- Category seed
- CSRF on POST endpoints (no POST endpoints yet)
- Dockerfile / compose entry
