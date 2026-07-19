"""Tests for the feed: date-list archive (/feed) and per-day pages (/feed/<date>).

Originally covered docs/PHASE1_CHUNKS.md chunk 2; extended for the archive.
"""
from app.tests.conftest import feed_today


# --- auth / empty routing ------------------------------------------------------


def test_feed_anonymous_redirects_to_login(client):
    resp = client.get("/feed", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/login"


def test_feed_day_anonymous_redirects_to_login(client):
    resp = client.get(f"/feed/{feed_today()}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/login"


def test_feed_no_categories_redirects_to_onboarding(auth_client):
    resp = auth_client.get("/feed", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/onboarding"


def test_feed_with_categories_returns_200(auth_client, assign_categories):
    assign_categories(["cs.LG"])
    resp = auth_client.get("/feed")
    assert resp.status_code == 200


# --- date list -----------------------------------------------------------------


def test_feed_lists_dates_with_user_content_newest_first(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.LG"])
    write_blurb("cs.LG", "old", date="2026-07-01")
    write_blurb("cs.LG", "new", date="2026-07-15")
    html = auth_client.get("/feed").text
    assert 'href="/feed/2026-07-15"' in html
    assert 'href="/feed/2026-07-01"' in html
    assert html.index("2026-07-15") < html.index("2026-07-01")


def test_feed_list_excludes_dates_without_user_categories(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.LG"])
    write_blurb("cs.AI", "not my category", date="2026-07-10")  # other users' category only
    html = auth_client.get("/feed").text
    assert "2026-07-10" not in html


def test_feed_list_groups_by_month(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.LG"])
    write_blurb("cs.LG", "june", date="2026-06-30")
    write_blurb("cs.LG", "july", date="2026-07-01")
    html = auth_client.get("/feed").text
    assert "July 2026" in html
    assert "June 2026" in html


def test_feed_list_empty_shows_first_run_message(auth_client, assign_categories):
    assign_categories(["cs.LG"])
    resp = auth_client.get("/feed")
    assert resp.status_code == 200
    assert "after the next daily run" in resp.text


# --- per-day page --------------------------------------------------------------


def test_feed_day_sections_alphabetical_by_slug(auth_client, assign_categories, write_blurb):
    assign_categories(["stat.ML", "cs.AI", "cs.LG"])
    for slug in ["stat.ML", "cs.AI", "cs.LG"]:
        write_blurb(slug, f"Body for {slug}.")
    html = auth_client.get(f"/feed/{feed_today()}").text
    pos = [html.index(f'data-slug="{s}"') for s in ["cs.AI", "cs.LG", "stat.ML"]]
    assert pos == sorted(pos)


def test_feed_day_heading_shows_category(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.LG"])
    write_blurb("cs.LG", "Body.")
    html = auth_client.get(f"/feed/{feed_today()}").text
    assert "cs.LG" in html
    # display_name from seeded categories
    assert "Machine Learning" in html


def test_feed_day_renders_markdown_to_html(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.LG"])
    write_blurb("cs.LG", "## Theme 1: Scaling laws\n\n[Big Paper](http://arxiv.org/abs/2401.1)")
    html = auth_client.get(f"/feed/{feed_today()}").text
    assert "Theme 1: Scaling laws</h2>" in html
    assert 'href="http://arxiv.org/abs/2401.1"' in html
    assert ">Big Paper</a>" in html


def test_feed_day_escapes_raw_html(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.LG"])
    write_blurb("cs.LG", "Hello <script>alert(1)</script> world")
    html = auth_client.get(f"/feed/{feed_today()}").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_feed_day_missing_single_file_shows_placeholder(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.AI", "cs.LG"])
    write_blurb("cs.LG", "Only LG has content today.")  # cs.AI file absent; day dir exists
    resp = auth_client.get(f"/feed/{feed_today()}")
    assert resp.status_code == 200
    assert "Only LG has content today." in resp.text
    assert "no new papers today" in resp.text.lower()


# --- unlinkable days redirect back to the list ---------------------------------


def test_feed_day_without_content_redirects_to_list(auth_client, assign_categories):
    assign_categories(["cs.LG"])  # no content written for this date
    resp = auth_client.get("/feed/2026-01-01", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/feed"


def test_feed_day_other_categories_only_redirects_to_list(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.LG"])
    write_blurb("cs.AI", "someone else's category", date="2026-07-10")
    resp = auth_client.get("/feed/2026-07-10", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/feed"


def test_feed_day_bad_format_redirects_to_list(auth_client, assign_categories):
    assign_categories(["cs.LG"])
    resp = auth_client.get("/feed/not-a-date", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/feed"


# --- "/" routing ---------------------------------------------------------------


def test_index_logged_in_with_categories_redirects_to_feed(auth_client, assign_categories):
    assign_categories(["cs.LG"])
    resp = auth_client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/feed"


def test_index_logged_in_without_categories_redirects_to_onboarding(auth_client):
    resp = auth_client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/onboarding"


def test_index_anonymous_renders_landing(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'href="/login"' in resp.text
