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

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_db(client):
    """Truncate per-user state before each test so test order doesn't matter.

    Depends on `client` so app startup (table creation + category seeding) has
    already run. `categories` is intentionally left seeded.
    """
    from app.db import get_conn

    with get_conn() as conn:
        conn.execute("DELETE FROM user_categories")
        conn.execute("DELETE FROM users")
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
