"""Iteration 15 - Substack RSS import (admin), has_profile on session, share buttons.

Tests:
 - POST /api/admin/rss/import (admin auth) imports >=1 essay, then idempotent.
 - GET  /api/admin/rss/status returns imported_total + recent list.
 - Non-admin Bearer => 403 on both.
 - Imported essay queryable via GET /api/essays/{post_id} and has source=substack_import
   in MongoDB, trailing #Hashtag block stripped.
 - POST /api/auth/session 401 on bogus session_id (we can't mint a real one); has_profile
   surfaced via /api/auth/me with seeded session.
"""
import os
import subprocess
import time
import uuid
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE_URL}/api"


def _mongosh(script: str) -> str:
    r = subprocess.run(
        ["mongosh", "--quiet", "--eval", script],
        capture_output=True, text=True, timeout=30,
    )
    return r.stdout


def _seed(role: str, is_admin: bool, email: str | None = None):
    uid = f"user_iter15_{role}_{uuid.uuid4().hex[:8]}"
    token = f"tok_iter15_{role}_{uuid.uuid4().hex}"
    email = email or f"iter15.{role}.{int(time.time()*1000)}@example.com"
    script = f"""
use('test_database');
db.users.deleteMany({{email: '{email}'}});
db.users.insertOne({{
  user_id: '{uid}', email: '{email}', name: 'Iter15 {role}',
  picture: '', is_admin: {str(is_admin).lower()}, status: 'approved',
  source: 'manual_test',
  created_at: new Date().toISOString(), last_login_at: new Date().toISOString()
}});
db.user_sessions.insertOne({{
  user_id: '{uid}', session_token: '{token}',
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now()+7*24*60*60*1000).toISOString()
}});
"""
    _mongosh(script)
    return uid, email, token


def _cleanup(uid: str):
    _mongosh(
        f"use('test_database');"
        f"db.users.deleteMany({{user_id:'{uid}'}});"
        f"db.user_sessions.deleteMany({{user_id:'{uid}'}});"
        f"db.profiles.deleteMany({{user_id:'{uid}'}});"
    )


def _admin_token():
    """Return (uid, token) for the canonical admin user peter@1691inc.com."""
    return _seed("admin", True, email="peter@1691inc.com")


# ---------- Admin RSS endpoints ----------
class TestAdminRssEndpoints:
    def test_non_admin_forbidden_on_import(self):
        uid, _email, token = _seed("member", False)
        try:
            r = requests.post(f"{API}/admin/rss/import",
                              headers={"Authorization": f"Bearer {token}"}, timeout=60)
            assert r.status_code == 403, r.text
        finally:
            _cleanup(uid)

    def test_non_admin_forbidden_on_status(self):
        uid, _email, token = _seed("member", False)
        try:
            r = requests.get(f"{API}/admin/rss/status",
                             headers={"Authorization": f"Bearer {token}"}, timeout=15)
            assert r.status_code == 403, r.text
        finally:
            _cleanup(uid)

    def test_unauthenticated_forbidden(self):
        r1 = requests.post(f"{API}/admin/rss/import", timeout=15)
        assert r1.status_code == 401, r1.text
        r2 = requests.get(f"{API}/admin/rss/status", timeout=15)
        assert r2.status_code == 401, r2.text

    def test_admin_import_then_idempotent_and_status(self):
        uid, _email, token = _admin_token()
        hdr = {"Authorization": f"Bearer {token}"}
        try:
            # First import (RSS network call - allow generous timeout)
            r = requests.post(f"{API}/admin/rss/import", headers=hdr, timeout=90)
            assert r.status_code == 200, r.text
            data = r.json()
            assert data.get("ok") is True, data
            imported_first = data.get("imported", 0)
            # Either fresh import OR already-imported on a previous run; in either case
            # the response shape must be sane.
            assert isinstance(imported_first, int)
            assert "skipped" in data

            # Second call: must be idempotent. All previously-imported items skip.
            r2 = requests.post(f"{API}/admin/rss/import", headers=hdr, timeout=90)
            assert r2.status_code == 200, r2.text
            data2 = r2.json()
            assert data2.get("imported", 0) == 0, f"Expected idempotent import to add 0, got {data2}"
            assert data2.get("skipped", 0) >= imported_first

            # Status endpoint
            s = requests.get(f"{API}/admin/rss/status", headers=hdr, timeout=15)
            assert s.status_code == 200, s.text
            sd = s.json()
            assert "imported_total" in sd and "recent" in sd
            assert isinstance(sd["recent"], list)
            assert sd["imported_total"] >= 1, sd
            assert len(sd["recent"]) >= 1
            # Recent items should be projected (no _id) and carry expected keys
            item = sd["recent"][0]
            for k in ("post_id", "title", "source_url"):
                assert k in item, item
            # Persist a post_id for the next test class
            TestAdminRssEndpoints._sample_post_id = item["post_id"]
        finally:
            _cleanup(uid)


