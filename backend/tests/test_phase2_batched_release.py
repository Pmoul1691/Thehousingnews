"""Phase 2 tests: batched release scheduler, /api/posts/mine, replies, admin release-now."""
import subprocess
import time
from datetime import datetime, timezone

import requests
import pytest


# ---- Helpers ----

def _no_underscore_id(obj):
    if isinstance(obj, dict):
        assert "_id" not in obj, f"_id leak: {obj}"
        for v in obj.values():
            _no_underscore_id(v)
    elif isinstance(obj, list):
        for v in obj:
            _no_underscore_id(v)


def _force_release_at_past(collection: str, id_field: str, id_value: str):
    """Set release_at to current UTC iso so it counts as <= now for the next admin/release-now call."""
    past_iso = datetime.now(timezone.utc).isoformat()
    subprocess.run(
        ["mongosh", "--quiet", "--eval",
         f"use('test_database'); db.{collection}.updateOne({{{id_field}: '{id_value}'}}, {{$set: {{release_at: '{past_iso}'}}}});"],
        check=True, capture_output=True,
    )


# ---- Module: POST /api/posts contract change ----

class TestPostCreatePendingRelease:
    def test_post_returns_pending_release_with_release_at(self, http, base_url, approved_user, bearer):
        r = http.post(f"{base_url}/api/posts",
                      json={"text": "Phase2 queued post"},
                      headers=bearer(approved_user["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "pending_release"
        assert "release_at" in data
        # release_at must be a parseable ISO and > created_at
        ra = datetime.fromisoformat(data["release_at"])
        ca = datetime.fromisoformat(data["created_at"])
        assert ra > ca
        # release_at must be in the future (a real 8:30/17:30 window)
        assert ra > datetime.now(timezone.utc)
        _no_underscore_id(data)

    def test_pending_post_not_in_public_feed(self, http, base_url, approved_user, bearer):
        unique = f"TEST_PENDING_{int(time.time()*1000)}"
        r = http.post(f"{base_url}/api/posts",
                      json={"text": unique},
                      headers=bearer(approved_user["token"]))
        assert r.status_code == 200
        pub = requests.get(f"{base_url}/api/posts/public")
        assert pub.status_code == 200
        texts = [it.get("text", "") for it in pub.json()["items"]]
        assert unique not in texts

    def test_pending_post_not_in_feed(self, http, base_url, approved_user, bearer):
        unique = f"TEST_PENDING_FEED_{int(time.time()*1000)}"
        r = http.post(f"{base_url}/api/posts",
                      json={"text": unique},
                      headers=bearer(approved_user["token"]))
        assert r.status_code == 200
        feed = http.get(f"{base_url}/api/posts/feed", headers=bearer(approved_user["token"]))
        assert feed.status_code == 200
        texts = [it.get("text", "") for it in feed.json()["items"]]
        assert unique not in texts


# ---- Module: GET /api/posts/mine ----

class TestPostsMine:
    def test_mine_unapproved_returns_empty(self, http, base_url, needs_app_user, bearer):
        r = http.get(f"{base_url}/api/posts/mine", headers=bearer(needs_app_user["token"]))
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_mine_returns_queued_and_released(self, http, base_url, approved_user, admin_user, bearer):
        # 1 queued
        unique_q = f"TEST_MINE_Q_{int(time.time()*1000)}"
        rq = http.post(f"{base_url}/api/posts", json={"text": unique_q},
                       headers=bearer(approved_user["token"]))
        assert rq.status_code == 200
        # 1 to be released
        unique_r = f"TEST_MINE_R_{int(time.time()*1000)}"
        rr = http.post(f"{base_url}/api/posts", json={"text": unique_r},
                       headers=bearer(approved_user["token"]))
        assert rr.status_code == 200
        released_pid = rr.json()["post_id"]
        _force_release_at_past("posts", "post_id", released_pid)
        rel = http.post(f"{base_url}/api/admin/release-now", headers=bearer(admin_user["token"]))
        assert rel.status_code == 200

        # GET /api/posts/mine
        mine = http.get(f"{base_url}/api/posts/mine", headers=bearer(approved_user["token"]))
        assert mine.status_code == 200
        items = mine.json()["items"]
        by_text = {it["text"]: it for it in items}
        assert unique_q in by_text
        assert unique_r in by_text
        # is_released booleans
        assert by_text[unique_r]["is_released"] is True
        assert by_text[unique_q]["is_released"] is False
        # Each item has reply_count
        for it in items:
            assert "reply_count" in it
            assert isinstance(it["reply_count"], int)
        _no_underscore_id(mine.json())


# ---- Module: Replies ----

class TestReplies:
    def test_reply_unapproved_403(self, http, base_url, needs_app_user, approved_user, bearer):
        # First create a post by approved
        rp = http.post(f"{base_url}/api/posts", json={"text": "host post"},
                       headers=bearer(approved_user["token"]))
        pid = rp.json()["post_id"]
        r = http.post(f"{base_url}/api/posts/{pid}/replies",
                      json={"text": "hi from unapproved"},
                      headers=bearer(needs_app_user["token"]))
        assert r.status_code == 403

    def test_reply_to_nonexistent_404(self, http, base_url, approved_user, bearer):
        r = http.post(f"{base_url}/api/posts/post_doesnotexist/replies",
                      json={"text": "ghost reply"},
                      headers=bearer(approved_user["token"]))
        assert r.status_code == 404

    def test_reply_text_validation(self, http, base_url, approved_user, bearer):
        rp = http.post(f"{base_url}/api/posts", json={"text": "host"},
                       headers=bearer(approved_user["token"]))
        pid = rp.json()["post_id"]
        # too long
        r = http.post(f"{base_url}/api/posts/{pid}/replies",
                      json={"text": "x" * 301},
                      headers=bearer(approved_user["token"]))
        assert r.status_code == 422
        # empty
        r2 = http.post(f"{base_url}/api/posts/{pid}/replies",
                       json={"text": ""},
                       headers=bearer(approved_user["token"]))
        assert r2.status_code == 422

    def test_reply_create_pending_and_visibility(
        self, http, base_url, approved_user, admin_user, bearer
    ):
        # host post
        rp = http.post(f"{base_url}/api/posts", json={"text": "host post for replies"},
                       headers=bearer(approved_user["token"]))
        pid = rp.json()["post_id"]
        # Release the host post so guests can also fetch its replies endpoint cleanly (not strictly required)
        _force_release_at_past("posts", "post_id", pid)
        http.post(f"{base_url}/api/admin/release-now", headers=bearer(admin_user["token"]))

        # create reply (pending)
        unique = f"TEST_REPLY_{int(time.time()*1000)}"
        r = http.post(f"{base_url}/api/posts/{pid}/replies",
                      json={"text": unique},
                      headers=bearer(approved_user["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "pending_release"
        assert data["reply_id"].startswith("reply_")
        assert "release_at" in data
        rid = data["reply_id"]
        _no_underscore_id(data)

        # Guest GET replies: pending reply should NOT appear
        g = requests.get(f"{base_url}/api/posts/{pid}/replies")
        assert g.status_code == 200
        guest_texts = [it.get("text", "") for it in g.json()["items"]]
        assert unique not in guest_texts

        # Approved author GET replies: own pending should appear with is_released=false
        own = http.get(f"{base_url}/api/posts/{pid}/replies",
                       headers=bearer(approved_user["token"]))
        assert own.status_code == 200
        own_items = own.json()["items"]
        match = [it for it in own_items if it["text"] == unique]
        assert match, f"own pending reply not visible to author: {own_items}"
        assert match[0]["is_released"] is False
        assert "author" in match[0]
        _no_underscore_id(own.json())

        # Force release & call release-now
        _force_release_at_past("replies", "reply_id", rid)
        rel = http.post(f"{base_url}/api/admin/release-now", headers=bearer(admin_user["token"]))
        assert rel.status_code == 200

        # Guest now sees the reply
        g2 = requests.get(f"{base_url}/api/posts/{pid}/replies")
        assert g2.status_code == 200
        g2_texts = [it.get("text", "") for it in g2.json()["items"]]
        assert unique in g2_texts
        for it in g2.json()["items"]:
            if it.get("text") == unique:
                assert it["is_released"] is True

        # Reply_count on the post should reflect the released reply
        feed = http.get(f"{base_url}/api/posts/feed", headers=bearer(approved_user["token"]))
        assert feed.status_code == 200
        for it in feed.json()["items"]:
            if it["post_id"] == pid:
                assert it["reply_count"] >= 1


# ---- Module: admin release-now ----

class TestAdminReleaseNow:
    def test_release_now_requires_admin(self, http, base_url, approved_user, bearer):
        r = http.post(f"{base_url}/api/admin/release-now",
                      headers=bearer(approved_user["token"]))
        assert r.status_code == 403

    def test_release_now_returns_summary(self, http, base_url, admin_user, bearer):
        r = http.post(f"{base_url}/api/admin/release-now",
                      headers=bearer(admin_user["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("posts_released", "emails_sent", "window", "kind"):
            assert key in data, f"missing key {key} in {data}"
        assert data["kind"] in ("am", "pm")

    def test_release_now_flips_due_pending(self, http, base_url, approved_user, admin_user, bearer):
        # Create + force due
        unique = f"TEST_RELEASE_{int(time.time()*1000)}"
        rp = http.post(f"{base_url}/api/posts", json={"text": unique},
                       headers=bearer(approved_user["token"]))
        pid = rp.json()["post_id"]
        _force_release_at_past("posts", "post_id", pid)
        rel = http.post(f"{base_url}/api/admin/release-now", headers=bearer(admin_user["token"]))
        assert rel.status_code == 200
        # Public feed must include
        pub = requests.get(f"{base_url}/api/posts/public")
        texts = [it.get("text", "") for it in pub.json()["items"]]
        assert unique in texts
        for it in pub.json()["items"]:
            if it.get("text") == unique:
                assert it["is_released"] is True


# ---- Module: release-window endpoint (still next_window) ----

class TestReleaseWindowEndpoint:
    def test_release_window_iso_future(self, http, base_url):
        r = http.get(f"{base_url}/api/release-window")
        assert r.status_code == 200
        data = r.json()
        nxt = datetime.fromisoformat(data["next_release_iso"])
        assert nxt > datetime.now(timezone.utc)
        assert data["timezone"] == "America/Chicago"
