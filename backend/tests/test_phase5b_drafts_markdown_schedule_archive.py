"""Phase 5b backend tests: markdown rendering, drafts, scheduled essays, member archive."""
import asyncio
import os
import re
import sys
import time
import uuid
import subprocess
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.strip().split("=", 1)[1].strip().rstrip("/")
                break

# Allow importing backend services for direct invocation of process_scheduled_essays
sys.path.insert(0, "/app/backend")


def _mongo(script: str) -> str:
    r = subprocess.run(["mongosh", "--quiet", "--eval", script], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"mongo failed: {r.stderr}")
    return r.stdout


def _bearer(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- Markdown rendering ----------------
# section: services/markdown_render.py + GET /api/essays/{id} html field
class TestMarkdownRender:
    def test_render_function_basic(self):
        from services.markdown_render import render
        out = render("# Heading\n\n**bold** and *italic*\n\n- item1\n- item2\n\n> quote\n\n[link](https://example.com)")
        assert "<h1>" in out and "Heading" in out
        assert "<strong>" in out and "bold" in out
        assert "<em>" in out and "italic" in out
        assert "<ul>" in out and "<li>" in out
        assert "<blockquote>" in out
        assert '<a href="https://example.com"' in out

    def test_render_strips_script_and_handlers(self):
        from services.markdown_render import render
        out = render('hello <script>alert(1)</script> world\n\n<img src="x" onerror="alert(2)">')
        # script tag stripped (its text content may remain harmlessly with strip=True)
        assert "<script" not in out
        assert "</script>" not in out
        # event handler attribute stripped
        assert "onerror" not in out
        assert "alert(2)" not in out  # onerror payload removed since it lived only in attribute

    def test_render_empty(self):
        from services.markdown_render import render
        assert render("") == ""
        assert render(None) == ""

    def test_essay_response_includes_html_for_member(self, approved_user):
        body = "# Hello\n\nThis is **bold** content with [link](https://example.com).\n\n" + ("x " * 80)
        r = requests.post(f"{BASE_URL}/api/posts",
                          headers=_bearer(approved_user["token"]),
                          json={"kind": "essay", "title": "MDTest", "text": body})
        assert r.status_code == 200, r.text
        pid = r.json()["post_id"]
        try:
            g = requests.get(f"{BASE_URL}/api/essays/{pid}", headers=_bearer(approved_user["token"]))
            assert g.status_code == 200
            data = g.json()
            assert data["paywall"] is False
            assert "html" in data and "<h1>" in data["html"] and "<strong>" in data["html"]
            assert data["text"].startswith("# Hello")
        finally:
            _mongo(f"use('test_database'); db.posts.deleteMany({{post_id:'{pid}'}});")

    def test_essay_response_paywall_no_html_text(self, approved_user):
        body = "# Title\n\n**bold** content " + ("x " * 80)
        r = requests.post(f"{BASE_URL}/api/posts",
                          headers=_bearer(approved_user["token"]),
                          json={"kind": "essay", "title": "PaywallMD", "text": body})
        pid = r.json()["post_id"]
        try:
            # Unauthenticated
            g = requests.get(f"{BASE_URL}/api/essays/{pid}")
            assert g.status_code == 200
            data = g.json()
            assert data["paywall"] is True
            assert "html" not in data
            assert "text" not in data
            assert "preview" in data
        finally:
            _mongo(f"use('test_database'); db.posts.deleteMany({{post_id:'{pid}'}});")


# ---------------- Drafts ----------------
# section: routes/drafts.py GET/PUT/DELETE /api/drafts/mine
class TestDrafts:
    def _cleanup(self, user_id):
        _mongo(f"use('test_database'); db.drafts.deleteMany({{user_id:'{user_id}'}});")

    def test_get_empty_draft(self, approved_user):
        try:
            r = requests.get(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]))
            assert r.status_code == 200
            assert r.json() == {}
        finally:
            self._cleanup(approved_user["user_id"])

    def test_put_then_get_draft(self, approved_user):
        try:
            payload = {"kind": "essay", "text": "Working on it", "title": "Draft Title",
                       "subtitle": "subtitle", "image_path": "/foo.png", "scheduled_at": None}
            r = requests.put(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]), json=payload)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["kind"] == "essay"
            assert d["title"] == "Draft Title"
            assert d["text"] == "Working on it"

            g = requests.get(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]))
            assert g.status_code == 200
            gd = g.json()
            assert gd["title"] == "Draft Title"
            assert gd["text"] == "Working on it"
            assert "_id" not in gd
        finally:
            self._cleanup(approved_user["user_id"])

    def test_put_upserts_single_draft(self, approved_user):
        try:
            requests.put(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]),
                         json={"kind": "post", "text": "v1"})
            requests.put(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]),
                         json={"kind": "post", "text": "v2"})
            # only one draft row
            out = _mongo(f"use('test_database'); print(db.drafts.countDocuments({{user_id:'{approved_user['user_id']}'}}));")
            assert "1" in out
            g = requests.get(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]))
            assert g.json()["text"] == "v2"
        finally:
            self._cleanup(approved_user["user_id"])

    def test_delete_draft(self, approved_user):
        try:
            requests.put(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]),
                         json={"kind": "post", "text": "to be deleted"})
            d = requests.delete(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]))
            assert d.status_code == 200
            assert d.json().get("ok") is True
            g = requests.get(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]))
            assert g.json() == {}
        finally:
            self._cleanup(approved_user["user_id"])

    def test_draft_cleared_on_publish(self, approved_user):
        pid = None
        try:
            requests.put(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]),
                         json={"kind": "post", "text": "to publish"})
            r = requests.post(f"{BASE_URL}/api/posts", headers=_bearer(approved_user["token"]),
                              json={"kind": "post", "text": "this is my short post"})
            assert r.status_code == 200, r.text
            pid = r.json()["post_id"]
            g = requests.get(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]))
            assert g.json() == {}, "draft should be auto-cleared on publish"
        finally:
            self._cleanup(approved_user["user_id"])
            if pid:
                _mongo(f"use('test_database'); db.posts.deleteMany({{post_id:'{pid}'}});")

    def test_draft_cleared_on_essay_publish(self, approved_user):
        pid = None
        try:
            requests.put(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]),
                         json={"kind": "essay", "text": "draft body"})
            body = "Long essay body. " * 20
            r = requests.post(f"{BASE_URL}/api/posts", headers=_bearer(approved_user["token"]),
                              json={"kind": "essay", "title": "T", "text": body})
            assert r.status_code == 200, r.text
            pid = r.json()["post_id"]
            g = requests.get(f"{BASE_URL}/api/drafts/mine", headers=_bearer(approved_user["token"]))
            assert g.json() == {}
        finally:
            self._cleanup(approved_user["user_id"])
            if pid:
                _mongo(f"use('test_database'); db.posts.deleteMany({{post_id:'{pid}'}});")


