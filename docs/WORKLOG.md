# Worklog

## Session: 2026-06-28 (Phase 1 chunk 0 — app skeleton + OAuth + /goal prep)

### Worked on
Stood up the new FastAPI app at `app/` per the Phase 1 spec. End-to-end Google OAuth login working locally. Added test scaffolding, acceptance-criteria doc, and a `/goal` autonomy boundary doc to make the next chunks runnable under Claude Code's `/goal` mode. Fetched the full arXiv subcategory taxonomy.

### Completed

**App skeleton (`app/`, new top-level dir)**
- FastAPI + Jinja2 SSR + Authlib + SQLite (WAL, FK on). Files: `main.py`, `config.py`, `db.py`, `schema.sql`, `auth.py`, `routes.py`, `templates/{base,index}.html`, `requirements.txt` (pinned), `.env.example`, `README.md`.
- `schema.sql` is verbatim from the spec — users / categories / user_categories / daily_runs.
- `auth.py` does the OAuth round-trip and upserts users by `google_sub` (never by email).
- Settings are loaded from `app/.env` (separate from `api/.env`) at import time into a frozen dataclass; `DB_PATH` and `CONTENT_DIR` env-overridable with sensible defaults.
- `/healthz` returns 200 if DB is reachable.
- `.gitignore` updated: `app/.env`, `app/.venv/`, `app/paperpulse.sqlite*`, `docs/internal-readme.md`.

**End-to-end OAuth round-trip — verified locally**
- Google Cloud OAuth client created in the new "Google Auth Platform" UI (was reorganized from the older "OAuth consent screen" flow). Scopes: openid, email, profile. Test-user mode. Redirect URI: `http://localhost:8000/auth/google/callback`.
- Logged in successfully, came back as Unmesh / turingmachinesllc@gmail.com, user row upserted.

**Test scaffold (`app/tests/`)**
- `conftest.py` sets dummy OAuth env + tmpdir SQLite DB *before* any `app.*` import (config loads at import time, so order matters). Session-scoped `client` fixture using `TestClient`.
- `test_smoke.py` — two passing tests: `/healthz` returns ok, anonymous `/` renders with "Sign in with Google".
- Test command: `PYTHONPATH=. app/.venv/bin/pytest app/tests`.

**Acceptance criteria + autonomy boundary for `/goal`**
- `docs/PHASE1_CHUNKS.md` — chunks 0–3 broken into discrete, pytest-shaped acceptance criteria. Chunk 0 marked done; chunks 1–3 ready to drive `/goal` runs.
- `docs/GOAL_AUTONOMY.md` — in-scope (file edits under `app/` and `docs/`, local pytest, read-only git, localhost curl) vs hard-gated (git state changes, files outside `app/`/`docs/`, all external network, docker, ssh, destructive ops, secrets). Hard-gated steps still require explicit confirmation even mid-goal.

**arXiv taxonomy fetched + committed**
- `app/data/categories.json` — 155 subcategories across all archives (cs 40, math 32, physics 22, etc.), sorted by `(archive, slug)`. Each row has `slug`, `display_name`, `archive`, `description`, `rss_url`.
- RSS URL pattern (`https://rss.arxiv.org/rss/{slug}`) verified live for one dotted slug (`cs.LG`) and one bare slug (`quant-ph`) — both `HTTP 200 application/rss+xml`.
- Known imperfection: aliased slugs (e.g. `cs.NA` ↔ `math.NA`, `cs.SY` ↔ `eess.SY`, several others) are all retained. Picker UI in chunk 1 needs an alias-dedupe call.

### Decisions made
- **`app/` as a new top-level dir**, not nested under `api/` and not via renaming `api/` → `pipeline/`. Matches the spec's "don't share venv with pipeline" intent without import-path churn. Naming inconsistency (`api/` is really the pipeline) accepted.
- **`app/.env` separate from `api/.env`** — keeps the two deployables decoupled and matches the spec.
- **`DB_PATH` env-configurable, default `app/paperpulse.sqlite`** — makes prod path (`/data/db/paperpulse.sqlite`) a one-env-var switch.
- **Styling deferred** — dogfood with unstyled HTML. Theme port (Jekyll → app) happens as one focused pass once features are in place. Unmesh may pick a different design entirely.
- **No on-the-fly dependency-injection refactor for `current_user`** in this chunk. Tests for auth-gated endpoints land in chunk 1 along with a proper `Depends()`-based `current_user` so test overrides are clean. Deliberately deferred to avoid scope creep here.
- **Test scaffold uses one session-scoped DB** for now. Per-test reset fixture lands in chunk 1 when there's stateful data worth isolating.

