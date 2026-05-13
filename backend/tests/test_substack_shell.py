"""
Substack shell smoke tests:
- Reader: bookmarks CRUD + reads
- Writer: stats/published/scheduled
- Essays: search/filter + detail
Run after existing phase suites for regression on new shell.
"""
import time
import pytest
import requests

from conftest import BASE_URL, _bearer, _seed_user, _cleanup_user, _mongo_eval


# --- Essays search/filter (public) ---
class TestEssaysSearch:
    def test_essays_list_public(self):
        r = requests.get(f"{BASE_URL}/api/essays")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_essays_search_q(self):
        r = requests.get(f"{BASE_URL}/api/essays", params={"q": "nonexistent_xyz_zzz"})
        assert r.status_code == 200
        assert isinstance(r.json().get("items", []), list)

    def test_essays_search_market(self):
        r = requests.get(f"{BASE_URL}/api/essays", params={"market": "Atlanta"})
        assert r.status_code == 200
        assert "items" in r.json()


# --- Reader bookmarks ---
class TestReaderBookmarks:
    @pytest.fixture
    def member(self):
        u = _seed_user("readerbm", "approved", False)
        yield u
        _cleanup_user(u["user_id"])

    @pytest.fixture
    def writer_and_essay(self):
        # Seed a writer + a published essay directly via mongosh
        u = _seed_user("writeress", "approved", False)
        post_id = f"post_test_{int(time.time()*1000)}"
        _mongo_eval(f"""
use('test_database');
db.posts.insertOne({{
  post_id: '{post_id}',
  user_id: '{u['user_id']}',
  kind: 'essay',
  title: 'TEST_Essay_Bookmark',
  subtitle: 'sub',
  text: '# Hello\\n\\nbody text here.',
  status: 'approved',
  is_released: true,
  release_at: new Date().toISOString(),
  created_at: new Date().toISOString(),
  word_count: 3
}});
""")
        yield {"post_id": post_id, "user_id": u["user_id"]}
        _mongo_eval(f"use('test_database'); db.posts.deleteOne({{post_id: '{post_id}'}}); db.bookmarks.deleteMany({{post_id: '{post_id}'}});")
        _cleanup_user(u["user_id"])

    def test_get_bookmarks_empty(self, member):
        r = requests.get(f"{BASE_URL}/api/me/bookmarks", headers=_bearer(member["token"]))
        assert r.status_code == 200
        assert "items" in r.json()

    def test_bookmark_lifecycle(self, member, writer_and_essay):
        h = _bearer(member["token"])
        pid = writer_and_essay["post_id"]

        # Check status pre-create
        r = requests.get(f"{BASE_URL}/api/me/bookmarks/{pid}", headers=h)
        assert r.status_code == 200
        assert r.json().get("is_bookmarked") is False

        # POST create
        r = requests.post(f"{BASE_URL}/api/me/bookmarks/{pid}", headers=h)
        assert r.status_code in (200, 201)

        # GET status true
        r = requests.get(f"{BASE_URL}/api/me/bookmarks/{pid}", headers=h)
        assert r.status_code == 200
        assert r.json().get("is_bookmarked") is True

        # GET list contains the post
        r = requests.get(f"{BASE_URL}/api/me/bookmarks", headers=h)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert any(it.get("post_id") == pid for it in items)
        # No _id leakage
        for it in items:
            assert "_id" not in it

        # DELETE
        r = requests.delete(f"{BASE_URL}/api/me/bookmarks/{pid}", headers=h)
        assert r.status_code in (200, 204)

        # Verify removed
        r = requests.get(f"{BASE_URL}/api/me/bookmarks/{pid}", headers=h)
        assert r.status_code == 200
        assert r.json().get("is_bookmarked") is False

    def test_bookmarks_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/me/bookmarks")
        assert r.status_code in (401, 403)


# --- Writer dashboard ---
class TestWriterDashboard:
    @pytest.fixture
    def writer(self):
        u = _seed_user("writer", "approved", False)
        yield u
        _cleanup_user(u["user_id"])

    def test_stats_shape(self, writer):
        r = requests.get(f"{BASE_URL}/api/me/writer/stats", headers=_bearer(writer["token"]))
        assert r.status_code == 200
        d = r.json()
        for k in ("published_essays", "scheduled_essays", "short_posts_30d",
                  "follower_count", "essay_emails_sent_30d"):
            assert k in d, f"missing key {k}"
            assert isinstance(d[k], int)

    def test_published_list(self, writer):
        r = requests.get(f"{BASE_URL}/api/me/writer/published", headers=_bearer(writer["token"]))
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and isinstance(d["items"], list)

    def test_scheduled_list(self, writer):
        r = requests.get(f"{BASE_URL}/api/me/writer/scheduled", headers=_bearer(writer["token"]))
        assert r.status_code == 200
        assert isinstance(r.json().get("items", []), list)

    def test_writer_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/me/writer/stats")
        assert r.status_code in (401, 403)

    def test_writer_blocks_needs_app(self):
        u = _seed_user("needsappw", "needs_application", False)
        try:
            r = requests.get(f"{BASE_URL}/api/me/writer/stats", headers=_bearer(u["token"]))
            assert r.status_code in (401, 403)
        finally:
            _cleanup_user(u["user_id"])
