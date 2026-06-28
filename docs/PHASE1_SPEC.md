# Phase 1 Spec — Profiles + Personalized Feed

**Status:** Spec'd, not started
**Last updated:** 2026-06-08

## What we're shipping
Logged-in users sign in with Google, pick up to 5 categories from the full arXiv subcategory taxonomy (~150 subcategories across cs / stat / math / physics / q-bio / q-fin / eess / econ), and see a personalized daily feed composed of per-category summaries. The existing public Jekyll archive at `paperpulse.ukurup.com` is untouched. The personalized experience lives at `app.paperpulse.ukurup.com`.

## Goals
- Users can sign in via Google OAuth, pick categories, and see a daily feed limited to those categories.
- Zero impact to the existing public Jekyll archive — it continues to ship its current daily summary as today.
- No payments, email, or learning loops in Phase 1.
- Operationally additive — same droplet, same compose stack, new container + new subdomain.

## Non-goals (deferred — see `ROADMAP.md`)
- Like/dislike learning loop and feed personalization beyond category filtering.
- Free-text category input.
- Daily email digest.
- Archive of past personalized feeds (today only for MVP).
- Pricing tiers / Stripe.
- Full observability stack (Prometheus, Grafana).
- DB-backed content index / entitlement flags.
- Replacing Jekyll with a unified dynamic app.

## User flow (happy path)
1. User lands on `paperpulse.ukurup.com` (existing Jekyll archive). Header has a new "Sign in" link pointing to `app.paperpulse.ukurup.com`.
2. App subdomain redirects to Google OAuth.
3. Google redirects back with a code; app exchanges for tokens; session cookie set.
4. First-time users: forced onboarding page — pick 1–5 categories from the full arXiv subcategory taxonomy. Picker is grouped by archive (cs, stat, math, physics, q-bio, q-fin, eess, econ) with a search box. Submit.
5. Feed page: today's per-category summaries for the selected categories, concatenated, in a stable order (alphabetical by slug).
6. Settings page: change selected categories, sign out, delete account.

## Architecture
Two independent deployables on the same droplet, fronted by the existing nginx:

```
paperpulse.ukurup.com         (Jekyll static site, existing)
    nginx → blog container → static HTML

app.paperpulse.ukurup.com     (new FastAPI app)
    nginx → fastapi container → SSR HTML
                              ↓ reads SQLite
                              ↓ reads markdown content files

/var/lib/paperpulse/
    secrets/        (existing — Gemini key, plus new Google OAuth secret + session secret)
    content/        (new — per-category daily markdown blurbs; written by pipeline, read by app)
    db/             (new — SQLite DB + WAL files; written by pipeline + app)
```

The daily pipeline (existing systemd timer at 6am Eastern) is modified to:
- Continue generating the existing combined daily summary for the Jekyll archive (unchanged).
- Also generate per-category blurbs under `/var/lib/paperpulse/content/YYYY-MM-DD/<slug>.md`.
- Track its own runs in the `daily_runs` SQLite table.

## Stack

| Layer | Choice | Rationale |
|---|---|---|
| Web framework | FastAPI | Already in the Python stack; minimal new deps |
| Templates | Jinja2 | SSR, no JS framework needed |
| Auth | Authlib (Google OAuth 2.0 / OpenID Connect) | Standard, maintained, handles state + PKCE |
| Session | Starlette `SessionMiddleware`, HttpOnly + Secure + SameSite=Lax cookie | Sufficient for browser-based login; no JWT needed |
| DB | SQLite in WAL mode, persistent volume | Right-sized for current scale; backup-friendly |
| LLM | Existing Gemini Flash Lite via `google-genai` | Unchanged |
| Container | New `app` service in `docker-compose.prod.yml` | Same droplet, fronted by existing nginx |
| TLS | Existing Certbot, SAN-extended to include `app.paperpulse.ukurup.com` | Same renewal path |

## Data model (SQLite)