### Open follow-ups not blocking
- Upgrade Claude Code to ≥ v2.1.139 to enable `/goal` (current install returned "Unknown command").
- Two FastAPI deprecation warnings surfaced by pytest:
  - `@app.on_event("startup")` → switch to lifespan handler
  - `TemplateResponse(name, {"request": request, ...})` → switch to new `(request, name, ...)` signature
  Both trivial; folding into chunk 1.
- Alias-dedupe strategy for the category picker (chunk 1 design call).
- Re-verify a few non-cs RSS URLs (e.g. `q-bio.NC`) before depending on them in the pipeline (chunk 4).
- DigitalOcean Spaces backup setup still untouched — flagged as Track A from the access-setup walkthrough.
- Privacy policy page (required to move OAuth consent screen out of Testing mode) — Phase 1 launch concern.
- `docs/internal-readme.md` now gitignored (closing the prior open follow-up).

### Next session priorities
1. Run `/goal` against chunk 1 once Claude Code is upgraded. Goal condition: `pytest app/tests passes including new tests covering every acceptance criterion in chunk 1 of docs/PHASE1_CHUNKS.md`.
2. Before launching: tighten chunk 1 acceptance criteria if anything reads vague on a re-skim.
3. Add the `current_user` dependency + test override fixture as the first step of chunk 1.
4. Address the two deprecation warnings as part of chunk 1.

---

## Session: 2026-06-08 (prod 502 — nginx stale upstream IP)

### Worked on
Diagnosed and fixed a prod 502 outage on `paperpulse.ukurup.com`.

### Completed

**Diagnosed: nginx caching stale blog container IP**
- Symptom: `502 Bad Gateway` site-wide. nginx logs: `connect() failed (113: Host is unreachable) while connecting to upstream, upstream: "http://172.18.0.2:4000/"`.
- Both `blog` and `nginx` containers were up and on the same Docker network (`arxivsum_web`). `docker exec arxivsum-nginx-1 wget http://blog:4000/` worked fine — DNS resolved `blog` to `172.18.0.4`, not `172.18.0.2`.
- Root cause: nginx was up 46h, blog had been recreated 22h ago by the daily deploy. nginx's `proxy_pass http://blog:4000` resolves the hostname once at config-load time and caches the IP forever. When blog got a new IP after recreate, nginx kept proxying to the dead one.

