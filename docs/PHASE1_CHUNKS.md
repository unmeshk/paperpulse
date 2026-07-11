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

## Chunk 3 — Settings + account deletion (DONE)

**Goal:** A logged-in user can change their categories and delete their account.

**Decisions (locked):**
- Reuse chunk 1–2 building blocks: `current_user` dep, CSRF helpers,
  `_user_category_slugs`, `_grouped_categories`, and the test fixtures.
- The settings picker is the onboarding picker with the user's current slugs
  pre-checked, plus a separate delete-account form.
- `POST /settings` success → 302 → `/feed` (same as onboarding).
- Delete is a **soft delete**: set `users.deleted_at`, clear the session, keep
  the row and the user's `user_categories` rows. `current_user` already filters
  `deleted_at IS NULL`, so the account reads as gone.

Acceptance:
- [x] `GET /settings` returns 200 for a logged-in user and the user's currently
      selected slugs are rendered as checked; 302 → `/auth/login` for anonymous.
- [x] `POST /settings` with a valid 1–5 slug set + CSRF full-replaces
      `user_categories` for that user and returns 302 → `/feed`.
- [x] `POST /settings` with 6 slugs → 400; with an unknown slug → 400.
- [x] `POST /settings` with missing/invalid CSRF → 403; anonymous → 401 or 302 → `/auth/login`.
- [x] `POST /settings/delete-account` with CSRF sets `users.deleted_at`, clears
      the session, returns 302 → `/`.
- [x] `POST /settings/delete-account` with missing/invalid CSRF → 403; anonymous → 401 or 302.
- [x] After delete, `GET /` renders the anonymous landing ("Sign in with Google").
- [x] After delete, the `users` row still exists with `deleted_at` set (soft, not hard, delete).

Test scaffolding: reuse `auth_client`, `db_user`, `assign_categories`,
`reset_db`, and the `_get_csrf` helper. No new dependencies.

Test command: `PYTHONPATH=. app/.venv/bin/pytest app/tests`

---

## Chunk 4 — Pipeline integration (per-category blurbs) (DONE)

Touches `api/` (the pipeline). Governed by the **chunk 4 scoped exception** in
`docs/GOAL_AUTONOMY.md`: `api/` + `api/tests` edits and root-`.venv` pytest are
in-scope for this goal; real Gemini/network calls, docker, deploy, and push stay
hard-gated. Tests mock Gemini and the network — the goal run makes no external
calls. The real pipeline run and prod deploy are done manually afterward.

**Decisions (locked):**
- **Keep the existing global Jekyll blog flow untouched** (`retrieve_daily_results`
  + `create_blogpost`). Chunk 4 *adds* a per-category blurb path alongside it.
- **Dynamic fetch list:** `SELECT DISTINCT category_slug FROM user_categories`
  unioned with the fixed public list (`cs.LG`, `cs.AI`, `cs.CL`, `cs.CV`,
  `stat.ML`), sorted, deduped. `api/` reads the app SQLite via a new
  `APP_DB_PATH` env.
- **Blurb generator reuses `Agent.identify_important_papers(papers)`** per
  category (already emits themed markdown with `[Title](url)` links).
- **Output:** `CONTENT_DIR/<NY-date>/<slug>.md`, one file per non-empty category.
  New `CONTENT_DIR` env for `api/`; date computed in `America/New_York` to match
  what the feed reads. Empty categories write no file (feed shows its placeholder).
- **Cross-listed papers** appear in every feed-category they're in (dedupe is
  per-category by URL, not global).

Code changes (all under `api/`):
- `arxiv_client.py`: add `retrieve_results_by_category(slugs)` → `{slug: [papers]}`,
  deduping within each category. Factor the per-feed fetch into a mockable seam
  (e.g. `_fetch_category_papers(slug)`). Leave `retrieve_daily_results` as-is.
- New `api/feeds.py`: `get_fetch_list(app_db_path)`, `today_ny()`,
  `generate_category_blurbs(papers_by_category, agent, content_dir, date)`.
- `api/settings.py`: add `APP_DB_PATH`, `CONTENT_DIR`, `FIXED_PUBLIC_CATEGORIES`.
- `api/main.py`: after the existing blog flow, run the per-category path.

Acceptance:
- [x] `get_fetch_list` returns the sorted, deduped union of `user_categories`
      slugs and the fixed public list; with zero users it equals the fixed list.
- [x] `retrieve_results_by_category` groups papers by source category; a paper in
      two feeds appears in both groups; duplicates within one feed are removed.
      (Network mocked via the fetch seam.)
- [x] `generate_category_blurbs` writes `CONTENT_DIR/<date>/<slug>.md` for each
      non-empty category, content = the agent's markdown; creates the day dir.
- [x] A category with an empty paper list produces no file.
- [x] The day-dir name is the `America/New_York` date.
- [x] Blurb content preserves the agent's themed markdown and `[Title](url)` links.
- [x] Existing blog flow still works: `api/tests/test_main.py` (and test_mixpanel)
      still pass; `create_blogpost` output unchanged.
- [x] No real Gemini or network call in any chunk 4 test (Agent + fetch mocked).

Test scaffolding (`api/tests/`, root `.venv`):
- A fake agent whose `identify_important_papers(papers)` returns canned markdown.
- Monkeypatch `ArxivClient._fetch_category_papers` to return canned papers.
- A temp app SQLite (users + user_categories) for `get_fetch_list`.
- A tmpdir `CONTENT_DIR`.

Test command: `PYTHONPATH=. .venv/bin/pytest api/tests`
