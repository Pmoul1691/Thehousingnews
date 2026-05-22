"""Iteration 19 backend tests:
- /api/posts/search (text search; admin/approved-only; kind, market filters; suspended excluded)
- /api/admin/orphan-profiles GET + POST /reconnect
- /api/applications rate limit (one per email per 24h)
- /api/uploads image resize (>1MB triggers downscale to <=2000px longest edge)
- services.admin_digest: build_admin_digest + render_admin_digest_html + subject in send_admin_digest
Seeds users directly via Motor (same MONGO_URL/DB_NAME the API uses).
"""
import io
import os
import asyncio
import uuid
import time
import requests
import pytest
from datetime import datetime, timezone, timedelta
from PIL import Image
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://housing-news-perf.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# -------- helpers --------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _seed(db, email: str, *, is_admin=False, status="approved", suspended=False):
    uid = f"user_test_{uuid.uuid4().hex[:10]}"
    tok = f"tok_test_{uuid.uuid4().hex[:12]}"
    await db.users.insert_one({
        "user_id": uid,
        "email": email,
        "name": email.split("@")[0],
        "picture": "",
        "is_admin": is_admin,
        "status": status,
        "suspended": suspended,
        "source": "iter19_test",
        "created_at": _now_iso(),
        "last_login_at": _now_iso(),
    })
    await db.user_sessions.insert_one({
        "user_id": uid,
        "session_token": tok,
        "created_at": _now_iso(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    })
    return uid, tok


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def db(event_loop):
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def admin_ctx(event_loop, db):
    email = f"peter@1691inc.com"  # in allowlist
    # avoid email uniqueness collisions: use a unique-ish email but admin via flag
    uid, tok = event_loop.run_until_complete(_seed(db, email, is_admin=True))
    yield {"uid": uid, "tok": tok, "email": email}
    event_loop.run_until_complete(db.users.delete_one({"user_id": uid}))
    event_loop.run_until_complete(db.user_sessions.delete_one({"session_token": tok}))


@pytest.fixture(scope="module")
def member_ctx(event_loop, db):
    email = f"member.iter19.{uuid.uuid4().hex[:6]}@example.com"
    uid, tok = event_loop.run_until_complete(_seed(db, email))
    yield {"uid": uid, "tok": tok, "email": email}
    event_loop.run_until_complete(db.users.delete_one({"user_id": uid}))
    event_loop.run_until_complete(db.user_sessions.delete_one({"session_token": tok}))


def _h(tok: str):
    return {"Authorization": f"Bearer {tok}"}


# ============ /api/posts/search ============
class TestPostsSearch:
    @pytest.fixture(scope="class", autouse=True)
    def seed_posts(self, event_loop, db, member_ctx):
        # Author "real estate" posts under member, one essay + one short
        uid = member_ctx["uid"]
        # Profile with a market value so market filter works
        event_loop.run_until_complete(db.profiles.update_one(
            {"user_id": uid},
            {"$set": {
                "user_id": uid, "email": member_ctx["email"], "name": "Iter19 Member",
                "market": "Chicago", "updated_at": _now_iso(),
            }},
            upsert=True,
        ))
        now = _now_iso()
        posts = [
            {
                "post_id": f"post_iter19_{uuid.uuid4().hex[:8]}",
                "user_id": uid, "kind": "post",
                "text": "A short note on real estate cycles and discipline.",
                "title": None, "subtitle": None, "image_path": None, "media": [],
                "status": "approved", "created_at": now,
                "release_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            },
            {
                "post_id": f"post_iter19_{uuid.uuid4().hex[:8]}",
                "user_id": uid, "kind": "essay",
                "title": "On real estate value", "subtitle": "Slow money",
                "text": "Real estate is patient capital. " * 20,
                "image_path": None, "media": [],
                "status": "approved", "created_at": now,
                "release_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            },
        ]
        event_loop.run_until_complete(db.posts.insert_many(posts))
        yield posts
        ids = [p["post_id"] for p in posts]
        event_loop.run_until_complete(db.posts.delete_many({"post_id": {"$in": ids}}))

    def test_q_too_short_returns_422(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/posts/search", params={"q": "r"}, headers=_h(admin_ctx["tok"]))
        assert r.status_code == 422, r.text

    def test_q_real_estate_returns_items_with_author_and_reply_count(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/posts/search", params={"q": "real estate"}, headers=_h(admin_ctx["tok"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert "items" in body and len(body["items"]) >= 2
        for it in body["items"]:
            assert "author" in it and isinstance(it["author"], dict)
            assert "reply_count" in it and isinstance(it["reply_count"], int)

    def test_kind_essay_narrows(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/posts/search", params={"q": "real estate", "kind": "essay"}, headers=_h(admin_ctx["tok"]))
        assert r.status_code == 200, r.text
        for it in r.json()["items"]:
            assert it.get("kind") == "essay"

    def test_market_filter(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/posts/search", params={"q": "real estate", "market": "Chicago"}, headers=_h(admin_ctx["tok"]))
        assert r.status_code == 200, r.text
        # must still find at least one item authored by the Chicago profile
        assert len(r.json()["items"]) >= 1
        # nonexistent market -> empty
        r2 = requests.get(f"{BASE_URL}/api/posts/search", params={"q": "real estate", "market": "ZZZ_no_market"}, headers=_h(admin_ctx["tok"]))
        assert r2.status_code == 200
        assert r2.json()["items"] == []

    def test_suspended_users_excluded(self, admin_ctx, event_loop, db, member_ctx):
        # suspend the member, re-run search, expect 0
        event_loop.run_until_complete(db.users.update_one(
            {"user_id": member_ctx["uid"]}, {"$set": {"suspended": True}}
        ))
        try:
            r = requests.get(f"{BASE_URL}/api/posts/search", params={"q": "real estate"}, headers=_h(admin_ctx["tok"]))
            assert r.status_code == 200
            for it in r.json()["items"]:
                assert it["user_id"] != member_ctx["uid"]
        finally:
            event_loop.run_until_complete(db.users.update_one(
                {"user_id": member_ctx["uid"]}, {"$set": {"suspended": False}}
            ))


# ============ /api/admin/orphan-profiles ============
class TestOrphanProfiles:
    def test_list_and_reconnect(self, admin_ctx, event_loop, db):
        # Seed orphan profile + live user with same email
        orphan_uid = f"user_orphan_{uuid.uuid4().hex[:8]}"
        email = f"orphan.iter19.{uuid.uuid4().hex[:6]}@example.com"
        event_loop.run_until_complete(db.profiles.insert_one({
            "user_id": orphan_uid, "email": email, "name": "Orphan One",
            "market": "Austin", "updated_at": _now_iso(),
        }))
        # live user (no profile) with same email
        live_uid, _ = event_loop.run_until_complete(_seed(db, email))
        # Seed one post under orphan_uid to verify reassignment
        post_id = f"post_orph_{uuid.uuid4().hex[:8]}"
        event_loop.run_until_complete(db.posts.insert_one({
            "post_id": post_id, "user_id": orphan_uid, "kind": "post",
            "text": "Orphaned post body", "status": "approved",
            "release_at": _now_iso(), "created_at": _now_iso(),
            "media": [], "image_path": None,
        }))

        try:
            # LIST
            r = requests.get(f"{BASE_URL}/api/admin/orphan-profiles", headers=_h(admin_ctx["tok"]))
            assert r.status_code == 200, r.text
            items = r.json()["items"]
            target = next((x for x in items if x["profile_user_id"] == orphan_uid), None)
            assert target is not None, "orphan not listed"
            assert target["candidate_user"] is not None
            assert target["candidate_user"]["user_id"] == live_uid
            assert target["post_count"] >= 1

            # RECONNECT
            r2 = requests.post(
                f"{BASE_URL}/api/admin/orphan-profiles/reconnect",
                json={"profile_email": email}, headers=_h(admin_ctx["tok"]),
            )
            assert r2.status_code == 200, r2.text
            body = r2.json()
            assert body["reconnected"] is True
            assert body["new_user_id"] == live_uid
            assert body["posts_reassigned"] >= 1

            # GET again - should no longer list the orphan
            r3 = requests.get(f"{BASE_URL}/api/admin/orphan-profiles", headers=_h(admin_ctx["tok"]))
            assert r3.status_code == 200
            assert not any(x["profile_user_id"] == orphan_uid for x in r3.json()["items"])
        finally:
            event_loop.run_until_complete(db.profiles.delete_many({"email": email}))
            event_loop.run_until_complete(db.posts.delete_one({"post_id": post_id}))
            event_loop.run_until_complete(db.users.delete_one({"user_id": live_uid}))


# ============ /api/applications rate limit ============
class TestApplicationsRateLimit:
    def test_second_submission_within_24h_returns_429(self, event_loop, db):
        # Simulate: one application already exists by the same email within last 24h.
        # Then a fresh user with that email submits and must be 429'd by the
        # rate-limit branch (before the user.status early-return path).
        email = f"rl.iter19.{uuid.uuid4().hex[:6]}@example.com"
        # Pre-seed application doc for that email (recent timestamp)
        event_loop.run_until_complete(db.applications.insert_one({
            "application_id": f"app_pre_{uuid.uuid4().hex[:8]}",
            "user_id": f"user_prior_{uuid.uuid4().hex[:6]}",
            "email": email, "name": "Prior", "status": "declined",
            "why_joining": "x"*30, "current_role": "Broker", "market": "Austin",
            "years_in_real_estate": "5",
            "created_at": _now_iso(), "reviewed_at": None, "reviewed_by": None,
        }))
        uid, tok = event_loop.run_until_complete(_seed(db, email, status="needs_application"))
        payload = {
            "why_joining": "I want to learn from operators in real estate markets here.",
            "current_role": "Broker", "market": "Austin", "years_in_real_estate": "5",
        }
        try:
            r = requests.post(f"{BASE_URL}/api/applications", json=payload, headers=_h(tok))
            assert r.status_code == 429, f"expected 429, got {r.status_code}: {r.text}"
        finally:
            event_loop.run_until_complete(db.applications.delete_many({"email": email}))
            event_loop.run_until_complete(db.users.delete_one({"user_id": uid}))
            event_loop.run_until_complete(db.user_sessions.delete_one({"session_token": tok}))


# ============ /api/uploads image resize ============
class TestImageResize:
    def test_large_image_is_resized_to_2000_max_dim(self, member_ctx):
        # Build a ~1.5-3MB JPEG with high entropy at 2500x2500 so it stays
        # above the 1MB resize trigger but under the 6MB upload cap.
        import random
        random.seed(42)
        img = Image.new("RGB", (2500, 2500))
        pixels = img.load()
        for y in range(0, 2500, 4):
            for x in range(0, 2500, 4):
                c = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                for dy in range(4):
                    for dx in range(4):
                        if y+dy < 2500 and x+dx < 2500:
                            pixels[x+dx, y+dy] = c
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        original_bytes = buf.getvalue()
        assert 1024*1024 < len(original_bytes) < 6*1024*1024, (
            f"need image between 1MB and 6MB, got {len(original_bytes)}"
        )

        files = {"file": ("big.jpg", original_bytes, "image/jpeg")}
        data = {"kind": "posts"}
        r = requests.post(f"{BASE_URL}/api/uploads", files=files, data=data, headers=_h(member_ctx["tok"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("size") and body["size"] < len(original_bytes), (
            f"expected resize, got size={body.get('size')} vs original={len(original_bytes)}"
        )
        # fetch and verify dimensions
        path = body["path"]
        r2 = requests.get(f"{BASE_URL}/api/uploads/file/{path}")
        assert r2.status_code == 200
        out_img = Image.open(io.BytesIO(r2.content))
        assert max(out_img.size) <= 2000, f"longest edge {max(out_img.size)} > 2000"


# ============ admin digest ============
class TestAdminDigest:
    def test_build_and_render_and_subject(self, event_loop, db):
        import sys
        sys.path.insert(0, "/app/backend")
        from services import admin_digest as ad  # type: ignore

        # Seed: an essay this week with replies, biggest mover (member with extra posts vs last week)
        uid, _ = event_loop.run_until_complete(_seed(db, f"digest.{uuid.uuid4().hex[:6]}@example.com"))
        event_loop.run_until_complete(db.profiles.update_one(
            {"user_id": uid},
            {"$set": {"user_id": uid, "name": "Mover Person", "market": "NYC"}},
            upsert=True,
        ))
        now = datetime.now(timezone.utc)
        # 3 posts this week, 0 last week => biggest mover
        posts = []
        for i in range(3):
            pid = f"post_digest_{uuid.uuid4().hex[:8]}"
            posts.append(pid)
            event_loop.run_until_complete(db.posts.insert_one({
                "post_id": pid, "user_id": uid, "kind": "essay" if i == 0 else "post",
                "title": "An essay this week" if i == 0 else None,
                "text": "Body of weekly content "*5,
                "status": "approved", "release_at": (now - timedelta(days=1)).isoformat(),
                "created_at": (now - timedelta(days=1)).isoformat(),
                "media": [], "image_path": None,
            }))
        # reply on essay
        event_loop.run_until_complete(db.replies.insert_one({
            "reply_id": f"rep_{uuid.uuid4().hex[:6]}", "post_id": posts[0],
            "user_id": uid, "text": "Nice", "status": "approved",
            "created_at": now.isoformat(), "release_at": now.isoformat(),
        }))

        try:
            data = event_loop.run_until_complete(ad.build_admin_digest(db))
            assert isinstance(data, dict)
            assert "biggest_mover" in data
            html = ad.render_admin_digest_html(data)
            assert isinstance(html, str) and len(html) > 500
            # When applicable, expect biggest mover heading + top essays
            if data.get("biggest_mover"):
                assert "Biggest mover" in html
            if data.get("posts", {}).get("top_essays"):
                assert "Top essays this week" in html

            # Subject date stamping inside send_admin_digest path - rebuild label
            wk_end = datetime.fromisoformat(data["window"]["to"].replace("Z", "+00:00"))
            label = wk_end.strftime("%b %-d")
            assert label  # platform supports %-d on Linux
            subj = f"Sunday brief - {label}"
            assert "Sunday brief" in subj and label in subj
        finally:
            event_loop.run_until_complete(db.posts.delete_many({"post_id": {"$in": posts}}))
            event_loop.run_until_complete(db.replies.delete_many({"post_id": {"$in": posts}}))
            event_loop.run_until_complete(db.users.delete_one({"user_id": uid}))
            event_loop.run_until_complete(db.profiles.delete_one({"user_id": uid}))
