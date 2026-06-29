"""Per-category feed blurbs for the PaperPulse personalized feed (Phase 1).

The pipeline writes one markdown blurb per category to
CONTENT_DIR/<NY-date>/<slug>.md, which the app's /feed page renders. This is
separate from (and additive to) the public Jekyll blog flow.
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from api.settings import FIXED_PUBLIC_CATEGORIES

logger = logging.getLogger(__name__)

FEED_TZ = ZoneInfo("America/New_York")


def today_ny():
    """Today's date (YYYY-MM-DD) in America/New_York — matches what the feed reads."""
    return datetime.now(FEED_TZ).strftime("%Y-%m-%d")


def get_fetch_list(app_db_path):
    """Sorted, deduped union of users' selected categories and the fixed public list.

    Reads `SELECT DISTINCT category_slug FROM user_categories` from the app SQLite.
    If the DB is missing or unreadable, falls back to the fixed public list so the
    public archive keeps shipping with zero users.

    Args:
        app_db_path: Path to the app's SQLite DB (may be empty/None).

    Returns:
        Sorted list of unique category slugs.
    """
    slugs = set(FIXED_PUBLIC_CATEGORIES)
    try:
        if app_db_path and Path(app_db_path).exists():
            conn = sqlite3.connect(app_db_path)
            try:
                rows = conn.execute("SELECT DISTINCT category_slug FROM user_categories").fetchall()
                slugs.update(row[0] for row in rows if row[0])
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"Could not read user categories from {app_db_path}: {e}")
    return sorted(slugs)


def generate_category_blurbs(papers_by_category, agent, content_dir, date):
    """Generate and write one markdown blurb per non-empty category.

    Writes to content_dir/<date>/<slug>.md. Empty categories produce no file
    (the feed shows its own "no new papers today" placeholder). The day dir is
    created only when there is at least one file to write.

    Args:
        papers_by_category: Dict mapping slug -> list of paper dicts.
        agent: An object with identify_important_papers(papers) -> markdown str.
        content_dir: Base content directory.
        date: Day-dir name (YYYY-MM-DD), typically today_ny().

    Returns:
        List of slugs that were written.
    """
    day_dir = Path(content_dir) / date
    written = []
    for slug, papers in papers_by_category.items():
        if not papers:
            continue
        try:
            blurb = agent.identify_important_papers(papers)
        except Exception as e:
            logger.error(f"Blurb generation failed for {slug}: {e}")
            continue
        if not blurb or not blurb.strip():
            continue
        day_dir.mkdir(parents=True, exist_ok=True)
        (day_dir / f"{slug}.md").write_text(blurb, encoding="utf-8")
        written.append(slug)
    logger.info(f"Wrote {len(written)} category blurbs for {date}: {written}")
    return written
