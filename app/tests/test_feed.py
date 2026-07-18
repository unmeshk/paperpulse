"""Tests for chunk 2 — feed page.

Covers every acceptance criterion in docs/PHASE1_CHUNKS.md chunk 2.
"""
from app.tests.conftest import feed_today


# --- auth / empty routing ------------------------------------------------------


def test_feed_anonymous_redirects_to_login(client):
    resp = client.get("/feed", follow_redirects=False)
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


# --- rendering -----------------------------------------------------------------


def test_feed_sections_alphabetical_by_slug(auth_client, assign_categories, write_blurb):
    assign_categories(["stat.ML", "cs.AI", "cs.LG"])
    for slug in ["stat.ML", "cs.AI", "cs.LG"]:
        write_blurb(slug, f"Body for {slug}.")
    html = auth_client.get("/feed").text
    pos = [html.index(f'data-slug="{s}"') for s in ["cs.AI", "cs.LG", "stat.ML"]]
    assert pos == sorted(pos)


def test_feed_section_heading_shows_category(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.LG"])
    write_blurb("cs.LG", "Body.")
    html = auth_client.get("/feed").text
    assert "cs.LG" in html
    # display_name from seeded categories
    assert "Machine Learning" in html


def test_feed_renders_markdown_to_html(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.LG"])
    write_blurb("cs.LG", "## Theme 1: Scaling laws\n\n[Big Paper](http://arxiv.org/abs/2401.1)")
    html = auth_client.get("/feed").text
    assert "Theme 1: Scaling laws</h2>" in html
    assert 'href="http://arxiv.org/abs/2401.1"' in html
    assert ">Big Paper</a>" in html


def test_feed_escapes_raw_html(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.LG"])
    write_blurb("cs.LG", "Hello <script>alert(1)</script> world")
    html = auth_client.get("/feed").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# --- missing content -----------------------------------------------------------


def test_feed_missing_single_file_shows_placeholder(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.AI", "cs.LG"])
    write_blurb("cs.LG", "Only LG has content today.")  # cs.AI file absent; day dir exists
    resp = auth_client.get("/feed")
    assert resp.status_code == 200
    assert "Only LG has content today." in resp.text
    assert "no new papers today" in resp.text.lower()


def test_feed_missing_day_dir_shows_empty_state(auth_client, assign_categories):
    assign_categories(["cs.LG"])  # categories selected, but no content dir for today
    resp = auth_client.get("/feed")
    assert resp.status_code == 200
    assert "pipeline runs at 6am Eastern" in resp.text


def test_feed_uses_new_york_today(auth_client, assign_categories, write_blurb):
    assign_categories(["cs.LG"])
    write_blurb("cs.LG", "NY-today content.", date=feed_today())
    resp = auth_client.get("/feed")
    assert resp.status_code == 200
    assert "NY-today content." in resp.text


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
