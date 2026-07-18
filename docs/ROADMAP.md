# Roadmap

## Phase 1 — In progress
Daily personalized feed via Google login + curated cs.* category selection. See `PHASE1_SPEC.md` for the full scope.

Core app + pipeline shipped and verified in prod (2026-07-18). Items 1–6 shipped 2026-07-18 (PRs #45–#47). Remaining before Phase 1 closes:

1. ~~**Theme port.**~~ Shipped (PR #45, then superseded by the shared sidebar in #47).
2. ~~**Login entry point on the main blog page.**~~ Shipped (PR #46, routed through /login in #47).
3. ~~**Dedicated login/signup page.**~~ Shipped (PR #47): /login interstitial.
4. ~~**Logout lands on the main blog page**~~ Shipped (PR #47): ?logged_out=1 banner.
5. ~~**Hard delete.**~~ Shipped (PR #47): cascade delete + confirmation checkbox.
6. ~~**"Buy me a coffee" on the personalized feed.**~~ Shipped (PR #47): sidebar link.
7. **Cross-site login-state consistency.** Bug: while logged in, clicking About or What's New lands on the static blog, whose header always shows "Log in" — the logged-in state disappears. Fix so the header state is consistent when moving between app and blog (options: small JS on the blog that checks an app session endpoint and swaps the nav; or serve About/What's New from the app when logged in). Include a general consistency audit: walk every nav path logged in and logged out, verify the header always reflects actual session state.
8. **Update What's New for public launch.** Once OAuth leaves Testing mode and signup opens to everyone, add a What's New entry announcing the personalized feed.
9. **Deploy-script image pruning.** Each deploy leaves a ~1.4GB image set on the droplet; disk filled and broke a deploy on 2026-07-18. Prune old SHA-tagged sets in `deploy-paperpulse.sh` (keep current + previous; GHCR retains everything for rollback).

## Phase 2 — Next major release (post-Phase 1)
Feedback-driven feed improvement. Readers mark sections / papers / themes as "more like this" or "less like this." The system uses the signal to re-rank or re-prompt summaries over time. End state: each user's feed continually adapts to their preferences.

Open design questions for Phase 2 kickoff (not blocking now):
- Signal granularity: per-paper, per-section, or per-theme?
- Storage model: append-only events vs aggregated per-user scores?
- Re-ranking approach: heuristic weights, embedding similarity, or per-user prompt customization?
- Cold-start handling for new users with no signal.

## Backlog — Pick off opportunistically once Phase 1 is in production
Priority order will depend on what we learn from real users; this is not a fixed sequence.

1. **Free-text category input.** User types a topic of interest in plain text. System maps it to the closest cs.* category (or a curated topic vocabulary) and generates a daily summary for that custom topic, treated identically to a built-in category.
2. **Daily email digest.** Opt-in. Sends the user's personalized feed to an email address they choose.
3. **Personalized feed archive.** Show last N days of personalized feeds, not just today.
4. **Pricing tiers via Stripe.** E.g. free = 1 category, paid = more. Note: current LLM cost is fixed regardless of user count, so tiering is positioning/monetization, not cost recovery.
5. **Hover-to-explain on paper titles.** Hovering a paper title in the feed pops up a short plain-language explanation of the abstract (LLM-generated, cached per paper). Reduces clicks to arXiv for skim-reading users.

## Infrastructure — When the system outgrows current scaffolding
- **Proper observability stack** (Prometheus + Grafana) replacing the lightweight `daily_runs` SQLite table.
- **DB-backed content index** (e.g. `content_items` table with metadata + status + entitlement flags). Add when entitlements, per-user content, or free-form categories make filesystem-only storage insufficient.
- **SQLite → Postgres** if write contention or replication become real concerns. Not expected at MVP scale.

## Notes
- Phase 2 is the originally-stated next big move (the learning loop). Backlog items are smaller in scope and can land before, after, or in parallel with Phase 2 depending on user demand.
- See `PHASE1_SPEC.md` for the current Phase 1 scope and decisions.