# ---------------- Scheduled essays ----------------
# section: POST /api/posts scheduled_at + services/scheduler.process_scheduled_essays
class TestScheduledEssays:
    def _seed_follower(self, writer_id):
        ts = int(time.time() * 1000)
        uid = f"user_fol_{ts}_{uuid.uuid4().hex[:6]}"
        email = f"fol.{ts}@example.com"
        _mongo(f"""use('test_database');
db.users.insertOne({{user_id:'{uid}', email:'{email}', name:'Fol', is_admin:false, status:'approved',
  source:'manual_test', created_at:new Date().toISOString(), last_login_at:new Date().toISOString()}});
db.follows.insertOne({{follower_id:'{uid}', followed_id:'{writer_id}', created_at:new Date().toISOString()}});
""")
        return uid

    def _cleanup(self, uids, pid=None):
        for uid in uids:
            _mongo(f"""use('test_database');
db.users.deleteMany({{user_id:'{uid}'}});
db.follows.deleteMany({{$or:[{{follower_id:'{uid}'}},{{followed_id:'{uid}'}}]}});
db.essay_dispatches.deleteMany({{recipient_user_id:'{uid}'}});
""")
        if pid:
            _mongo(f"use('test_database'); db.posts.deleteMany({{post_id:'{pid}'}}); db.essay_dispatches.deleteMany({{post_id:'{pid}'}});")

    def test_schedule_future_creates_scheduled_essay(self, approved_user):
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        body = "Scheduled essay body. " * 20
        pid = None
        try:
            r = requests.post(f"{BASE_URL}/api/posts", headers=_bearer(approved_user["token"]),
                              json={"kind": "essay", "title": "Sched", "text": body, "scheduled_at": future})
            assert r.status_code == 200, r.text
            data = r.json()
            pid = data["post_id"]
            assert data["status"] == "scheduled"
            assert data["release_at"] == future or data["release_at"].startswith(future[:19])
            # No dispatch rows
            time.sleep(1.0)
            out = _mongo(f"use('test_database'); print(db.essay_dispatches.countDocuments({{post_id:'{pid}'}}));")
            assert "0" in out.strip().split("\n")[-1]
        finally:
            if pid:
                _mongo(f"use('test_database'); db.posts.deleteMany({{post_id:'{pid}'}}); db.essay_dispatches.deleteMany({{post_id:'{pid}'}});")

    def test_schedule_past_rejected_422(self, approved_user):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        body = "x " * 80
        r = requests.post(f"{BASE_URL}/api/posts", headers=_bearer(approved_user["token"]),
                          json={"kind": "essay", "title": "PastSched", "text": body, "scheduled_at": past})
        assert r.status_code == 422, r.text
        assert "future" in r.text.lower()

    def test_short_post_ignores_scheduled_at(self, approved_user):
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        pid = None
        try:
            r = requests.post(f"{BASE_URL}/api/posts", headers=_bearer(approved_user["token"]),
                              json={"kind": "post", "text": "short post yo", "scheduled_at": future})
            assert r.status_code == 200, r.text
            data = r.json()
            pid = data["post_id"]
            assert data["status"] == "pending_release"
            # release_at should NOT equal scheduled_at (i.e., it should use the next window)
            assert data["release_at"] != future
        finally:
            if pid:
                _mongo(f"use('test_database'); db.posts.deleteMany({{post_id:'{pid}'}});")

    def test_process_scheduled_essays_flips_and_dispatches_idempotent(self, approved_user):
        # 1. Create a scheduled essay
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        body = "Scheduled body. " * 20
        r = requests.post(f"{BASE_URL}/api/posts", headers=_bearer(approved_user["token"]),
                          json={"kind": "essay", "title": "SchedDispatch", "text": body, "scheduled_at": future})
        assert r.status_code == 200
        pid = r.json()["post_id"]
        # 2. Seed a follower
        fol = self._seed_follower(approved_user["user_id"])
        try:
            # 3. Force release_at into the past
            past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            _mongo(f"use('test_database'); db.posts.updateOne({{post_id:'{pid}'}}, {{$set:{{release_at:'{past}'}}}});")
            # 4. Call process_scheduled_essays directly
            from motor.motor_asyncio import AsyncIOMotorClient
            from services.scheduler import process_scheduled_essays
            mclient = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db = mclient[os.environ.get("DB_NAME", "test_database")]
            loop = asyncio.new_event_loop()
            try:
                res = loop.run_until_complete(process_scheduled_essays(db))
                assert res["released"] >= 1
                # status flipped
                out = _mongo(f"use('test_database'); printjson(db.posts.findOne({{post_id:'{pid}'}}, {{_id:0, status:1}}));")
                assert "approved" in out
                # dispatch row created
                out2 = _mongo(f"use('test_database'); print(db.essay_dispatches.countDocuments({{post_id:'{pid}'}}));")
                last = out2.strip().split("\n")[-1]
                assert int(last) == 1, f"expected 1 dispatch row, got {last}"
                # 5. Idempotent: second invoke shouldn't add a new row or re-dispatch
                res2 = loop.run_until_complete(process_scheduled_essays(db))
                assert res2["released"] == 0  # no rows in 'scheduled' status anymore
                out3 = _mongo(f"use('test_database'); print(db.essay_dispatches.countDocuments({{post_id:'{pid}'}}));")
                assert int(out3.strip().split("\n")[-1]) == 1
            finally:
                loop.close()
                mclient.close()
        finally:
            self._cleanup([fol], pid)


