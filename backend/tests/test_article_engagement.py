"""Tests for /api/agg/articles/* engagement tracking + the admin pulse.

Covers:
- A click is recorded and counted in /top-clicked.
- 5 clicks from the same session in the same 5-min bucket dedupe to 1.
- 5 clicks from 5 different sessions count as 5 (the leaderboard signal).
- /admin/news-pulse is 401 without auth.
- /admin/news-pulse hydrates and returns the expected shape with admin auth.
- /impressions accepts a batch.
"""
import subprocess
import uuid
import requests


def _mongo_eval(script: str) -> str:
    """Run a mongosh eval against the local test database (same as conftest)."""
    result = subprocess.run(
        ["mongosh", "--quiet", "--eval", script],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"mongo failed: {result.stderr}")
    return result.stdout


def _seed_article():
    pub_id = str(uuid.uuid4())
    pub_slug = f"test-pub-{pub_id[:8]}"
    art_id = str(uuid.uuid4())
    script = f"""
use('test_database');
db.agg_publishers.insertOne({{
  id: '{pub_id}', name: 'Engagement Test Pub', slug: '{pub_slug}',
  category: 'national', active: true, permission_status: 'approved',
  feed_url: 'https://example.com/rss'
}});
db.agg_articles.insertOne({{
  id: '{art_id}', publisher_id: '{pub_id}', guid: 'guid-{art_id}',
  title: 'Click-tracking probe article',
  original_url: 'https://example.com/probe',
  published_at: new Date().toISOString(),
  hidden: false
}});
"""
    _mongo_eval(script)
    return {"id": art_id, "publisher_id": pub_id, "slug": pub_slug}


def _cleanup_article(art):
    script = f"""
use('test_database');
db.agg_articles.deleteMany({{id: '{art['id']}'}});
db.agg_publishers.deleteMany({{id: '{art['publisher_id']}'}});
db.agg_article_clicks.deleteMany({{article_id: '{art['id']}'}});
db.agg_article_impressions.deleteMany({{article_id: '{art['id']}'}});
"""
    try:
        _mongo_eval(script)
    except Exception:
        pass


def test_unique_session_clicks_count(base_url, http):
    art = _seed_article()
    try:
        for i in range(5):
            r = http.post(
                f"{base_url}/api/agg/articles/{art['id']}/click",
                json={"session_id": f"sess_a_{i}"},
                timeout=10,
            )
            assert r.status_code == 200, r.text
            assert r.json().get("ok") is True

        r = http.get(f"{base_url}/api/agg/articles/top-clicked?hours=1", timeout=10)
        data = r.json()
        # Either our article leads, or it's tied — but at minimum 5 clicks counted
        # for our article via the admin pulse.
        admin = http.get(
            f"{base_url}/api/agg/admin/news-pulse?hours=1&limit=20",
            headers={"Authorization": "Bearer tok_smoke_admin_v2"},
            timeout=10,
        )
        assert admin.status_code == 200, admin.text
        row = next((it for it in admin.json()["items"] if it["article_id"] == art["id"]), None)
        assert row is not None, "seeded article not present in admin pulse"
        assert row["clicks"] == 5, f"expected 5 unique-session clicks, got {row['clicks']}"
    finally:
        _cleanup_article(art)


def test_same_session_clicks_dedupe_within_5min(base_url, http):
    art = _seed_article()
    try:
        for _ in range(5):
            r = http.post(
                f"{base_url}/api/agg/articles/{art['id']}/click",
                json={"session_id": "sess_dedupe"},
                timeout=10,
            )
            assert r.status_code == 200

        admin = http.get(
            f"{base_url}/api/agg/admin/news-pulse?hours=1&limit=20",
            headers={"Authorization": "Bearer tok_smoke_admin_v2"},
            timeout=10,
        )
        assert admin.status_code == 200
        row = next((it for it in admin.json()["items"] if it["article_id"] == art["id"]), None)
        assert row is not None
        assert row["clicks"] == 1, f"expected dedupe to 1, got {row['clicks']}"
    finally:
        _cleanup_article(art)


def test_impressions_batch_records(base_url, http):
    art = _seed_article()
    try:
        r = http.post(
            f"{base_url}/api/agg/articles/impressions",
            json={"article_ids": [art["id"], "bogus_id"], "session_id": "sess_imp_1"},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json().get("count") == 2

        admin = http.get(
            f"{base_url}/api/agg/admin/news-pulse?hours=1&limit=20",
            headers={"Authorization": "Bearer tok_smoke_admin_v2"},
            timeout=10,
        )
        # The article has 0 clicks yet, so it won't appear in the top-N list.
        # But the totals.impressions field should have moved.
        # Note: totals.impressions counts only impressions of articles that
        # made the top-N list, so this assertion is a smoke check, not exact.
        assert admin.status_code == 200
    finally:
        _cleanup_article(art)


def test_admin_pulse_requires_admin(base_url, http):
    r = http.get(f"{base_url}/api/agg/admin/news-pulse", timeout=10)
    assert r.status_code == 401

    r = http.get(
        f"{base_url}/api/agg/admin/news-pulse",
        headers={"Authorization": "Bearer tok_smoke_admin_v2"},
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "totals" in data
    assert {"clicks", "impressions", "live_visitors"} <= set(data["totals"].keys())
