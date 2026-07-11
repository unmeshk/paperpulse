"""Tests for chunk 1 — category seed + onboarding picker.

Covers every acceptance criterion in docs/PHASE1_CHUNKS.md chunk 1.
"""
import json
import re

import pytest


def _load_categories():
    from app.db import CATEGORIES_PATH

    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_csrf(client):
    """Hit GET /onboarding to populate the session CSRF token and return it."""
    resp = client.get("/onboarding")
    assert resp.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', resp.text)
    assert match, "csrf_token hidden field not found in onboarding form"
    return match.group(1)


# --- categories.json + seeding -------------------------------------------------


def test_categories_json_exists_and_valid():
    rows = _load_categories()
    assert len(rows) >= 100
    for row in rows:
        assert row.get("slug")
        assert row.get("display_name")
        assert row.get("archive")
        assert row.get("rss_url")


def test_seeded_active_count_matches_json(client):
    from app.db import get_conn

    expected = len(_load_categories())
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM categories WHERE active = 1").fetchone()["n"]
    assert count == expected


def test_seed_is_idempotent(client):
    from app.db import get_conn, init_db

    init_db()  # re-run; must not error or duplicate
    init_db()
    expected = len(_load_categories())
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"]
        active = conn.execute("SELECT COUNT(*) AS n FROM categories WHERE active = 1").fetchone()["n"]
    assert total == expected
    assert active == expected


# --- GET /onboarding -----------------------------------------------------------


def test_onboarding_get_anonymous_redirects(client):
    resp = client.get("/onboarding", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/login"


def test_onboarding_get_logged_in_ok(auth_client):
    resp = auth_client.get("/onboarding")
    assert resp.status_code == 200


def test_onboarding_has_all_archives_and_search(auth_client):
    resp = auth_client.get("/onboarding")
    assert resp.status_code == 200
    html = resp.text
    assert 'type="search"' in html  # search input present
    archives = sorted({row["archive"] for row in _load_categories()})
    for archive in archives:
        assert f"<legend>{archive}</legend>" in html, f"missing archive header: {archive}"


# --- POST /onboarding ----------------------------------------------------------


def test_post_valid_five_slugs_persists(auth_client, db_user):
    from app.db import get_conn

    token = _get_csrf(auth_client)
    slugs = ["cs.LG", "cs.AI", "cs.CL", "cs.CV", "stat.ML"]
    resp = auth_client.post(
        "/onboarding",
        data={"slugs": slugs, "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category_slug FROM user_categories WHERE user_id = ?", (db_user["id"],)
        ).fetchall()
    assert sorted(r["category_slug"] for r in rows) == sorted(slugs)
    assert len(rows) == 5


def test_post_full_replace_not_append(auth_client, db_user):
    from app.db import get_conn

    token = _get_csrf(auth_client)
    auth_client.post(
        "/onboarding",
        data={"slugs": ["cs.LG", "cs.AI"], "csrf_token": token},
        follow_redirects=False,
    )
    auth_client.post(
        "/onboarding",
        data={"slugs": ["cs.CV"], "csrf_token": token},
        follow_redirects=False,
    )
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category_slug FROM user_categories WHERE user_id = ?", (db_user["id"],)
        ).fetchall()
    assert [r["category_slug"] for r in rows] == ["cs.CV"]


def test_post_six_slugs_rejected(auth_client):
    token = _get_csrf(auth_client)
    slugs = ["cs.LG", "cs.AI", "cs.CL", "cs.CV", "stat.ML", "math.ST"]
    resp = auth_client.post(
        "/onboarding",
        data={"slugs": slugs, "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_post_unknown_slug_rejected(auth_client):
    token = _get_csrf(auth_client)
    resp = auth_client.post(
        "/onboarding",
        data={"slugs": ["cs.LG", "not.a.real.slug"], "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_post_anonymous_blocked(client):
    resp = client.post(
        "/onboarding",
        data={"slugs": ["cs.LG"], "csrf_token": "anything"},
        follow_redirects=False,
    )
    assert resp.status_code in (401, 302)
    if resp.status_code == 302:
        assert resp.headers["location"] == "/auth/login"


def test_post_missing_csrf_forbidden(auth_client):
    _get_csrf(auth_client)  # establish a session token, then omit it from the POST
    resp = auth_client.post(
        "/onboarding",
        data={"slugs": ["cs.LG"]},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_post_invalid_csrf_forbidden(auth_client):
    _get_csrf(auth_client)
    resp = auth_client.post(
        "/onboarding",
        data={"slugs": ["cs.LG"], "csrf_token": "wrong-token"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_session_persists_after_onboarding(auth_client):
    token = _get_csrf(auth_client)
    resp = auth_client.post(
        "/onboarding",
        data={"slugs": ["cs.LG"], "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    home = auth_client.get("/")
    assert home.status_code == 200
    assert "tester@example.com" in home.text
