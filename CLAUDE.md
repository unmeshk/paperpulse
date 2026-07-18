# ArXivSum Development Guide

Use the caveman skill from global skills always unless specifically asked to not use it

## Commands
- Run application: `PYTHONPATH=. .venv/bin/python -m api.main`
- Run tests: `PYTHONPATH=. .venv/bin/python -m pytest api/tests/test_main.py`
- Run specific test: `PYTHONPATH=. .venv/bin/python -m pytest api/tests/test_main.py::test_function_name`
- Start dev server: `docker compose up --build`
- Start prod server: `docker-compose -f docker-compose.prod.yml up -d`

## Code Style Guide
- **Imports**: Group imports (stdlib → third-party → local)
- **Formatting**: 4-space indentation, 120 char line limit
- **Types**: Use docstrings for type documentation
- **Naming**: snake_case for variables/functions, PascalCase for classes
- **Error Handling**: Use specific exception handling with try/except
- **Documentation**: Multi-line docstrings with Args/Returns sections
- **Classes**: Prefix private methods with underscore (_)
- **Testing**: Use pytest fixtures for reusable test components

Set `PROJECT_ENV=dev` for development mode (uses cached files) or `PROJECT_ENV=prod` for production.

## Architecture

**Pipeline (run once daily via cron):**
1. `ArxivClient.retrieve_daily_results()` — fetches today's papers from arXiv RSS feeds (`rss.arxiv.org/rss/{category}`), one request per category, deduplicates across categories, filters to the most recent pubDate only
2. `FileHandler` — in dev mode, caches paper list to `papers-YYYY-MM-DD.pkl` in `PROJECT_DIR`
3. `Agent.identify_important_papers()` — batches papers, calls Gemini (`gemini-3.1-flash-lite`) to produce a thematic markdown summary with inline `[Title](url)` links; sleeps 30s between batches to respect free-tier rate limits
4. `create_blogpost()` — writes Jekyll markdown to `blog/_posts/YYYY-MM-DD-daily-summary.markdown`

**Key env vars (`api/.env`):**
- `GEMINI_API_KEY` — Gemini API key
- `PROJECT_DIR` — absolute path to repo root (where pkl files are saved)
- `PROJECT_ENV` — `dev` or `prod`

**RSS categories:** `cs.LG`, `cs.AI`, `cs.CL`, `cs.CV`

**Virtual env:** `.venv/` in repo root