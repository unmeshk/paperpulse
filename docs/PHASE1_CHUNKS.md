# Phase 1 — chunked acceptance criteria

Each chunk lists a single verifiable end state, broken into pytest-shaped
assertions. Used as the source of truth for `/goal` runs.

Test command (from repo root):
```
PYTHONPATH=. app/.venv/bin/pytest app/tests
```

---

## Chunk 0 — Skeleton (DONE)

Acceptance:
- [x] `GET /healthz` returns 200 `{"status": "ok"}`
- [x] `GET /` returns 200 with "Sign in with Google" for an anonymous visitor
- [x] Google OAuth round-trip works against `http://localhost:8000` (manual verification)
- [x] User row upserted on first login (manual: confirmed via dogfood)

---

## Chunk 1 — Category seed + onboarding picker (DONE)

**Goal:** A logged-in user can pick 1–5 categories and have them persisted.

Acceptance:
- [x] `app/data/categories.json` exists, committed, contains >= 100 arXiv subcategories with `slug`, `display_name`, `archive` (cs/stat/math/...), `rss_url`.
- [x] On `init_db()`, `categories` table is seeded from that JSON; re-running is idempotent (no duplicate rows, no errors).
- [x] `SELECT COUNT(*) FROM categories WHERE active = 1` matches the JSON row count.
- [x] `GET /onboarding` returns 200 for a logged-in user, 302 → `/auth/login` for anonymous.
- [x] `GET /onboarding` HTML contains all archives as group headers and a search input.
- [x] `POST /onboarding` with body `slugs=["cs.LG","cs.AI","cs.CL","cs.CV","stat.ML"]` for a logged-in user returns 302 → `/`, and `user_categories` has exactly 5 rows for that user.
- [x] `POST /onboarding` with 6 slugs returns 400 (cap-of-5 enforced server-side).
- [x] `POST /onboarding` with an unknown slug returns 400.
- [x] `POST /onboarding` for an anonymous request returns 401 or 302 → `/auth/login`.
- [x] After successful POST, `GET /` for that user redirects to `/feed` (or renders the feed placeholder — TBD when chunk 2 lands; for now just confirms session persists).
- [x] CSRF token required on `POST /onboarding`; missing/invalid token returns 403.

Test scaffolding required:
- An auth-injection fixture (dependency-override on `current_user`) so tests don't have to run a real OAuth round-trip. This is the place to add it.
- A per-test DB reset fixture (truncate `users` and `user_categories` between tests) so test order doesn't matter.

---

## Chunk 2 — Feed page (DONE)

**Goal:** A logged-in user with selected categories sees today's per-category
blurbs, rendered from markdown to HTML, in alphabetical order by slug.

**Decisions (locked):**
- **Renderer:** `markdown-it-py`, pinned in `app/requirements.txt`, configured
  with raw HTML disabled (`html=False`) so LLM-generated blurbs can't inject
  markup. (New dependency — install is pre-authorized for the `/goal` run.)
- **No-categories user:** `GET /feed` redirects (302) to `/onboarding`.
- **`/` routing (wires the chunk 1 TBD):** logged-in user with categories → 302
  to `/feed`; logged-in without categories → 302 to `/onboarding`; anonymous →
  landing page (unchanged).
- **"Today":** `datetime.now(ZoneInfo("America/New_York")).date()` (stdlib
  `zoneinfo`, no dep). Content path is `CONTENT_DIR/<YYYY-MM-DD>/<slug>.md`.

Acceptance:
- [x] Anonymous `GET /feed` returns 302 → `/auth/login`.
- [x] Logged-in user with no selected categories: `GET /feed` returns 302 → `/onboarding`.
- [x] Logged-in user with selected categories: `GET /feed` returns 200.
- [x] Response contains one section per selected category, ordered alphabetically by slug, each section headed by the category (slug and/or display_name).
- [x] Each section renders the HTML produced from `CONTENT_DIR/<today>/<slug>.md`: a source `## Theme 1` appears as an `<h2>`, and a source `[Title](url)` appears as `<a href="url">Title</a>`.
- [x] XSS guard: a source file containing a literal `<script>…</script>` is not emitted as an executable tag (raw HTML escaped/stripped by the `html=False` renderer config).
- [x] Missing single file: if a selected category's `<today>/<slug>.md` is absent, that section shows a "no new papers today" placeholder; page is still 200.
- [x] Missing day dir: if `CONTENT_DIR/<today>/` does not exist, the page shows a "pipeline runs at 6am Eastern" empty state; page is still 200.
- [x] "Today" is `America/New_York`, not server UTC: the feed reads from the directory named by the NY date. (Test: write a file under the NY-today dir, assert it renders.)
- [x] `GET /` for a logged-in user with categories returns 302 → `/feed`; with no categories returns 302 → `/onboarding`; anonymous still renders the landing page with "Sign in with Google".

Test scaffolding required:
- `conftest.py`: set `CONTENT_DIR` to a tmpdir **before** any `app.*` import (same constraint as `DB_PATH` — config freezes at import time).
- A content-writing fixture (e.g. `write_blurb(slug, body, date=<NY today>)`) that creates `CONTENT_DIR/<date>/<slug>.md`.
- A helper to assign categories to the test user directly via DB insert into `user_categories`, so feed tests don't depend on the onboarding POST flow.
- Reuse `auth_client`, `db_user`, `reset_db` from chunk 1. Extend `reset_db` (or add a sibling) to also clear `CONTENT_DIR` between tests.

Notes / follow-ups:
- Actual per-category `.md` files come from **chunk 4** (pipeline, `api/`, hard-gated). Chunk 2 is verified entirely with fixture files under `CONTENT_DIR`.
- Alias-dedupe in the picker is still open from chunk 1 — not a chunk 2 blocker.

---

## Chunk 3 — Settings + account deletion

Acceptance (draft):
- [ ] `GET /settings` shows current categories.
- [ ] `POST /settings` updates `user_categories` (full replace, not append).
- [ ] `POST /settings/delete-account` soft-deletes the user (`deleted_at` set), clears session.
- [ ] After soft delete, `GET /` shows anonymous view.
- [ ] CSRF tokens on both POSTs.

---

## Chunk 4 — Pipeline integration (per-category blurbs)

Out of `app/` scope — touches `api/`. Hard-gated (see `docs/GOAL_AUTONOMY.md`).
