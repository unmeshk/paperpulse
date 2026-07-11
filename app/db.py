import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import APP_DIR, settings

SCHEMA_PATH = APP_DIR / "schema.sql"
CATEGORIES_PATH = APP_DIR / "data" / "categories.json"


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


@contextmanager
def get_conn():
    conn = _connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        _ensure_archive_column(conn)
        _seed_categories(conn)


def _ensure_archive_column(conn: sqlite3.Connection) -> None:
    """Add the categories.archive column to pre-existing DBs (CREATE TABLE IF NOT
    EXISTS won't add it to a table created before this column existed)."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(categories)").fetchall()}
    if "archive" not in cols:
        conn.execute("ALTER TABLE categories ADD COLUMN archive TEXT NOT NULL DEFAULT ''")


def _seed_categories(conn: sqlite3.Connection) -> None:
    """Seed the categories table from data/categories.json. Idempotent: an
    existing slug is updated in place, so re-running adds no duplicate rows."""
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        rows = json.load(f)
    for sort_order, row in enumerate(rows):
        conn.execute(
            "INSERT INTO categories (slug, display_name, description, rss_url, archive, active, sort_order) "
            "VALUES (?, ?, ?, ?, ?, 1, ?) "
            "ON CONFLICT(slug) DO UPDATE SET "
            "display_name = excluded.display_name, description = excluded.description, "
            "rss_url = excluded.rss_url, archive = excluded.archive, active = 1, "
            "sort_order = excluded.sort_order",
            (row["slug"], row["display_name"], row.get("description"), row["rss_url"], row["archive"], sort_order),
        )
