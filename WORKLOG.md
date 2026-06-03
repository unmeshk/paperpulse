# Worklog

## Session: 2026-06-03 (continued)

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
- Merge `refactor/oai-pmh-migration` → `main` to close all 4 Dependabot alerts
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
