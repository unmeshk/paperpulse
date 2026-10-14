# PaperPulse repository quickstart

Last checked: 2026-10-14. This is an orientation map, not authorization to implement plans or deploy.

## Start here

1. Read [AGENTS.md](AGENTS.md) for working rules and required skills.
2. Run `git status --short` and `git branch --show-current`; preserve existing work.
3. Read the latest entries in [docs/WORKLOG.md](docs/WORKLOG.md), then the relevant design below.
4. Check actual code before relying on older README or deployment instructions.

Current work branch: `feat/semantic-evaluation-main`, based on `origin/main` at `f8e2f7e`.
Milestone 0 merged through PR #56; its API/app/build CI passed on October 14.
The previous evaluation/budget branches are preserved; milestone 1 work carried forward.
The original `docs/semantic-interest-feed` branch and its commits are preserved.
UI/session fixes and preview tooling landed in main through PR #54. Milestone 0
budget implementation is merged; production accounting activation remains unverified. Milestone 1 offline tooling/data are
versioned on the evaluation branch. Local generated data and scratch
files remain outside version control. Recheck the working tree each session.

## Current architecture

- **Daily pipeline:** [api/main.py](api/main.py) orchestrates RSS retrieval, Gemini summaries, and publishing.
  [api/arxiv_client.py](api/arxiv_client.py) filters each feed to its latest publication date and deduplicates papers.
  [api/settings.py](api/settings.py) defines prompts and five public categories: `cs.LG`, `cs.AI`, `cs.CL`,
  `cs.CV`, `stat.ML`. [api/agent.py](api/agent.py) uses `gemini-3.1-flash-lite` and batches inputs.
  [api/model_calls.py](api/model_calls.py) handles counting, bounded calls/retries, and usage reconciliation;
  [api/model_budget.py](api/model_budget.py) enforces a shared $15/day ledger, quota pacing, and pipeline lock.
  No fixed 30-second sleeps remain. Dev mode caches fetched papers in dated root-level pickle files.
- **Public blog:** [api/webs.py](api/webs.py) writes `blog/_posts/YYYY-MM-DD-daily-summary.markdown`.
  Jekyll layouts/includes under `blog/` render the public archive and Mixpanel tracking.
- **Personalized category content:** [api/feeds.py](api/feeds.py) reads the union of user selections and
  fixed public categories from SQLite, then writes `CONTENT_DIR/<New-York-date>/<category>.md`.
  Summaries are shared by category, not generated separately for every reader.
- **Web app:** [app/main.py](app/main.py) builds FastAPI; Jinja templates and static assets live in `app/`.
  [app/auth.py](app/auth.py) handles Google OAuth and signed sessions. A separate `pp_logged_in` cookie
  is only a display hint for the blog. Static assets bypass session middleware to prevent stale-cookie races.
- **Preferences and feeds:** [app/routes.py](app/routes.py) implements onboarding/settings, selection of
  one to five categories, CSRF checks, account deletion, `/feed` date listing, and `/feed/{day}` rendering.
  Generated Markdown renders with raw HTML disabled. The shared picker supports search and subject filtering.
- **Storage:** [app/db.py](app/db.py) initializes SQLite WAL and seeds [categories.json](app/data/categories.json).
  [app/schema.sql](app/schema.sql) contains users, categories, user selections, and a `daily_runs` table;
  the current pipeline does not populate that run table. Account deletion cascades through selections.

## Local commands and configuration

Run from the repository root. Existing environments are `.venv/` for the pipeline and `app/.venv/` for the app;
dependencies live in [api/requirements.txt](api/requirements.txt) and [app/requirements.txt](app/requirements.txt).

```sh
# Pipeline tests
PYTHONPATH=. .venv/bin/python -m pytest api/tests -q

# App tests: unset inherited paths so fixtures use temporary DB/content storage
env -u DB_PATH -u CONTENT_DIR PYTHONPATH=. app/.venv/bin/python -m pytest app/tests -q

# Web app
PYTHONPATH=. app/.venv/bin/uvicorn app.main:app --reload --port 8000

# Public blog at localhost:4000
docker compose up --build

# Generate content: fetches RSS and calls Gemini, including when using dev paper caches
PROJECT_ENV=dev PYTHONPATH=. .venv/bin/python -m api.main
```

