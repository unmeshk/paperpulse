# Phase 1 — Deployment / Rollout Plan

Phase 1 code (Google login + personalized per-category feeds) is complete and
tested on branch `feat/phase1-personalized-feed`. This doc is the plan to take it
to production. It is the "next phase" of work; pick it up in a fresh context.

## Status going in

- Branch `feat/phase1-personalized-feed`, **not merged, no PR opened**.
- Commits: `fd5cb07` (chunk 1), `5f9020f` (chunk 2), `e5d8146` (chunk 3),
  `a36724f` (chunk 4).
- Tests green: 39 `app/tests` (app/.venv), 27 `api/tests` (root .venv).
- Verified live locally via Chrome: onboarding, feed, settings, save flow,
  CSRF 403. Chunk 4 (pipeline) is unit-tested with Gemini + network mocked; it
  has **never run for real** against Gemini.

## The core architectural change

The app (`app/`) is a **new second web service** that has never been deployed.
Today `docker-compose.prod.yml` has services `blog`, `api`, `nginx`, `certbot` —
no `app`, no shared volumes, and nginx only serves the blog at
`paperpulse.ukurup.com`.

The pipeline (`api/`) writes per-category blurbs; the app reads them. They are
separate containers, so they must share two paths via named volumes:

- **Content volume** — `api` writes `CONTENT_DIR/<NY-date>/<slug>.md`; `app`
  reads it. Same volume mounted in both at e.g. `/data/content`;
  `CONTENT_DIR=/data/content` in both services.
- **App DB volume** — the pipeline reads the app's SQLite for the dynamic fetch
  list (`SELECT DISTINCT category_slug FROM user_categories`). The app's DB
  volume (e.g. `/data/db/paperpulse.sqlite`) must also mount into `api`, with
  `APP_DB_PATH` pointing at it.

The systemd timer runs `docker compose run --rm api …`, which inherits the `api`
service's volumes + env — so adding them to the `api` service covers the 6am run.

---

## Steps

### 1. Containerize the app (code, in-repo)
- [ ] `app/Dockerfile` — mirror `api/Dockerfile` (`python:3.11-slim`), but run a
      server: `uvicorn app.main:app --host 0.0.0.0 --port 8000` (uvicorn already
      pinned in `app/requirements.txt`; decide uvicorn-workers vs gunicorn+uvicorn
      worker for prod).
- [ ] Add `app` service to `docker-compose.prod.yml`: image
      `ghcr.io/unmeshk/paperpulse-app`, `expose: 8000`, the content + DB volumes,
      env (`DB_PATH=/data/db/paperpulse.sqlite`, `CONTENT_DIR=/data/content`,
      `COOKIE_SECURE=true`), on the `web` network.
- [ ] Amend the `api` service: add the content + DB volumes and
      `CONTENT_DIR` / `APP_DB_PATH` env.
- [ ] Declare the two named volumes in the compose `volumes:` block.

### 2. App secrets (code gap + droplet ops)
- [ ] **Code gap:** `app/config.py` reads only `os.getenv` — it does NOT support
      Docker file-based secrets like `api/settings.py`'s `get_secret()`. Either
      (a) add a `get_secret`-style reader to the app (preferred for the sensitive
      values), or (b) inject `GOOGLE_OAUTH_CLIENT_ID`,
      `GOOGLE_OAUTH_CLIENT_SECRET`, `SESSION_SECRET` as env in compose.
- [ ] If (a): create secret files under `/var/lib/paperpulse/secrets/` on the
      droplet (root, `chmod 600`), reference as Docker secrets in compose.

### 3. Google OAuth for prod (external — Google Cloud Console)
- [ ] Add redirect URI `https://app.paperpulse.ukurup.com/auth/google/callback`
      (subdomain name is from the spec — **confirm it**).
- [ ] Move the consent screen Testing → Production. Scopes (openid/email/profile)
      are non-sensitive, so this mainly needs a **privacy policy URL** + homepage,
      not full app verification. Until then only test users can log in.