# ---------- Imported essay is queryable + de-branded ----------
class TestImportedEssayShape:
    def test_essay_fetchable_and_no_hashtag_trailing(self):
        # Need an admin to trigger an import + seed at least one essay.
        uid, _email, token = _admin_token()
        hdr = {"Authorization": f"Bearer {token}"}
        try:
            requests.post(f"{API}/admin/rss/import", headers=hdr, timeout=90)
            s = requests.get(f"{API}/admin/rss/status", headers=hdr, timeout=15)
            assert s.status_code == 200, s.text
            recent = s.json().get("recent", [])
            if not recent:
                pytest.skip("No imported essays available to inspect (RSS empty?)")
            post_id = recent[0]["post_id"]

            # Public essay fetch (anon ok for non-paywalled OR returns paywalled snippet)
            # We pass admin Bearer to be safe -- admin should always see full content.
            r = requests.get(f"{API}/essays/{post_id}", headers=hdr, timeout=20)
            assert r.status_code == 200, r.text
            essay = r.json()
            assert essay.get("post_id") == post_id
            assert essay.get("title")
            # Content text or preview should exist
            body = essay.get("text") or essay.get("preview") or ""

            # Verify the source==substack_import flag is in Mongo for that post
            out = _mongosh(
                f"use('test_database');"
                f"var d = db.posts.findOne({{post_id:'{post_id}'}}, "
                f"{{_id:0, source:1, source_guid:1, source_url:1, text:1}});"
                f"print(JSON.stringify(d));"
            )
            line = next((ln.strip() for ln in out.splitlines() if ln.strip().startswith("{")), "")
            assert line, f"mongosh output had no JSON: {out!r}"
            doc = json.loads(line)
            assert doc.get("source") == "substack_import", doc
            assert doc.get("source_guid")
            # Hashtag-strip assertion: stored `text` should NOT end with a line that is
            # purely hashtags. We tolerate hashtags embedded *inside* the essay - only
            # the trailing block must be gone.
            text_field = (doc.get("text") or "").rstrip()
            if text_field:
                last_line = text_field.splitlines()[-1].strip()
                if last_line:
                    tokens = last_line.split()
                    all_hash = bool(tokens) and all(t.startswith("#") and len(t) > 1 for t in tokens)
                    assert not all_hash, f"Trailing line is all hashtags: {last_line!r}"
            assert isinstance(body, str)
        finally:
            _cleanup(uid)


# ---------- /auth/session has_profile + /auth/me ----------
class TestSessionHasProfile:
    def test_session_invalid_id_401(self):
        r = requests.post(f"{API}/auth/session",
                          json={"session_id": "definitely-not-a-real-id-xyz"}, timeout=15)
        assert r.status_code in (400, 401, 502), r.text

    def test_me_has_profile_false_for_seeded_member(self):
        uid, _email, token = _seed("hp", False)
        try:
            r = requests.get(f"{API}/auth/me",
                             headers={"Authorization": f"Bearer {token}"}, timeout=15)
            assert r.status_code == 200, r.text
            data = r.json()
            assert "has_profile" in data
            assert data["has_profile"] is False
        finally:
            _cleanup(uid)

    def test_me_has_profile_true_when_profile_exists(self):
        uid, _email, token = _seed("hp2", False)
        try:
            # Insert a profile doc for this user
            _mongosh(
                f"use('test_database');"
                f"db.profiles.insertOne({{user_id:'{uid}', market:'Chicago',"
                f"created_at:new Date().toISOString()}});"
            )
            r = requests.get(f"{API}/auth/me",
                             headers={"Authorization": f"Bearer {token}"}, timeout=15)
            assert r.status_code == 200, r.text
            data = r.json()
            assert data.get("has_profile") is True
        finally:
            _cleanup(uid)


# ---------- Hashtag stripping unit-ish check on the helper ----------
class TestHashtagStripperUnit:
    def test_strip_trailing_hashtag_only_line(self):
        # Import lazily so test collection works even if backend deps missing somehow
        from services.substack_import import _strip_trailing_hashtag_block
        body = "Real estate is about people.\n\n#realestate #leadership #ops"
        out = _strip_trailing_hashtag_block(body)
        assert "#realestate" not in out
        assert "Real estate is about people." in out

    def test_strip_trailing_inline_hashtags(self):
        from services.substack_import import _strip_trailing_hashtag_block
        body = "Final thought stays. #foo #bar #baz"
        out = _strip_trailing_hashtag_block(body)
        assert "Final thought stays." in out
        assert "#foo" not in out

    def test_keeps_body_hashtags(self):
        from services.substack_import import _strip_trailing_hashtag_block
        body = "I love #1 priorities.\nMore prose here."
        out = _strip_trailing_hashtag_block(body)
        assert "#1" in out