- Pipeline configuration: `GEMINI_API_KEY`, `PROJECT_DIR` (absolute repository path), `PROJECT_ENV`.
  `GEMINI_BUDGET_DIR` must be an absolute persistent directory with an initialized ledger. Missing/corrupt
  accounting stops the pipeline before retrieval. Initialization requires verified opening spend and quotas;
  follow the [milestone 0 runbook](docs/SEMANTIC_INTEREST_FEED_IMPLEMENTATION_PLAN.md#milestone-0-accounting-initialization-and-cutover).
  Never create a separate paid-evaluation allowance or delete/reset the production ledger.
  `CONTENT_DIR` enables category output; `APP_DB_PATH` points to the app DB for selected categories.
  Export pipeline path variables before launch because settings read them at import time.
- App configuration: `app/.env`, loaded explicitly by [app/config.py](app/config.py). Required:
  `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `SESSION_SECRET`.
  Optional: `DB_PATH`, `CONTENT_DIR`, `COOKIE_SECURE`, `BLOG_URL`, `INDICATOR_COOKIE_DOMAIN`.
- Both components support Docker secret files under `/run/secrets/`. Never copy secret values into documentation.
- Fresh API verification on 2026-10-14: **78 tests passed**, including evaluation controls and archived RSS membership.
  Historical baseline on 2026-10-13: **70 API tests and 54 app tests passed**; production Compose validates. No live OAuth, browser,
  paid Gemini, or production verification was performed in that check.
- Local browser preview/check tooling: [preview_design.py](app/tests/preview_design.py) and
  [browser_design.cjs](app/tests/browser_design.cjs). Read their setup before use; browser evidence in the
  worklog is historical, separate from the test baseline above.

## Active work and plans

- **Merged in main (PR #54):** blog/app visual alignment, shared searchable category picker, and static-response
  session/CSRF race fix. Review state and evidence: [PERSONALIZED_FEED_DESIGN.md](docs/PERSONALIZED_FEED_DESIGN.md).
  These changes are inherited from main; deployment has not been freshly verified.
- **Latest planning:** semantic interest feeds. Read the
  [specification](docs/SEMANTIC_INTEREST_FEED_SPEC.md),
  [technical design](docs/SEMANTIC_INTEREST_FEED_TECHNICAL_DESIGN.md), and
  [implementation plan](docs/SEMANTIC_INTEREST_FEED_IMPLEMENTATION_PLAN.md).
  These describe one to three categories, up to five optional interest phrases, shared semantic processing,
  immutable daily archives, and a $15/day total Gemini ceiling. Milestone 0 accounting is implemented locally;
  production cutover and evaluation activation remain pending. Semantic matching and immutable feeds are not
  implemented. Milestone 1's isolated [runner and review workflow](api/evaluation/README.md)
  now includes 128 candidate pairs across eight interests, calibration/held-out splits,
  three complete archived RSS sets, structured validation, cached responses and measured-capacity/gate tooling.
  Human labels, owner rubric approval, live relevance/token/latency/cost measurements and the gate decision
  remain pending. Owner requested offline preparation while production accounting is inactive.
  No paid evaluation or production change has occurred. Read the plan's milestone 1 evidence before continuing.
  Session ended with the goal blocked on operational accounting and human/live evidence;
  use the latest [worklog handoff](docs/WORKLOG.md) to resume next session.
- [ROADMAP.md](docs/ROADMAP.md) records broader product direction, including the future feedback learning loop.
  Semantic-interest planning in the October 6 worklog is newer than the roadmap's active-work introduction.

## Known behavior to account for

- Public and per-category paths independently fetch overlapping RSS feeds. Deduplication within one fetch
  method does not mean one fetch per category across the whole pipeline.
- Archives use current category selections, not historical preference snapshots.
- RSS failure can return the same empty list as a successful empty feed. LLM batch failures can yield partial
  or empty output; legacy exception handling can let the process exit successfully despite publishing failure.
  Accounting/quota failures now stop with a nonzero status, preserving completed summary output when available.
  Check generated artifacts and logs, not exit status alone.
- Public posts use the process-local date; category feeds explicitly use America/New_York.
- Category replacement uses an autocommit DB connection; the delete/insert sequence is not currently atomic.
- Older documentation is incomplete: `app/README.md` still describes a skeleton despite implemented features.
  Commented-out OpenAI/PDF code is legacy, not the active summarization path.

## Deployment context

[docker-compose.prod.yml](docker-compose.prod.yml) defines API, app, Jekyll, nginx, and certbot services.
[.github/workflows/deploy.yml](.github/workflows/deploy.yml) tests both Python components, builds GHCR images,
and deploys main-branch pushes through the production environment gate.
[scripts/deploy-paperpulse.sh](scripts/deploy-paperpulse.sh) is the repository deployment script.
The [systemd timer](systemd/paperpulse-daily.timer) schedules publishing at 6am America/New_York with
up to five minutes of jitter; the service currently allows 30 minutes.

The worklog records Hetzner migration as complete, confirmed by the owner on 2026-10-05. Current main
includes PR #53's restart policies, web-only deployment, and checked SQLite backups;
see [Hetzner operations](docs/HETZNER_OPERATIONS.md). Older DigitalOcean runbooks still contain historical
hosting instructions. Before operational work, compare installed scripts, Compose configuration, and timers
with the repository; do not infer live state from local files. API and app images copy only their respective Python directories,
so pipeline code cannot assume app modules or OAuth configuration are available.

Keep this guide concise and current under the maintenance rule in [AGENTS.md](AGENTS.md).
