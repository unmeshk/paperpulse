# Roadmap

## Phase 1 — In progress
Daily personalized feed via Google login + curated cs.* category selection. See `PHASE1_SPEC.md` for the full scope.

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
