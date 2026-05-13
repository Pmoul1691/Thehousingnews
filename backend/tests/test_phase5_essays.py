"""Phase 5 tests: Substack-style essays.

Covers:
  - POST /api/posts kind='post' (or omitted): 500 char limit, batched release, status pending_release (regression)
  - POST /api/posts kind='essay': instant release, status approved, validation rules
  - Follower email dispatch into db.essay_dispatches + idempotency
  - GET /api/essays/{post_id}: member full, non-member/unauth paywall, 404 cases
  - Feed endpoints (/public, /feed, /mine, /by-user/{id}) include essays with preview not text
  - Pete picks work for essays
"""
import asyncio
import json
import subprocess
import time
from datetime import datetime, timezone

import pytest
import requests


# ----------------- helpers -----------------

def _no_underscore_id(obj):
    if isinstance(obj, dict):
        assert "_id" not in obj, f"_id leak: {list(obj.keys())}"
        for v in obj.values():
            _no_underscore_id(v)
    elif isinstance(obj, list):
        for v in obj:
            _no_underscore_id(v)


def _mongo(script: str) -> str:
    res = subprocess.run(
        ["mongosh", "--quiet", "--eval", script],
        capture_output=True, text=True, timeout=30,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr)
    return res.stdout


def _mongo_json(script: str):
    """Return JSON from a mongosh script using EJSON.stringify."""
    out = _mongo(script)
    out = out.strip()
    if not out:
        return None
    return json.loads(out)


def _count_essay_dispatches(post_id: str) -> int:
    out = _mongo(
        f"use('test_database'); print(db.essay_dispatches.countDocuments({{post_id: '{post_id}'}}));"
    ).strip().splitlines()
    # take the last numeric line
    for line in reversed(out):
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0


def _seed_extra_user(role: str, status: str = "approved", suspended: bool = False) -> dict:
    ts = int(time.time() * 1000) + hash(role) % 1000
    user_id = f"user_{role}_{ts}"
    token = f"tok_{role}_{ts}"
    email = f"test.{role}.{ts}@example.com"
    susp = "true" if suspended else "false"
    _mongo(
        f"use('test_database');"
        f"db.users.deleteMany({{email: '{email}'}});"
        f"db.users.insertOne({{user_id: '{user_id}', email: '{email}', name: 'Test {role}', "
        f"picture: '', is_admin: false, status: '{status}', suspended: {susp}, "
        f"source: 'manual_test', created_at: new Date().toISOString(), "
        f"last_login_at: new Date().toISOString()}});"
        f"db.user_sessions.insertOne({{user_id: '{user_id}', session_token: '{token}', "
        f"created_at: new Date().toISOString(), "
        f"expires_at: new Date(Date.now()+7*24*60*60*1000).toISOString()}});"
    )
    return {"user_id": user_id, "token": token, "email": email}