```sql
PRAGMA journal_mode = WAL;

CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  google_sub TEXT NOT NULL UNIQUE,           -- stable Google account ID; join on this, not email
  email TEXT NOT NULL,                       -- may change over time
  display_name TEXT,
  picture_url TEXT,
  created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  deleted_at TEXT                            -- soft delete
);
CREATE INDEX idx_users_email ON users(email);

CREATE TABLE categories (
  slug TEXT PRIMARY KEY,                     -- e.g. 'cs.LG'
  display_name TEXT NOT NULL,                -- e.g. 'Machine Learning'
  description TEXT,
  rss_url TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE user_categories (
  user_id INTEGER NOT NULL,
  category_slug TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  PRIMARY KEY (user_id, category_slug),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (category_slug) REFERENCES categories(slug)
);

CREATE TABLE daily_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_date TEXT NOT NULL,                    -- e.g. '2026-06-07' (Eastern)
  started_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL,                      -- 'running' | 'success' | 'failed'
  error_message TEXT,
  categories_completed INTEGER NOT NULL DEFAULT 0,
  categories_total INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_daily_runs_date ON daily_runs(run_date);
```

Notes:
- `users.google_sub` is the authoritative join key for OAuth, not email.
- `users.deleted_at` is soft delete; a nightly purge can hard-delete after a grace period if desired.
- `categories` is seeded once on first deploy from a static list committed in the repo. The seed covers the full arXiv subcategory taxonomy (~150 entries). Idempotent re-seed on app startup so adding new arXiv categories later is a one-line config bump.
- 5-category cap is enforced at the application layer when inserting into `user_categories`.
- **Category popularity is queryable from `user_categories`.** Example: `SELECT category_slug, COUNT(*) AS users FROM user_categories WHERE user_id IN (SELECT id FROM users WHERE deleted_at IS NULL) GROUP BY category_slug ORDER BY users DESC;`. This gives a point-in-time snapshot of "which categories are most popular." Historical popularity (track adds/removes over time, e.g. churn per category) is NOT captured by this schema — if we want it, add an append-only `user_category_events` table later. Defer that until Phase 2 / when we actually need a trend.

## Content storage layout

```
/var/lib/paperpulse/content/
    2026-06-07/
        cs.LG.md
        cs.AI.md
        cs.CL.md
        cs.CV.md
        cs.IR.md
        ...
    2026-06-08/
        ...
```

Each file is a short markdown blurb (~3 paragraphs) summarizing the day's papers for that category with inline `[Title](arxiv_url)` links. If a category has zero new papers, write a placeholder file with a "no new papers today" line so the feed renders cleanly.

No DB-level index of these files in Phase 1; the app reads them on demand via the filesystem. Listing is `os.listdir(YYYY-MM-DD/)`.

## Pipeline changes (`api/`)

Current flow (single combined summary):
1. Fetch RSS for 4 categories.
2. Dedup + filter to most recent pubDate.
3. Single Gemini batch → combined thematic summary.
4. Write Jekyll post.

New flow (combined + per-category):
1. Compute the fetch list dynamically at run start: `SELECT DISTINCT category_slug FROM user_categories` UNION the fixed public-archive list (`cs.LG`, `cs.AI`, `cs.CL`, `cs.CV`, `stat.ML`). The fixed union guarantees the Jekyll archive keeps shipping even with zero users.
2. Fetch RSS for that union.
3. Dedup + filter to most recent pubDate.
4. Continue: combined thematic summary over the fixed public-archive subset → Jekyll post. Unchanged behavior.
5. New: for each category in the union, filter to papers tagged with that category and call Gemini with a per-category prompt → write `/var/lib/paperpulse/content/YYYY-MM-DD/<slug>.md`.
6. Delete raw RSS feed data (in-memory parsed feeds, any on-disk intermediates) once the per-category markdown is written. Don't persist raw feeds across runs. The Jekyll post + per-category markdown files are the only durable artifacts.
7. Insert/update `daily_runs` row with status throughout.

**Design call: cross-listed papers appear in every relevant category's daily blurb.** Reasoning: a cs.CV reader who picks only cs.CV expects to see all cs.CV-relevant work, including papers primarily filed under cs.LG. Duplication for users selecting overlapping categories is an acceptable trade-off.