**Fix (`fix/nginx-runtime-resolver`, PR merged)**
- Added `resolver 127.0.0.11 valid=10s ipv6=off;` (Docker's embedded DNS) + variable `proxy_pass` (`set $blog_upstream blog:4000; proxy_pass http://$blog_upstream;`) so nginx re-resolves at request time instead of caching at startup.
- Added `proxy_connect_timeout 5s` + 60s read/send timeouts so a dead backend fails fast instead of defaulting to 60s connect.
- After auto-deploy, still 502 — because `docker compose up -d` doesn't recreate nginx when only the bind-mounted config changes on disk. One-time `docker compose restart nginx` on the droplet loaded the new config; future recreates handled automatically now.

### Decisions made
- **Variable-based `proxy_pass` over `depends_on: [blog]` on nginx.** `depends_on` only controls startup order, not recreate ordering, so it doesn't fix recreate-time IP churn. Runtime resolver removes the deploy coupling entirely.
- **Kept scheme outside the variable** (`set $blog_upstream blog:4000; proxy_pass http://$blog_upstream;` rather than putting `http://` inside the variable) — avoids subtle URI-rewrite bugs if a path is ever added to the proxy_pass target.
- **No follow-up PR to auto-restart nginx on config change in the deploy script.** nginx config rarely changes; not worth the deploy-script complexity.

### Next session priorities
Unchanged from prior session: DO Spaces backup setup, Phase 1 foundations (FastAPI + SQLite + Authlib), seed arXiv taxonomy.

### Open follow-ups not blocking
- Deploy script doesn't restart nginx when `nginx/nginx.conf` changes on disk. Known gap; one manual `docker compose restart nginx` after such a change. Acceptable given how rarely the file changes.

---

## Session: 2026-06-07 → 2026-06-08 (Phase 1 spec + ops fix + chore PR)

### Worked on
Planning Phase 1 (Google login + personalized feeds), diagnosing a missing daily summary, and a small chore PR for doc reorg + content updates.

### Completed

**Phase 1 spec (`docs/PHASE1_SPEC.md`) + roadmap (`docs/ROADMAP.md`)**
- Full spec for profiles + per-category feeds: Google OAuth via Authlib, FastAPI + Jinja2 SSR, SQLite (WAL) on a persistent volume, new `app.paperpulse.ukurup.com` subdomain, per-category markdown blurbs at `/var/lib/paperpulse/content/YYYY-MM-DD/<slug>.md`, Jekyll archive untouched.
- Data model: `users` (joined by `google_sub`, soft delete), `categories`, `user_categories` (5-cap enforced at app layer), `daily_runs` ops table. Popularity query example in spec.
- Roadmap captures Phase 2 (like/dislike learning loop, free-text categories with own summaries, daily email digest, hover-to-explain abstracts, pricing tiers via Stripe) and infra backlog (Prometheus, content index, Postgres migration).

**Missing daily summary on 2026-06-07 — diagnosed + fixed (PR merged)**
- Symptom: systemd timer fired but no blog post written; container exited 0 in 19s with no logs visible from host.
- Root causes: (a) cs.LG RSS feed legitimately empty Sun morning (verified via WebFetch, not the Mon-Fri myth I initially overclaimed), (b) pipeline logs lived only inside the `--rm` run container so they vanished, (c) "no papers" path logged at error level and exited silently.
- Fix on `fix/empty-feed-handling` branch: added `./logs:/app/logs` mount + `LOG_DIR` env to `api` service; switched logging to `FileHandler + StreamHandler(sys.stderr)` so journald captures output; downgraded "no papers" to info-level skip. Merged to main; CI moved `latest` to the new SHA.

**Chore PR (`chore/docs-reorg-blog-readme`, merged)**
- Moved all root-level docs to `docs/` (PHASE1_SPEC, ROADMAP, WORKLOG, ERRORS, DROPLET_SETUP, CICD_PLAN, ROLLBACK). Verified no broken refs in CI/scripts/systemd/nginx.
- Added `stat.ML` to `RSS_CATEGORIES` in `api/settings.py`.
- What's New v1.04 entry listing the full updated category set.
- README intro updated for the new category list; replaced stale cron line with a Production deployment section pointing at CI/CD + systemd timer + `docs/` runbooks.

**Phase 1 blockers resolved (spec updated)**
- **Category scope:** free tier picks 5 from full arXiv subcategory taxonomy (~150), not a curated 20 cs.*. Picker grouped by archive (cs/stat/math/physics/q-bio/q-fin/eess/econ) with search.
- **Pipeline fetch list:** dynamic — `SELECT DISTINCT category_slug FROM user_categories` UNION fixed public-archive list (`cs.LG`, `cs.AI`, `cs.CL`, `cs.CV`, `stat.ML`). Public archive keeps shipping with zero users.
- **Raw feeds ephemeral:** added rule to delete RSS data after per-category markdown is written. Updated pipeline section + gotchas + sequencing.
- **Cross-listed papers:** confirmed — appear in every relevant category's blurb.
- **Backups:** locked in DO Spaces, `VACUUM INTO` snapshot, 30 daily + 12 monthly retention via lifecycle rules, credentials at `/var/lib/paperpulse/secrets/spaces_credentials`.

### Decisions made
- **Free-text categories deferred to Phase 2.** Considered moving them into Phase 1 with LLM topic→category mapping; rejected on YAGNI + scope grounds. Phase 1 stays a category picker, just over a much bigger universe.
- **5-cap stays at 5 across the bigger taxonomy.** Cleaner than per-archive limits. Tier differentiation belongs in Phase 2 with Stripe.
- **`daily_runs` table** included for ops visibility now (rather than waiting for a full Prometheus stack).
- **`VACUUM INTO` over `.backup`** for SQLite snapshots — atomic, no lock contention with WAL writers.
- **Backup runs from droplet (systemd timer)**, not CI — fewer moving parts. Open for revisit if we want off-host attestation.

### Next session priorities
- Set up the DO Spaces bucket (region, name, scoped access key, lifecycle rules). Then write `scripts/paperpulse-backup.sh`, systemd unit + timer, and `docs/BACKUP.md` runbook.
- Begin Phase 1 implementation per spec sequencing — start with foundations (FastAPI skeleton, SQLite schema + migrations, Authlib + Google OAuth on localhost).
- Fetch the live arXiv taxonomy to seed `categories` (one-time pull, commit the list).

### Open follow-ups not blocking
- Decide whether `docs/internal-readme.md` should be `.gitignore`'d (currently just untracked).
- Confirm droplet region before creating the DO Space (lowest-latency match).
- Pipeline runtime under the new dynamic fetch list — measure once we have real per-category Gemini passes; may need to raise systemd timeout or parallelize.

---

## Session: 2026-06-06 (CI/CD landing + systemd timer)

### Worked on
Landing the CI/CD pipeline end-to-end and replacing the broken cron with a systemd timer.

### Completed

**Step 5: deploy job + droplet runbook completion**
- Added `deploy` job to `.github/workflows/deploy.yml` — runs after `build` on push to main, gated by `production` environment, raw SSH with pinned known_hosts
- Deploy script: accepts SHA from `$1` or `$SSH_ORIGINAL_COMMAND`, strict 40-char hex validation
- Fixed `sha-` prefix on image tags in workflow so bare SHA matches deploy script + rollback doc expectations
- DROPLET_SETUP.md runbook executed on droplet: `deploy` user with locked password, authorized_keys with forced command + restrictions, sudoers fragment validated by visudo, deploy script installed at `/usr/local/sbin/deploy-paperpulse`
- Three GH Actions secrets configured: `DEPLOY_SSH_PRIVATE_KEY`, `DROPLET_HOST`, `DROPLET_KNOWN_HOSTS`
- `production` environment configured with required-reviewer protection
- Manual SSH test from laptop verified: forced command + sudo + validation + git fetch over HTTPS all work
- Branch protection on main: PR required, status checks required, 0 approvals (solo-dev exception)

**First auto-deploy**
- PR #33 merged, workflow ran on main
- First attempt: `deploy` job failed with "Host key verification failed" — `DROPLET_KNOWN_HOSTS` secret needed refresh
- After fixing: re-ran failed jobs, full pipeline went green end-to-end
- Production stayed up throughout

**Step 4: systemd timer (PR #34)**
- `systemd/paperpulse-daily.service` — oneshot unit running `docker compose run --rm api python -m api.main`, 30 min timeout, journal logging
- `systemd/paperpulse-daily.timer` — fires at 6am Eastern year-round (`OnCalendar=*-*-* 06:00:00 America/New_York`), `Persistent=true` for missed-run catch-up
- DROPLET_SETUP.md step 10 added: crontab removal, unit install, enable/start, verification, useful inspection commands
- Manual fire on droplet ran successfully — `2026-06-06-daily-summary.markdown` (7380 bytes) generated, journal logged cleanly

**Unplanned: Ubuntu 24.10 → 25.10 in-place upgrade**
- Discovered apt repos 404'ing because 24.10 is EOL
- Repointed sources to `old-releases.ubuntu.com`, ran `do-release-upgrade` (in screen session that survived an SSH drop)
- Picked "keep local" for the sshd_config conftest after diffing — only safe additions (comments, AcceptEnv tweaks)
- After upgrade: re-installed Docker Compose V2 plugin from Docker's official apt repo, brought blog/nginx/certbot stack back via `docker compose up -d --build`

### Decisions made
- **Solo-dev branch protection**: keep "Require pull request" + "Require status checks" enabled, drop "Require approvals" to 0 via unchecking the sub-checkbox. PRs still enforce CI gate; no impossible-self-review block.
- **Image tag format**: bare 40-char SHA (no `sha-` prefix). Cleaner mapping between CI output, deploy script input, and rollback procedures.
- **systemd timer timezone**: `America/New_York` in `OnCalendar` rather than UTC, so 6am Eastern stays 6am Eastern across DST shifts.
- **Defer MIXPANEL_TOKEN cleanup**: still passed as `${MIXPANEL_TOKEN}` env var, low-stakes since it's client-side anyway. Real secrets discipline reserved for GEMINI_API_KEY.
- **Remote URL on droplet**: switched from `git@github.com:...` to `https://github.com/...` for `/var/www/arxivsum`. Public repo + HTTPS = no auth needed on droplet. Local laptop remote stays SSH (was accidentally malformed mid-session and got fixed).

### Next session priorities
- **Step 7 cleanup** — rotate Gemini key (then put new value in `/var/lib/paperpulse/secrets/gemini_api_key`), rotate Mixpanel token, set Gemini spend cap, remove old `.env` files from droplet
- **Delete leftover test images from GHCR**: feature-branch SHA-tagged `paperpulse-api` and `paperpulse-blog` versions from `cc48127...` and `3162bf8...`
- **Tomorrow morning**: confirm the 6am Eastern systemd timer fires automatically and publishes the daily summary without manual intervention

### Open follow-ups not blocking
- `api/utils.py` and `api/main.py` still have commented-out PDF processing code with TODO. Decide whether to restore PDF features or delete the dead code.
- Consider whether the dry-run workflow path is still useful (we skipped using it for the actual rollout)

---

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