# ---------------- Member archive ----------------
# section: GET /api/profile/{user_id}/essays
class TestMemberArchive:
    def test_archive_returns_released_essays_chronological_desc(self, approved_user):
        body = "Essay body content " * 20
        ids = []
        try:
            r1 = requests.post(f"{BASE_URL}/api/posts", headers=_bearer(approved_user["token"]),
                               json={"kind": "essay", "title": "First", "subtitle": "s1", "text": body})
            ids.append(r1.json()["post_id"])
            time.sleep(1.1)  # ensure distinct release_at
            r2 = requests.post(f"{BASE_URL}/api/posts", headers=_bearer(approved_user["token"]),
                               json={"kind": "essay", "title": "Second", "subtitle": "s2", "text": body})
            ids.append(r2.json()["post_id"])

            g = requests.get(f"{BASE_URL}/api/profile/{approved_user['user_id']}/essays",
                             headers=_bearer(approved_user["token"]))
            assert g.status_code == 200, g.text
            data = g.json()
            assert "items" in data
            items = [i for i in data["items"] if i.get("post_id") in ids]
            assert len(items) == 2
            # desc by release_at
            assert items[0]["release_at"] >= items[1]["release_at"]
            assert items[0]["title"] == "Second"
            # full text excluded
            for it in items:
                assert "text" not in it, f"text should be excluded from archive list: {it}"
                assert "title" in it and "subtitle" in it
                assert "created_at" in it and "release_at" in it
                assert "is_pete_pick" in it and isinstance(it["is_pete_pick"], bool)
                assert "_id" not in it
        finally:
            for pid in ids:
                _mongo(f"use('test_database'); db.posts.deleteMany({{post_id:'{pid}'}});")

    def test_archive_excludes_scheduled_unreleased(self, approved_user):
        body = "Essay body content " * 20
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        pid_released = None
        pid_sched = None
        try:
            r1 = requests.post(f"{BASE_URL}/api/posts", headers=_bearer(approved_user["token"]),
                               json={"kind": "essay", "title": "Released", "text": body})
            pid_released = r1.json()["post_id"]
            r2 = requests.post(f"{BASE_URL}/api/posts", headers=_bearer(approved_user["token"]),
                               json={"kind": "essay", "title": "Future", "text": body, "scheduled_at": future})
            pid_sched = r2.json()["post_id"]

            g = requests.get(f"{BASE_URL}/api/profile/{approved_user['user_id']}/essays",
                             headers=_bearer(approved_user["token"]))
            ids = [i["post_id"] for i in g.json()["items"]]
            assert pid_released in ids
            assert pid_sched not in ids, "scheduled (unreleased) essay should not appear in archive"
        finally:
            for pid in [pid_released, pid_sched]:
                if pid:
                    _mongo(f"use('test_database'); db.posts.deleteMany({{post_id:'{pid}'}});")

    def test_archive_excludes_short_posts(self, approved_user):
        pid_post = None
        try:
            r = requests.post(f"{BASE_URL}/api/posts", headers=_bearer(approved_user["token"]),
                              json={"kind": "post", "text": "short content"})
            pid_post = r.json()["post_id"]
            g = requests.get(f"{BASE_URL}/api/profile/{approved_user['user_id']}/essays",
                             headers=_bearer(approved_user["token"]))
            ids = [i["post_id"] for i in g.json()["items"]]
            assert pid_post not in ids
        finally:
            if pid_post:
                _mongo(f"use('test_database'); db.posts.deleteMany({{post_id:'{pid_post}'}});")

    def test_archive_empty_for_suspended_writer(self, approved_user, needs_app_user):
        # Use needs_app_user as the viewer (not admin); suspend the writer
        body = "Essay body content " * 20
        pid = None
        try:
            r = requests.post(f"{BASE_URL}/api/posts", headers=_bearer(approved_user["token"]),
                              json={"kind": "essay", "title": "WillSuspend", "text": body})
            pid = r.json()["post_id"]
            # suspend
            _mongo(f"use('test_database'); db.users.updateOne({{user_id:'{approved_user['user_id']}'}}, {{$set:{{suspended:true}}}});")
            g = requests.get(f"{BASE_URL}/api/profile/{approved_user['user_id']}/essays",
                             headers=_bearer(needs_app_user["token"]))
            assert g.status_code == 200
            assert g.json()["items"] == []
        finally:
            _mongo(f"use('test_database'); db.users.updateOne({{user_id:'{approved_user['user_id']}'}}, {{$set:{{suspended:false}}}});")
            if pid:
                _mongo(f"use('test_database'); db.posts.deleteMany({{post_id:'{pid}'}});")