Subtleties:
- Pipeline runtime now scales with `len(distinct selected categories ∪ fixed public-archive list)`, not a fixed count. At 50 distinct categories × 30s inter-batch sleep that's already >25 min. Likely need to raise the systemd timeout, parallelize the LLM calls (within Gemini rate limits), or both. Decide during implementation once we see real numbers — don't pre-optimize.
- If a category has zero new papers, skip the LLM call and write a placeholder file directly.
- Empty-category placeholder is also useful when an LLM call fails — fail open with a "today's summary unavailable, see the public archive" line.
- Raw RSS data is treated as ephemeral. No pickle cache in prod (already true), no JSON dumps left behind. The pipeline's persistent outputs are the Jekyll post, the per-category markdown files, and the `daily_runs` row.

## Deployment

New container `app` in `docker-compose.prod.yml`:
- Image: `ghcr.io/<user>/paperpulse-app:<sha>` built by CI like the existing API.
- Mounts:
  - `/var/lib/paperpulse/db` → `/data/db` (RW; SQLite + WAL files)
  - `/var/lib/paperpulse/content` → `/data/content` (RO from app's perspective)
  - `/var/lib/paperpulse/secrets` → `/run/secrets` (Docker Compose secrets pattern, matches existing API)
- API container also gets RW mounts on `db/` (for `daily_runs`) and `content/` (for writes).
- New secret files (root-owned, chmod 600):
  - `/var/lib/paperpulse/secrets/google_oauth_client_id`
  - `/var/lib/paperpulse/secrets/google_oauth_client_secret`
  - `/var/lib/paperpulse/secrets/session_secret`
- Healthcheck endpoint at `/healthz` (returns 200 if DB is reachable).
- Logs to stdout, captured by Docker / journald.

nginx:
- New server block for `app.paperpulse.ukurup.com`.
- Reverse-proxy to the app container.
- HTTPS-only; add `X-Robots-Tag: noindex` so the app is not indexed.
- Existing Certbot extended via SAN to include the new subdomain.

DNS:
- A record for `app.paperpulse.ukurup.com` pointing to the droplet.

Backups:
- Nightly systemd timer: hot-backup `/var/lib/paperpulse/db/paperpulse.sqlite` via `VACUUM INTO` (atomic, no lock contention with WAL writers) → upload to a **DigitalOcean Spaces** bucket (S3-compatible). Retain last 30 daily snapshots + last 12 monthly. Lifecycle rule on the bucket handles expiry.
- Backup script lives at `/usr/local/bin/paperpulse-backup` and uses `s3cmd` or `aws s3` (with Spaces endpoint) authenticated via an access key stored in `/var/lib/paperpulse/secrets/spaces_credentials` (chmod 600, root-owned).
- Tested restore drill before launch: download latest snapshot, open in `sqlite3`, run integrity check + sample queries.
- `/var/lib/paperpulse/content` regenerates daily; backups nice-to-have, not load-bearing.

## Security & privacy

OAuth setup (Google Cloud Console):
- Create GCP project, configure OAuth consent screen as "External."
- Scopes: `openid`, `email`, `profile`. No sensitive scopes → no Google verification required, but unverified-app interstitial is shown until verification is submitted.
- Authorized JavaScript origins: `https://app.paperpulse.ukurup.com`.
- Authorized redirect URIs: `https://app.paperpulse.ukurup.com/auth/google/callback` (exact match required).

Cookies:
- Session cookie: `HttpOnly`, `Secure`, `SameSite=Lax`.
- Cookie scope: `app.paperpulse.ukurup.com` only (the default; do **not** set the domain to the parent).
- Session secret: random 32+ bytes, loaded from `/run/secrets/session_secret`.

CSRF:
- Authlib handles OAuth `state` automatically when wired correctly.
- Add a CSRF token to all state-changing POST endpoints (settings update, account delete).

PII handling:
- Store: email, display name, picture URL, Google sub.
- Don't log emails or display names in application logs — user IDs only.
- Account deletion: soft delete on user request; nightly purge after grace period.

Privacy policy:
- Required by the OAuth consent screen. One-pager covering: what data is collected (email, profile basics), purpose (login + personalization), where stored (droplet in $REGION), retention (until account deletion), no third-party sharing.

## Gotchas
1. **"Unverified app" warning.** Basic scopes (`openid email profile`) do not require Google verification, but users see an interstitial warning until you submit for review. Acceptable for low-volume launch; submit for verification when growth warrants it. (I'm fairly confident about current Google policy here; worth a quick check against the latest docs before launch.)
2. **Redirect URI exact match.** Must match exactly including protocol, host, and path. Off-by-one trailing slash is the classic 30-minute debug.
3. **`google_sub` is stable, email is not.** Always join by `google_sub`. If email changes upstream, update the column but never key off email.
4. **Cookie domain trap.** Setting cookie domain to `.paperpulse.ukurup.com` would expose the session to the Jekyll site too — leave it scoped to the app subdomain only.
5. **Pipeline runtime balloon.** Runtime scales with the size of the dynamic fetch list. With 50+ distinct user-selected categories, current 30s inter-batch sleep blows past the 30-min systemd timeout. Plan to raise the timeout and/or parallelize within Gemini rate limits. Confirm with real numbers before launch.
6. **Cross-listed papers** appear in multiple categories' summaries by design. Users selecting many overlapping categories will see some duplication; acceptable.
7. **Raw feeds are ephemeral.** Don't persist raw RSS data across runs. Anything cached for debugging must be wiped at end-of-run. Avoids accidentally retaining paper metadata we never committed to keep.
8. **Empty-category days** for niche categories. Write a placeholder so the feed renders cleanly.
9. **Time zone for "today."** Pipeline runs at 6am Eastern. The app should determine "today" using `America/New_York` to match the file layout, not server UTC.
10. **SQLite write contention.** Pipeline writes `daily_runs`; app writes user data. WAL handles concurrent reads + one writer. Sanity-check it before launch.
11. **Backup before launch.** Even one user lost is bad. Backup + restore drill before sending the sign-up link.
12. **Logout doesn't kill the Google session.** Standard OAuth behavior; "Sign out" just kills the local session cookie. Worth a UX note if confusing.
13. **GDPR-minimum compliance.** Privacy policy + working account-delete is the floor. Not a full compliance review.
14. **Session secret rotation.** Rotating it logs everyone out. Plan a rotation policy or accept periodic forced logouts.

## Low-hanging fruit (cheap wins worth doing in Phase 1)
- `/healthz` endpoint (also satisfies Docker healthcheck).
- `X-Robots-Tag: noindex` + `robots.txt` blocking crawlers on the app subdomain.
- 404 / 500 templates that look like the rest of the app.
- Logged-in user's email/avatar shown in the header so login state is obvious.
- "No new content yet — pipeline runs at 6am Eastern" empty state on the feed when the date directory doesn't exist.
- Idempotent category seed at app startup, sourced from a static list committed in the repo.
- Pinned `requirements.txt` for the app; don't share venv with the pipeline.

## Sequencing (rough, solo-dev, evenings/weekends)
1. **Foundations** — FastAPI skeleton, SQLite schema + migrations, Authlib + Google OAuth round-trip with a localhost redirect URI. Local dev only.
2. **Onboarding + feed** — category picker page (with cap-of-5 enforcement), today's feed page reading from `/var/lib/paperpulse/content/`, settings page, account deletion.
3. **Pipeline changes** — seed full arXiv subcategory taxonomy into `categories` table; switch fetch list to `DISTINCT user_categories ∪ fixed public-archive list`; add per-category Gemini passes; write to `/var/lib/paperpulse/content/`; populate `daily_runs`; delete raw feed data at end-of-run. Measure runtime against the timeout and parallelize if needed.
4. **Deployment plumbing** — new subdomain DNS, nginx server block, Certbot SAN, new `app` service in `docker-compose.prod.yml`, persistent volumes, secrets, healthcheck. Manual deploy first; wire into existing CI/CD after.
5. **Pre-launch hardening** — backup + restore drill, privacy policy page, GCP OAuth consent screen configured for production, end-to-end dogfood.
6. **Soft launch** — invite-link to a small group; watch logs, fix issues, iterate before opening up.

## Open design questions (resolve during implementation; not blockers)
- Picker UI for ~150 subcategories. Lean: archive-grouped accordions (cs / stat / math / physics / q-bio / q-fin / eess / econ) with a search box. Confirm the archive list against current arXiv taxonomy before seeding.
- Per-category prompt structure. Start with a literal adaptation of the current combined-summary prompt scoped to one category, then iterate on output quality.
- Whether to keep the existing combined Jekyll summary indefinitely or eventually replace it with a "default" feed assembled from per-category content. Keep both for Phase 1.
