# Worklog

## Session: 2026-06-03 → 2026-06-06 (CI/CD pipeline + OS upgrade)

### Worked on
Setting up automated CI/CD for ArXivSum: push-to-main → CI builds → deploy to droplet. Branch: `feat/ci-cd-pipeline`.

### Completed

**Step 1: containerize the API** (commit `6e7847d`)
- Added `get_secret()` helper in `api/settings.py` that reads `/run/secrets/<name>` first, falls back to `os.getenv()` for local dev
- Switched `main.py` to use it for `GEMINI_API_KEY`
- Rewrote `api/Dockerfile` (was a half-baked Flask template) — Python 3.11, `python -m api.main` entrypoint
- Added `api` service to `docker-compose.prod.yml` with Docker Compose secrets binding from `/var/lib/paperpulse/secrets/gemini_api_key`
- Dropped unused deps from `requirements.txt`: Flask, Flask-SQLAlchemy, gunicorn, psycopg2-binary
- Commented out unused PDF processing imports in `main.py` and `utils.py` with TODO markers
- 3 new pytest tests for `get_secret()`

**Step 2: CI builds and pushes images to GHCR** (commits `3162bf8`, `cc48127`, `25cd4fb`)
- New workflow `.github/workflows/deploy.yml` — runs tests, builds both images with git SHA + `latest` tags, pushes to GHCR
- Pushes only on `main`; PRs and `workflow_dispatch` run test+build without pushing
- Fixed pre-existing `test_create_blogpost` that depended on `PROJECT_DIR` being set in env
- Verified end-to-end: temporarily added feat branch to push triggers, watched workflow succeed, both images appeared in GHCR, reverted temp triggers

**Step 3: server-side secrets**
- `/var/lib/paperpulse/secrets/gemini_api_key` installed on droplet, root-owned, `chmod 600`
- Directory `chmod 700`
- (User ran this manually following the runbook)

**Step 4: deploy script + ROLLBACK.md** (commit `57afc80`)
- Switched `docker-compose.prod.yml` to `image:` references (no more `build:` in prod)
- `scripts/deploy-paperpulse.sh` — takes git SHA, does `git reset --hard origin/main`, pulls images, recreates containers, prunes layers, optionally runs pipeline one-shot
- `ROLLBACK.md` — procedures for image-tag rollback, first-deploy special case, dry-run rollback