def _cleanup_user(user_id: str):
    try:
        _mongo(
            f"use('test_database');"
            f"db.users.deleteMany({{user_id: '{user_id}'}});"
            f"db.user_sessions.deleteMany({{user_id: '{user_id}'}});"
            f"db.profiles.deleteMany({{user_id: '{user_id}'}});"
            f"db.posts.deleteMany({{user_id: '{user_id}'}});"
            f"db.replies.deleteMany({{user_id: '{user_id}'}});"
            f"db.follows.deleteMany({{$or: [{{follower_id: '{user_id}'}}, {{followed_id: '{user_id}'}}]}});"
            f"db.essay_dispatches.deleteMany({{$or: [{{writer_id: '{user_id}'}}, {{recipient_user_id: '{user_id}'}}]}});"
        )
    except Exception:
        pass


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _make_essay_body(n=200):
    return "This is a test essay body. " * (n // 27 + 1)


# ----------------- Module: short post regression -----------------

class TestShortPostRegression:
    def test_short_post_kind_omitted_defaults_to_post(self, http, base_url, approved_user):
        r = http.post(
            f"{base_url}/api/posts",
            json={"text": "A short post without kind field."},
            headers=_bearer(approved_user["token"]),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        _no_underscore_id(body)
        assert body["kind"] == "post"
        assert body["status"] == "pending_release"
        # release_at should be in the future (next 8:30am or 5:30pm CT) and != created_at
        assert body["release_at"] > body["created_at"]

    def test_short_post_500_char_limit_enforced(self, http, base_url, approved_user):
        r = http.post(
            f"{base_url}/api/posts",
            json={"kind": "post", "text": "x" * 501},
            headers=_bearer(approved_user["token"]),
        )
        assert r.status_code == 422, r.text

    def test_short_post_500_chars_ok(self, http, base_url, approved_user):
        r = http.post(
            f"{base_url}/api/posts",
            json={"kind": "post", "text": "x" * 500},
            headers=_bearer(approved_user["token"]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["kind"] == "post"


# ----------------- Module: essay create + validation -----------------

class TestEssayCreate:
    def test_essay_happy_path(self, http, base_url, approved_user):
        body = _make_essay_body()
        r = http.post(
            f"{base_url}/api/posts",
            json={"kind": "essay", "title": "My Essay Title", "subtitle": "A sub", "text": body},
            headers=_bearer(approved_user["token"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        _no_underscore_id(data)
        assert data["kind"] == "essay"
        assert data["status"] == "approved"
        # instant release
        assert data["release_at"] == data["created_at"]
        assert data["post_id"].startswith("post_")

    def test_essay_missing_title_422(self, http, base_url, approved_user):
        r = http.post(
            f"{base_url}/api/posts",
            json={"kind": "essay", "text": _make_essay_body()},
            headers=_bearer(approved_user["token"]),
        )
        assert r.status_code == 422
        assert "title" in r.text.lower()

    def test_essay_empty_title_422(self, http, base_url, approved_user):
        r = http.post(
            f"{base_url}/api/posts",
            json={"kind": "essay", "title": "   ", "text": _make_essay_body()},
            headers=_bearer(approved_user["token"]),
        )
        assert r.status_code == 422

    def test_essay_body_too_short_422(self, http, base_url, approved_user):
        r = http.post(
            f"{base_url}/api/posts",
            json={"kind": "essay", "title": "Short Essay", "text": "x" * 50},
            headers=_bearer(approved_user["token"]),
        )
        assert r.status_code == 422
        assert "100" in r.text or "characters" in r.text.lower()

    def test_essay_body_max_50000_chars_ok(self, http, base_url, approved_user):
        r = http.post(
            f"{base_url}/api/posts",
            json={"kind": "essay", "title": "Long Essay", "text": "y" * 50000},
            headers=_bearer(approved_user["token"]),
        )
        assert r.status_code == 200

    def test_essay_body_over_50000_422(self, http, base_url, approved_user):
        r = http.post(
            f"{base_url}/api/posts",
            json={"kind": "essay", "title": "TooLong", "text": "y" * 50001},
            headers=_bearer(approved_user["token"]),
        )
        assert r.status_code == 422

    def test_essay_unapproved_user_403(self, http, base_url, needs_app_user):
        r = http.post(
            f"{base_url}/api/posts",
            json={"kind": "essay", "title": "Nope", "text": _make_essay_body()},
            headers=_bearer(needs_app_user["token"]),
        )
        assert r.status_code == 403


# ----------------- Module: follower dispatch -----------------

class TestEssayFollowerDispatch:
    def test_dispatch_to_two_followers(self, http, base_url, approved_user):
        # Writer W = approved_user
        F1 = _seed_extra_user("f1")
        F2 = _seed_extra_user("f2")
        # F1 and F2 follow approved_user
        for f in (F1, F2):
            r = http.post(
                f"{base_url}/api/users/{approved_user['user_id']}/follow",
                headers=_bearer(f["token"]),
            )
            assert r.status_code == 200, r.text
        try:
            # Create essay as W
            r = http.post(
                f"{base_url}/api/posts",
                json={"kind": "essay", "title": "Dispatch Test", "text": _make_essay_body()},
                headers=_bearer(approved_user["token"]),
            )
            assert r.status_code == 200, r.text
            post_id = r.json()["post_id"]

            # BackgroundTask runs after response; poll up to 5s
            count = 0
            for _ in range(25):
                count = _count_essay_dispatches(post_id)
                if count >= 2:
                    break
                time.sleep(0.2)
            assert count == 2, f"expected 2 dispatches, got {count}"

            # Distinct recipients
            distinct_out = _mongo(
                f"use('test_database');"
                f"var ids = db.essay_dispatches.distinct('recipient_user_id', {{post_id: '{post_id}'}});"
                f"print(JSON.stringify(ids));"
            )
            # find the last non-empty JSON line
            ids = None
            for line in reversed(distinct_out.strip().splitlines()):
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    ids = json.loads(line)
                    break
            assert ids is not None
            assert set(ids) == {F1["user_id"], F2["user_id"]}
        finally:
            _cleanup_user(F1["user_id"])
            _cleanup_user(F2["user_id"])

    def test_dispatch_idempotent_via_direct_invoke(self, http, base_url, approved_user):
        """Call dispatch_essay_to_followers twice; second call must not double-insert."""
        F1 = _seed_extra_user("idem1")
        # F1 follows approved_user
        r = http.post(
            f"{base_url}/api/users/{approved_user['user_id']}/follow",
            headers=_bearer(F1["token"]),
        )
        assert r.status_code == 200
        try:
            # Create essay
            r = http.post(
                f"{base_url}/api/posts",
                json={"kind": "essay", "title": "Idem Test", "text": _make_essay_body()},
                headers=_bearer(approved_user["token"]),
            )
            assert r.status_code == 200, r.text
            post_id = r.json()["post_id"]

            # wait for background task to settle
            for _ in range(25):
                if _count_essay_dispatches(post_id) >= 1:
                    break
                time.sleep(0.2)

            # Now call dispatch directly a second time
            import sys
            sys.path.insert(0, "/app/backend")
            from motor.motor_asyncio import AsyncIOMotorClient
            import os
            mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
            db_name = os.environ.get("DB_NAME", "test_database")
            client = AsyncIOMotorClient(mongo_url)
            db = client[db_name]
            from services.essay_dispatch import dispatch_essay_to_followers

            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(dispatch_essay_to_followers(db, post_id))
            finally:
                loop.close()
                client.close()

            # 2nd run: 1 follower exists, should be skipped (already dispatched)
            assert result.get("sent", 0) == 0
            assert result.get("skipped", 0) == 1

            # Total count remains exactly 1
            final = _count_essay_dispatches(post_id)
            assert final == 1, f"idempotency broken; got {final} rows"
        finally:
            _cleanup_user(F1["user_id"])


# ----------------- Module: GET /api/essays/{post_id} -----------------

def _create_essay(http, base_url, user, title="Read Test", text=None):
    text = text or (_make_essay_body() + " extra " + "z" * 400)
    r = http.post(
        f"{base_url}/api/posts",
        json={"kind": "essay", "title": title, "subtitle": "sub here", "text": text},
        headers=_bearer(user["token"]),
    )
    assert r.status_code == 200, r.text
    return r.json()["post_id"], text


class TestEssayReader:
    def test_member_gets_full_body(self, http, base_url, approved_user):
        post_id, text = _create_essay(http, base_url, approved_user)
        r = http.get(f"{base_url}/api/essays/{post_id}",
                     headers=_bearer(approved_user["token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        _no_underscore_id(body)
        assert body["paywall"] is False
        assert body["text"] == text.strip()
        assert body["kind"] == "essay"
        assert body["title"] == "Read Test"
        assert body["subtitle"] == "sub here"
        # author shape
        assert body["author"]["user_id"] == approved_user["user_id"]
        assert "name" in body["author"]
        assert "market" in body["author"]
        assert "avatar_path" in body["author"]
        assert "is_supporter" in body["author"]
        assert "reply_count" in body
        assert "is_pete_pick" in body
        assert "image_path" in body

    def test_unauth_paywall_with_preview(self, http, base_url, approved_user):
        post_id, _ = _create_essay(http, base_url, approved_user)
        r = http.get(f"{base_url}/api/essays/{post_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        _no_underscore_id(body)
        assert body["paywall"] is True
        assert "text" not in body
        assert "preview" in body
        assert len(body["preview"]) <= 325  # ~320 + "..."
        # still includes basic meta
        assert body["title"] == "Read Test"
        assert body["subtitle"] == "sub here"
        assert "author" in body

    def test_non_member_paywall(self, http, base_url, approved_user, needs_app_user):
        post_id, _ = _create_essay(http, base_url, approved_user)
        r = http.get(f"{base_url}/api/essays/{post_id}",
                     headers=_bearer(needs_app_user["token"]))
        assert r.status_code == 200
        body = r.json()
        assert body["paywall"] is True
        assert "text" not in body
        assert "preview" in body

    def test_hidden_essay_404(self, http, base_url, approved_user, admin_user):
        post_id, _ = _create_essay(http, base_url, approved_user)
        # admin hides it
        h = http.post(f"{base_url}/api/admin/posts/{post_id}/hide",
                      headers=_bearer(admin_user["token"]))
        assert h.status_code == 200, h.text
        r = http.get(f"{base_url}/api/essays/{post_id}",
                     headers=_bearer(approved_user["token"]))
        assert r.status_code == 404

    def test_suspended_author_essay_404(self, http, base_url, approved_user, admin_user):
        post_id, _ = _create_essay(http, base_url, approved_user)
        s = http.post(f"{base_url}/api/admin/users/{approved_user['user_id']}/suspend",
                      headers=_bearer(admin_user["token"]))
        assert s.status_code == 200, s.text
        try:
            r = http.get(f"{base_url}/api/essays/{post_id}",
                         headers=_bearer(admin_user["token"]))
            assert r.status_code == 404
        finally:
            http.post(f"{base_url}/api/admin/users/{approved_user['user_id']}/unsuspend",
                     headers=_bearer(admin_user["token"]))

    def test_post_kind_id_404(self, http, base_url, approved_user):
        # Create a short post, then try to read it via /api/essays
        rp = http.post(f"{base_url}/api/posts",
                       json={"text": "Just a short post."},
                       headers=_bearer(approved_user["token"]))
        assert rp.status_code == 200
        post_id = rp.json()["post_id"]
        r = http.get(f"{base_url}/api/essays/{post_id}",
                     headers=_bearer(approved_user["token"]))
        assert r.status_code == 404

    def test_unknown_essay_404(self, http, base_url, approved_user):
        r = http.get(f"{base_url}/api/essays/post_does_not_exist_xyz",
                     headers=_bearer(approved_user["token"]))
        assert r.status_code == 404


# ----------------- Module: feed payloads include essays w/ preview -----------------

class TestFeedEssayPayload:
    def test_public_feed_has_essay_with_preview_not_text(self, http, base_url, approved_user):
        title = f"Feed Essay {int(time.time())}"
        post_id, _ = _create_essay(http, base_url, approved_user, title=title)
        # essays release instantly, so /public should have it
        r = http.get(f"{base_url}/api/posts/public")
        assert r.status_code == 200
        items = r.json()["items"]
        essay_items = [it for it in items if it.get("post_id") == post_id]
        assert essay_items, "essay missing from /public feed"
        item = essay_items[0]
        _no_underscore_id(item)
        assert item["kind"] == "essay"
        assert item["title"] == title
        assert item["subtitle"] == "sub here"
        assert "preview" in item
        assert "text" not in item

    def test_feed_endpoint_returns_essay_preview(self, http, base_url, approved_user):
        post_id, _ = _create_essay(http, base_url, approved_user, title="FeedAuth")
        r = http.get(f"{base_url}/api/posts/feed",
                     headers=_bearer(approved_user["token"]))
        assert r.status_code == 200
        items = r.json()["items"]
        match = [it for it in items if it.get("post_id") == post_id]
        assert match
        assert match[0]["kind"] == "essay"
        assert "preview" in match[0]
        assert "text" not in match[0]

    def test_mine_returns_essay_preview(self, http, base_url, approved_user):
        post_id, _ = _create_essay(http, base_url, approved_user, title="MineEssay")
        r = http.get(f"{base_url}/api/posts/mine",
                     headers=_bearer(approved_user["token"]))
        assert r.status_code == 200
        items = r.json()["items"]
        match = [it for it in items if it.get("post_id") == post_id]
        assert match
        assert match[0]["kind"] == "essay"
        assert "preview" in match[0]
        assert "text" not in match[0]

    def test_by_user_returns_essay_preview(self, http, base_url, approved_user):
        post_id, _ = _create_essay(http, base_url, approved_user, title="ByUserEssay")
        r = http.get(f"{base_url}/api/posts/by-user/{approved_user['user_id']}",
                     headers=_bearer(approved_user["token"]))
        assert r.status_code == 200
        items = r.json()["items"]
        match = [it for it in items if it.get("post_id") == post_id]
        assert match
        assert match[0]["kind"] == "essay"
        assert "preview" in match[0]
        assert "text" not in match[0]


# ----------------- Module: Pete pick on essay -----------------

class TestPetePickEssay:
    def test_admin_can_pick_essay(self, http, base_url, approved_user, admin_user):
        post_id, _ = _create_essay(http, base_url, approved_user, title="PickMe")
        r = http.post(f"{base_url}/api/admin/posts/{post_id}/pick",
                      headers=_bearer(admin_user["token"]))
        assert r.status_code == 200, r.text
        # picks list should include the essay
        rp = http.get(f"{base_url}/api/posts/picks")
        assert rp.status_code == 200
        items = rp.json()["items"]
        match = [it for it in items if it.get("post_id") == post_id]
        assert match, "picked essay missing from /picks"
        assert match[0]["kind"] == "essay"
        # unpick
        ru = http.post(f"{base_url}/api/admin/posts/{post_id}/unpick",
                       headers=_bearer(admin_user["token"]))
        assert ru.status_code == 200
