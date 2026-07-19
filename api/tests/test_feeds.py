"""Tests for chunk 4 — pipeline per-category blurbs.

Covers every acceptance criterion in docs/PHASE1_CHUNKS.md chunk 4.
No real Gemini or network calls: the Agent and the RSS fetch are mocked.
"""
import re
import sqlite3
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.append(str(Path(__file__).parent.parent.parent))

from api.arxiv_client import ArxivClient
from api.feeds import generate_category_blurbs, get_fetch_list, today_ny
from api.settings import FIXED_PUBLIC_CATEGORIES


class FakeAgent:
    """Stand-in for Agent — records calls, returns canned markdown. No network."""

    def __init__(self, blurb="## Theme 1: T\n\n[Paper](http://p)"):
        self.blurb = blurb
        self.calls = []

    def identify_important_papers(self, papers):
        self.calls.append(papers)
        return self.blurb


def _paper(url, title="t"):
    return {"title": title, "url": url, "authors": [], "summary": "s"}


def _make_app_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE user_categories (user_id INTEGER, category_slug TEXT)")
    conn.executemany("INSERT INTO user_categories VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


# --- get_fetch_list ------------------------------------------------------------


def test_fetch_list_unions_users_and_fixed_sorted_deduped(tmp_path):
    db = tmp_path / "app.sqlite"
    _make_app_db(db, [(1, "math.ST"), (1, "cs.LG"), (2, "math.ST")])  # dup + overlap
    result = get_fetch_list(str(db))
    assert result == sorted(set(FIXED_PUBLIC_CATEGORIES) | {"math.ST", "cs.LG"})
    assert result == sorted(result)
    assert len(result) == len(set(result))


def test_fetch_list_same_category_many_users_appears_once(tmp_path):
    db = tmp_path / "app.sqlite"
    _make_app_db(db, [(1, "cs.LG"), (2, "cs.LG"), (3, "cs.LG")])
    result = get_fetch_list(str(db))
    assert result.count("cs.LG") == 1


def test_retrieve_results_by_category_fetches_each_slug_once(monkeypatch):
    from api.arxiv_client import ArxivClient

    client = ArxivClient([])
    calls = []
    monkeypatch.setattr(client, "_fetch_category_papers", lambda slug: calls.append(slug) or [])
    monkeypatch.setattr("api.arxiv_client.time.sleep", lambda s: None)

    results = client.retrieve_results_by_category(["cs.LG", "cs.AI", "cs.LG"])

    assert calls == ["cs.LG", "cs.AI"]  # one download per unique category
    assert set(results) == {"cs.LG", "cs.AI"}


def test_fetch_list_zero_users_equals_fixed(tmp_path):
    db = tmp_path / "app.sqlite"
    _make_app_db(db, [])
    assert get_fetch_list(str(db)) == sorted(FIXED_PUBLIC_CATEGORIES)


def test_fetch_list_missing_db_falls_back_to_fixed(tmp_path):
    assert get_fetch_list(str(tmp_path / "nope.sqlite")) == sorted(FIXED_PUBLIC_CATEGORIES)
    assert get_fetch_list("") == sorted(FIXED_PUBLIC_CATEGORIES)


# --- retrieve_results_by_category ----------------------------------------------


def test_results_grouped_by_category_and_cross_listed(monkeypatch):
    client = ArxivClient()
    feeds = {"cs.LG": [_paper("http://x")], "cs.AI": [_paper("http://x"), _paper("http://y")]}
    monkeypatch.setattr(client, "_fetch_category_papers", lambda slug: list(feeds[slug]))
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)

    result = client.retrieve_results_by_category(["cs.LG", "cs.AI"])
    assert set(result) == {"cs.LG", "cs.AI"}
    assert [p["url"] for p in result["cs.LG"]] == ["http://x"]
    assert [p["url"] for p in result["cs.AI"]] == ["http://x", "http://y"]
    # cross-listed paper appears in both groups
    assert any(p["url"] == "http://x" for p in result["cs.LG"])
    assert any(p["url"] == "http://x" for p in result["cs.AI"])


def test_fetch_category_papers_dedupes_within_feed():
    xml = b"""<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
      <item><title>A</title><link>http://dup</link><description>Abstract: s</description><dc:creator>Au</dc:creator></item>
      <item><title>A again</title><link>http://dup</link><description>Abstract: s</description><dc:creator>Au</dc:creator></item>
    </channel></rss>"""
    client = ArxivClient()
    mock_resp = Mock()
    mock_resp.read.return_value = xml
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        papers = client._fetch_category_papers("cs.LG")
    assert len(papers) == 1
    assert papers[0]["url"] == "http://dup"


# --- generate_category_blurbs --------------------------------------------------


def test_blurbs_written_for_nonempty_categories(tmp_path):
    agent = FakeAgent(blurb="## Theme 1: Scaling\n\n[Paper](http://p)")
    papers_by_category = {"cs.LG": [_paper("http://a")], "cs.AI": []}
    written = generate_category_blurbs(papers_by_category, agent, str(tmp_path), "2026-06-28")

    assert written == ["cs.LG"]
    out = tmp_path / "2026-06-28" / "cs.LG.md"
    assert out.exists()
    text = out.read_text()
    assert "## Theme 1: Scaling" in text
    assert "[Paper](http://p)" in text
    # empty category produced no file
    assert not (tmp_path / "2026-06-28" / "cs.AI.md").exists()
    # agent called once (only for the non-empty category)
    assert len(agent.calls) == 1


def test_no_day_dir_when_all_categories_empty(tmp_path):
    agent = FakeAgent()
    written = generate_category_blurbs({"cs.LG": [], "cs.AI": []}, agent, str(tmp_path), "2026-06-28")
    assert written == []
    assert not (tmp_path / "2026-06-28").exists()
    assert agent.calls == []


def test_blurbs_use_provided_date_dir(tmp_path):
    agent = FakeAgent()
    generate_category_blurbs({"cs.LG": [_paper("http://u")]}, agent, str(tmp_path), "2099-01-02")
    assert (tmp_path / "2099-01-02" / "cs.LG.md").exists()


# --- today_ny ------------------------------------------------------------------


def test_today_ny_is_new_york_date():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    value = today_ny()
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", value)
    assert value == datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
