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
