"""Test fixtures and bootstrap.

Env vars must be set BEFORE any `app.*` module is imported, because
`app.config` reads them at import time and freezes them into a dataclass.
"""
import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="paperpulse-tests-")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-do-not-use-in-prod")
os.environ.setdefault("DB_PATH", os.path.join(_TMP_DIR, "test.sqlite"))
os.environ.setdefault("CONTENT_DIR", os.path.join(_TMP_DIR, "content"))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_db(client):
    """Truncate per-user state and clear feed content before each test so test
    order doesn't matter.

    Depends on `client` so app startup (table creation + category seeding) has
    already run. `categories` is intentionally left seeded.
    """
    import shutil

    from app.config import settings
    from app.db import get_conn

    with get_conn() as conn:
        conn.execute("DELETE FROM user_categories")
        conn.execute("DELETE FROM users")
    if settings.content_dir.exists():
        for child in settings.content_dir.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    yield


@pytest.fixture
def db_user(client):
    """Insert a real user row and return it as a dict."""
    from app.db import get_conn

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (google_sub, email, display_name) VALUES (?, ?, ?)",
            ("test-sub-1", "tester@example.com", "Tester"),
        )
        user_id = int(cur.lastrowid)
    return {"id": user_id, "email": "tester@example.com", "display_name": "Tester", "picture_url": None}


@pytest.fixture
def auth_client(client, db_user):
    """A TestClient with `current_user` overridden to return `db_user`."""
    from app.auth import current_user
    from app.main import app

    app.dependency_overrides[current_user] = lambda: db_user
    yield client
    app.dependency_overrides.pop(current_user, None)


def feed_today() -> str:
    """Today's date in the feed timezone (America/New_York), YYYY-MM-DD."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


@pytest.fixture
def assign_categories(db_user):
    """Assign category slugs to the test user directly via DB insert."""
    from app.db import get_conn

    def _assign(slugs, user_id=None):
        uid = db_user["id"] if user_id is None else user_id
        with get_conn() as conn:
            conn.executemany(
                "INSERT INTO user_categories (user_id, category_slug) VALUES (?, ?)",
                [(uid, s) for s in slugs],
            )

    return _assign


@pytest.fixture
def write_blurb():
    """Write CONTENT_DIR/<date>/<slug>.md; date defaults to NY-today."""
    from app.config import settings

    def _write(slug, body, date=None):
        day = settings.content_dir / (date or feed_today())
        day.mkdir(parents=True, exist_ok=True)
        path = day / f"{slug}.md"
        path.write_text(body, encoding="utf-8")
        return path

    return _write