**Unplanned: OS upgrade**
- Discovered droplet was on Ubuntu 24.10 (EOL since July 2025); apt repos were 404'ing
- Upgraded in place 24.10 → 25.10 via `do-release-upgrade` (after pointing sources to `old-releases.ubuntu.com`)
- Survived an SSH connection drop mid-upgrade (the upgrade tool's screen session kept going)
- Installed Docker Compose V2 plugin via Docker's official apt repo
- Brought old stack back up; production is back online on the upgraded OS

### Decisions made
- App secrets via Docker Compose file-based secrets (host file mounted at `/run/secrets/<name>`), not Swarm secrets. Cheap to migrate later if needed; no code changes required.
- Deploy script does `git fetch + git reset --hard origin/main`, not `git pull`. Deterministic. Untracked files (daily generated posts) survive.
- `MIXPANEL_TOKEN` deferred — still set via `${MIXPANEL_TOKEN}` env var, not Compose secrets. Low-stakes since it's client-side anyway.
- Dry-run test before merging was attempted but didn't complete due to OS upgrade priority shift. Skipping in favor of post-merge testing with rollback procedures in place.
- 25.10 is not LTS (EOL ~July 2026). Plan a fresh-droplet migration to 24.04 LTS as a separate session.

### Next session priorities
- Step 5: create restricted `deploy` user on droplet, wire SSH keys into GitHub Actions
- Step 6: replace cron with systemd timer that invokes `docker compose run --rm api`
- Step 7: cleanup — rotate Gemini and Mixpanel keys (assume old `.env` values are compromised), remove old `.env` files from droplet, set Gemini spend cap
- Set up branch protection on `main` (require PR + status checks)
- Delete the feature-branch SHA-tagged test images from GHCR
- Plan migration from 25.10 to a fresh 24.04 LTS droplet (separate session)

---

## Session: 2026-06-03 (continued — part 2)

### Worked on
Cleanup, dependency hygiene, and content fixes after the RSS/Gemini migration.

### Completed

**Ruby gem security fixes**
- Updated `addressable` 2.8.1 → 2.9.0 and `rexml` 3.3.9 → 3.4.4 via `bundle update` inside the Jekyll Docker container
- Fixes Dependabot alerts #9 (REXML DoS) and #11 (Addressable ReDoS); will close when branch is merged to main

**Markdown heading fix**
- Root cause: `COMBINE_PROMPT` instructed LLM to write "Theme N:" without `##`, stripping the heading markers from the per-batch summaries
- Fix: updated `COMBINE_PROMPT` to explicitly require `## Theme N:` format
- Verified with re-run: headings now render as bold H2 in the blog

**Removed OpenAI dependency**
- Commented out `summarize_paper`, `_create_and_run_thread`, `_combine_paper_summaries` in `agent.py` with a TODO for full removal in a later commit
- Removed `import openai` from `agent.py` and `main.py`
- Added `google-genai==2.7.0` and `PyMuPDF==1.27.2.3` to `requirements.txt`

**What's New page**
- Added v1.03 entry: RSS feeds, Gemini, inline paper linking

**README**
- Updated to reflect Gemini (was OpenAI), RSS feeds (was search API), correct run commands (`PYTHONPATH=. .venv/bin/python -m api.main`), and updated env vars (`GEMINI_API_KEY`)

### Decisions made
- `summarize_paper` commented out rather than deleted — preserves the OpenAI RAG approach for potential future use with a different LLM

### Next session priorities
- Delete `summarize_paper` and related OpenAI methods fully (TODO already in code)
- Set up cron job in prod Docker config to run the pipeline daily
- Investigate whether `MIXPANEL_TOKEN` tracking is wired up correctly for the new blog post format

---

## Session: 2026-06-03

### Worked on
Refactoring the paper retrieval pipeline and LLM integration.

### Completed

**Paper retrieval — switched to RSS feeds**
- Investigated arXiv search API 429/503 errors; attempted OAI-PMH as replacement
- Debugged OAI-PMH: `ListRecords` verb times out on all queries regardless of date range or category size; only static verbs (`Identify`, `ListSets`) work
- Root cause: arXiv OAI-PMH docs state it does not support selective harvesting by date; our `from`/`until` params caused server-side timeouts
- Replaced `ArxivClient` with RSS-based implementation (`rss.arxiv.org/rss/{category}`)
- RSS feeds are a complete daily batch — one request per category, no pagination
- Added date filtering: keeps only items matching the most recent `pubDate` in the feed, guarding against mixed-date edge cases
- All changes on branch `refactor/oai-pmh-migration`

**LLM — switched from OpenAI to Gemini**
- OpenAI key hit quota; switched `Agent` to use `google-genai` SDK
- Model: `gemini-3.1-flash-lite`
- Added `GEMINI_API_KEY` env var
- Added 30s sleep between LLM batches to respect free-tier token-per-minute limit (250k tokens/min)

**Paper linking — fixed zero-link problem**
- Root cause: `add_markdown_links` did post-hoc regex matching of LLM output against paper titles; LLM never mentioned titles verbatim so nothing matched
- Fix: pass `**URL:**` for each paper in the prompt; instruct LLM to output `[Title](url)` links inline
- Removed `add_markdown_links` call from pipeline; LLM now handles linking directly
- Blog posts now contain clickable links to every paper mentioned

### Decisions made
- OAI-PMH abandoned — server-side timeouts are not fixable from the client; RSS is the right tool for daily new-paper harvesting
- Gemini free tier has a 250k token/minute limit; 30s inter-batch sleep is sufficient for current paper volumes (~900 papers → 4 batches)
- Inline LLM linking is more robust than post-hoc regex matching and requires no additional API calls

### Next session priorities
- Remove unused `add_markdown_links` and related helpers from `utils.py`
- Set up cron job in prod Docker config to run the pipeline daily
- Investigate whether `MIXPANEL_TOKEN` tracking is wired up correctly for the new blog post format
