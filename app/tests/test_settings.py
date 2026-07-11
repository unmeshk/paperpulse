"""Tests for chunk 3 — settings + account deletion.

Covers every acceptance criterion in docs/PHASE1_CHUNKS.md chunk 3.
"""
import re


def _csrf(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', resp.text)
    assert match, f"csrf_token not found on {path}"
    return match.group(1)


def _user_slugs(user_id):
    from app.db import get_conn

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category_slug FROM user_categories WHERE user_id = ?", (user_id,)
        ).fetchall()
    return sorted(r["category_slug"] for r in rows)


# --- GET /settings -------------------------------------------------------------


def test_settings_get_anonymous_redirects(client):
    resp = client.get("/settings", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/login"


def test_settings_get_shows_current_selection_checked(auth_client, assign_categories, db_user):
    assign_categories(["cs.LG", "cs.AI"])
    html = auth_client.get("/settings").text
    assert 'value="cs.LG" checked' in html
    assert 'value="cs.AI" checked' in html
    # an unselected category is not checked
    assert 'value="cs.CV" checked' not in html


# --- POST /settings ------------------------------------------------------------


def test_settings_post_full_replace(auth_client, assign_categories, db_user):
    assign_categories(["cs.LG", "cs.AI"])
    token = _csrf(auth_client, "/settings")
    resp = auth_client.post(
        "/settings",
        data={"slugs": ["cs.CV", "cs.CL"], "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/feed"
    assert _user_slugs(db_user["id"]) == ["cs.CL", "cs.CV"]


def test_settings_post_six_slugs_rejected(auth_client):
    token = _csrf(auth_client, "/settings")
    resp = auth_client.post(
        "/settings",
        data={"slugs": ["cs.LG", "cs.AI", "cs.CL", "cs.CV", "stat.ML", "math.ST"], "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_settings_post_unknown_slug_rejected(auth_client):
    token = _csrf(auth_client, "/settings")
    resp = auth_client.post(
        "/settings",
        data={"slugs": ["cs.LG", "not.real"], "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_settings_post_missing_csrf_forbidden(auth_client):
    _csrf(auth_client, "/settings")
    resp = auth_client.post(
        "/settings",
        data={"slugs": ["cs.LG"]},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_settings_post_anonymous_blocked(client):
    resp = client.post(
        "/settings",
        data={"slugs": ["cs.LG"], "csrf_token": "x"},
        follow_redirects=False,
    )
    assert resp.status_code in (401, 302)


# --- delete account ------------------------------------------------------------


def test_delete_account_soft_deletes(auth_client, db_user):
    from app.db import get_conn

    token = _csrf(auth_client, "/settings")
    resp = auth_client.post(
        "/settings/delete-account",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"
    with get_conn() as conn:
        row = conn.execute(
            "SELECT deleted_at FROM users WHERE id = ?", (db_user["id"],)
        ).fetchone()
    assert row is not None  # row still exists (soft delete)
    assert row["deleted_at"] is not None  # deleted_at set


def test_delete_account_missing_csrf_forbidden(auth_client):
    _csrf(auth_client, "/settings")
    resp = auth_client.post(
        "/settings/delete-account",
        data={},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_after_delete_index_is_anonymous(auth_client, db_user):
    from app.auth import current_user
    from app.main import app

    token = _csrf(auth_client, "/settings")
    auth_client.post(
        "/settings/delete-account",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    # Drop the override so current_user uses the real (now-cleared) session.
    app.dependency_overrides.pop(current_user, None)
    resp = auth_client.get("/")
    assert resp.status_code == 200
    assert "Sign in with Google" in resp.text
