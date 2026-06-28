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

## Chunk 1 — Category seed + onboarding picker

**Goal:** A logged-in user can pick 1–5 categories and have them persisted.

Acceptance:
- [ ] `app/data/categories.json` exists, committed, contains >= 100 arXiv subcategories with `slug`, `display_name`, `archive` (cs/stat/math/...), `rss_url`.
- [ ] On `init_db()`, `categories` table is seeded from that JSON; re-running is idempotent (no duplicate rows, no errors).
- [ ] `SELECT COUNT(*) FROM categories WHERE active = 1` matches the JSON row count.
- [ ] `GET /onboarding` returns 200 for a logged-in user, 302 → `/auth/login` for anonymous.
- [ ] `GET /onboarding` HTML contains all archives as group headers and a search input.
- [ ] `POST /onboarding` with body `slugs=["cs.LG","cs.AI","cs.CL","cs.CV","stat.ML"]` for a logged-in user returns 302 → `/`, and `user_categories` has exactly 5 rows for that user.
- [ ] `POST /onboarding` with 6 slugs returns 400 (cap-of-5 enforced server-side).
- [ ] `POST /onboarding` with an unknown slug returns 400.
- [ ] `POST /onboarding` for an anonymous request returns 401 or 302 → `/auth/login`.
- [ ] After successful POST, `GET /` for that user redirects to `/feed` (or renders the feed placeholder — TBD when chunk 2 lands; for now just confirms session persists).
- [ ] CSRF token required on `POST /onboarding`; missing/invalid token returns 403.

Test scaffolding required:
- An auth-injection fixture (dependency-override on `current_user`) so tests don't have to run a real OAuth round-trip. This is the place to add it.
- A per-test DB reset fixture (truncate `users` and `user_categories` between tests) so test order doesn't matter.

---

## Chunk 2 — Feed page

**Goal:** Logged-in user with selected categories sees today's per-category blurbs.

Acceptance (draft — refine when chunk 1 lands):
- [ ] `GET /feed` returns 200 for logged-in user with categories selected.
- [ ] Response HTML contains one section per selected category, in alphabetical order by slug.
- [ ] Each section contains the markdown rendered from `CONTENT_DIR/YYYY-MM-DD/<slug>.md`.
- [ ] If a category's file is missing, section shows a "no new papers today" placeholder.
- [ ] If the whole `YYYY-MM-DD/` dir is missing, page shows "pipeline runs at 6am Eastern" empty state.
- [ ] "Today" is computed in `America/New_York`, not server UTC.
- [ ] Anonymous `GET /feed` returns 302 → `/auth/login`.

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