### 4. DNS + nginx + TLS (external + droplet ops)
- [ ] DNS: A record for the app subdomain → droplet IP.
- [ ] nginx: add an 80→443 redirect + a 443 server block proxying to `app:8000`.
      Use the **runtime-resolver pattern** already adopted for the blog
      (`resolver 127.0.0.11 valid=10s ipv6=off; set $up app:8000;
      proxy_pass http://$up;`) to avoid the stale-upstream-IP 502.
- [ ] certbot: issue a cert for the new subdomain.
- [ ] Gotcha (already documented): `docker compose up -d` won't recreate nginx on
      a config-only change → one `docker compose restart nginx` after editing
      `nginx/nginx.conf`.

### 5. CI/CD (code, in-repo — `.github/workflows/deploy.yml`)
- [ ] **Bug:** the test step runs only `api/tests/test_main.py`, so the new
      `test_feeds.py` (and `test_mixpanel.py`) never run in CI. Change to
      `pytest api/tests`.
- [ ] Add an **app test job**: `pip install -r app/requirements.txt`,
      `PYTHONPATH=. pytest app/tests`.
- [ ] Add an **app image** build+push (mirror the api/blog blocks; `file:
      app/Dockerfile`).
- [ ] **Verify** `scripts/deploy-paperpulse.sh` recreates all compose services
      (`docker compose up -d`) so the new `app` service actually comes up.
      (Script not re-read this session.)

### 6. Merge + deploy
- [ ] Land steps 1–5 on the branch, open the PR, merge to main → CI builds all
      images and triggers the droplet deploy. Sequencing: the app image must
      exist before the deploy runs the new compose service.

### 7. First-run verify (ops)
- [ ] App container starts → `init_db()` creates schema + seeds 155 categories on
      the DB volume.
- [ ] Trigger the pipeline manually (`systemctl start paperpulse-daily.service`)
      and confirm blurb files land in the content volume and render at `/feed`.
- [ ] Live smoke test on the subdomain: real OAuth login → onboarding → feed →
      settings.

---

## Gotchas that pass locally but break in the container

- **`tzdata` missing (HIGH PRIORITY).** Base image `python:3.11-slim` has no
  zoneinfo database. `ZoneInfo("America/New_York")` — used by chunk 2 (`app`
  feed date) AND chunk 4 (`api` blurb dir names) — raises
  `ZoneInfoNotFoundError` in the container. Passed locally only because macOS
  ships zoneinfo. **Fix: add `tzdata` to both `app/requirements.txt` and
  `api/requirements.txt`** (the pip `tzdata` package is the pure-Python fallback
  `zoneinfo` looks for). Without this the feed date and blurb writes break.
- **App secrets-from-env gap** (step 2) — same "works locally with `.env`,
  undefined in prod" class.
- **CI only runs `test_main.py`** (step 5) — the green chunk 4 suite isn't
  gating merges yet.

## Product / launch items (still open from the worklog)
- Privacy policy page — gates OAuth production mode (step 3).
- DigitalOcean Spaces backup — now higher priority: the app DB volume holds real
  user data.

## Open decisions to make
- Prod server for the app: uvicorn `--workers N` vs gunicorn + uvicorn worker.
- App secrets: file-based Docker secrets (needs app code change) vs env in compose.
- Confirm the subdomain name (`app.paperpulse.ukurup.com` per spec).

## Suggested order
Code first (steps 1, 2, 5, + tzdata) on the branch → external prep (DNS, OAuth,
privacy policy) → droplet ops (secrets, nginx, cert) → merge/deploy → verify →
backups.

## Notes
- Most of this is outside `app/`/`docs/` (compose, nginx, CI, Dockerfiles), so it
  is hard-gated under `docs/GOAL_AUTONOMY.md` — work it with explicit
  confirmation, not under an unattended `/goal`.
- Edge case carried from chunk 4: `api/main.py` early-returns when the blog's RSS
  categories are all empty, which skips the per-category blurb path that day even
  if a user-only category has papers. Rare; revisit if it bites.
