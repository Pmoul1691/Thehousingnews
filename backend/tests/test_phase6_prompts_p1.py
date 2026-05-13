"""Phase 6: Subject of the Week + P1 backlog (rate-limit applications, image resize, media reorder).

Covers:
- /api/prompts/current , GET /api/prompts , GET /api/prompts/{id}
- POST/PATCH/DELETE /api/admin/prompts (admin demotion behavior)
- POST /api/prompts/suggestions , admin list/accept/reject
- POST /api/posts prompt_id linking (+ invalid → 400)
- Feed responses snapshot post.prompt
- POST /api/applications rate-limit (429 within 24h)
- POST /api/uploads image resize >1MB triggers, GIF NOT resized, dims capped at 1920
- Scheduler advance_weekly_prompt() function direct invocation
"""
import io
import os
import time
import asyncio
import pytest
import requests
from PIL import Image
from conftest import _seed_user, _cleanup_user, _mongo_eval

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.strip().split("=", 1)[1].strip().rstrip("/")
                break


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---- Subject of the Week: Public + Admin CRUD ----

class TestPromptsCRUD:
    def setup_method(self):
        self.admin = _seed_user("admin6a", "approved", True, email=f"peter@1691inc.com")
        self.member = _seed_user("memb6a", "approved", False)
        # Wipe leftover prompts
        _mongo_eval("use('test_database'); db.prompts.deleteMany({title:/^TEST_/});")
        _mongo_eval("use('test_database'); db.prompt_suggestions.deleteMany({user_name:/^Test/});")

    def teardown_method(self):
        _cleanup_user(self.admin["user_id"])
        _cleanup_user(self.member["user_id"])
        _mongo_eval("use('test_database'); db.prompts.deleteMany({title:/^TEST_/});")
        _mongo_eval("use('test_database'); db.prompt_suggestions.deleteMany({user_name:/^Test/});")

    def test_current_empty_when_none_active(self):
        # Make sure no active prompts exist
        _mongo_eval("use('test_database'); db.prompts.updateMany({status:'active'}, {$set:{status:'past'}});")
        r = requests.get(f"{BASE_URL}/api/prompts/current")
        assert r.status_code == 200
        assert r.json() == {}

    def test_admin_create_demotes_existing_active(self):
        # Create first active
        r1 = requests.post(f"{BASE_URL}/api/admin/prompts",
                           headers=_h(self.admin["token"]),
                           json={"title": "TEST_first", "body": "b1", "status": "active"})
        assert r1.status_code == 200, r1.text
        p1 = r1.json()["prompt_id"]
        # Create second active -> should demote first
        r2 = requests.post(f"{BASE_URL}/api/admin/prompts",
                           headers=_h(self.admin["token"]),
                           json={"title": "TEST_second", "body": "b2", "status": "active"})
        assert r2.status_code == 200
        p2 = r2.json()["prompt_id"]
        # /current should return the second
        cur = requests.get(f"{BASE_URL}/api/prompts/current").json()
        assert cur.get("prompt_id") == p2
        assert "response_count" in cur
        # The first should now be 'past'
        lst = requests.get(f"{BASE_URL}/api/prompts").json()["items"]
        statuses = {x["prompt_id"]: x["status"] for x in lst}
        assert statuses.get(p1) == "past"
        assert statuses.get(p2) == "active"

    def test_non_admin_create_forbidden(self):
        r = requests.post(f"{BASE_URL}/api/admin/prompts",
                          headers=_h(self.member["token"]),
                          json={"title": "TEST_x", "body": "b", "status": "active"})
        assert r.status_code == 403

    def test_get_prompt_with_responses(self):
        r = requests.post(f"{BASE_URL}/api/admin/prompts",
                          headers=_h(self.admin["token"]),
                          json={"title": "TEST_with_resp", "body": "b", "status": "active"})
        pid = r.json()["prompt_id"]
        # Get details
        det = requests.get(f"{BASE_URL}/api/prompts/{pid}")
        assert det.status_code == 200
        d = det.json()
        assert d["prompt_id"] == pid
        assert isinstance(d["responses"], list)
        assert d["response_count"] == 0

    def test_patch_and_delete(self):
        r = requests.post(f"{BASE_URL}/api/admin/prompts",
                          headers=_h(self.admin["token"]),
                          json={"title": "TEST_edit", "body": "b", "status": "active"})
        pid = r.json()["prompt_id"]
        # Patch
        pr = requests.patch(f"{BASE_URL}/api/admin/prompts/{pid}",
                            headers=_h(self.admin["token"]),
                            json={"title": "TEST_edited", "body": "newbody", "status": "past"})
        assert pr.status_code == 200
        det = requests.get(f"{BASE_URL}/api/prompts/{pid}").json()
        assert det["title"] == "TEST_edited"
        assert det["status"] == "past"
        # Delete
        dr = requests.delete(f"{BASE_URL}/api/admin/prompts/{pid}", headers=_h(self.admin["token"]))
        assert dr.status_code == 200
        det2 = requests.get(f"{BASE_URL}/api/prompts/{pid}")
        assert det2.status_code == 404


# ---- Suggestions ----

class TestSuggestions:
    def setup_method(self):
        self.admin = _seed_user("admin6b", "approved", True, email=f"peter@1691inc.com")
        self.member = _seed_user("memb6b", "approved", False)
        self.outsider = _seed_user("out6b", "needs_application", False)
        _mongo_eval("use('test_database'); db.prompt_suggestions.deleteMany({user_name:/^Test/});")

    def teardown_method(self):
        _cleanup_user(self.admin["user_id"])
        _cleanup_user(self.member["user_id"])
        _cleanup_user(self.outsider["user_id"])
        _mongo_eval("use('test_database'); db.prompt_suggestions.deleteMany({user_name:/^Test/});")

    def test_member_can_suggest_then_admin_accepts(self):
        r = requests.post(f"{BASE_URL}/api/prompts/suggestions",
                          headers=_h(self.member["token"]),
                          json={"text": "How does your week start its rhythm?"})
        assert r.status_code == 200, r.text
        sid = r.json()["suggestion_id"]
        # outsider blocked
        r2 = requests.post(f"{BASE_URL}/api/prompts/suggestions",
                           headers=_h(self.outsider["token"]),
                           json={"text": "I have not been approved yet to suggest things"})
        assert r2.status_code == 403
        # admin list
        lst = requests.get(f"{BASE_URL}/api/admin/prompts/suggestions",
                           headers=_h(self.admin["token"])).json()
        assert any(s["suggestion_id"] == sid for s in lst["items"])
        # accept
        ar = requests.post(f"{BASE_URL}/api/admin/prompts/suggestions/{sid}/accept",
                          headers=_h(self.admin["token"]))
        assert ar.status_code == 200
        assert "text" in ar.json()

    def test_reject_suggestion(self):
        r = requests.post(f"{BASE_URL}/api/prompts/suggestions",
                          headers=_h(self.member["token"]),
                          json={"text": "Reject this please, it's just a test"})
        sid = r.json()["suggestion_id"]
        rj = requests.post(f"{BASE_URL}/api/admin/prompts/suggestions/{sid}/reject",
                          headers=_h(self.admin["token"]))
        assert rj.status_code == 200


# ---- Posts with prompt_id ----

class TestPostPromptLink:
    def setup_method(self):
        self.admin = _seed_user("admin6c", "approved", True, email=f"peter@1691inc.com")
        self.member = _seed_user("memb6c", "approved", False)
        _mongo_eval("use('test_database'); db.prompts.deleteMany({title:/^TEST_/});")

    def teardown_method(self):
        _cleanup_user(self.admin["user_id"])
        _cleanup_user(self.member["user_id"])
        _mongo_eval("use('test_database'); db.prompts.deleteMany({title:/^TEST_/});")

    def test_post_with_valid_prompt_id_sets_snapshot_in_feed(self):
        # Create a prompt
        pr = requests.post(f"{BASE_URL}/api/admin/prompts",
                           headers=_h(self.admin["token"]),
                           json={"title": "TEST_link", "body": "b", "status": "active"})
        pid = pr.json()["prompt_id"]
        # Post with prompt_id
        pp = requests.post(f"{BASE_URL}/api/posts",
                           headers=_h(self.member["token"]),
                           json={"kind": "post", "text": "writing about the week", "prompt_id": pid})
        assert pp.status_code == 200, pp.text
        post_id = pp.json()["post_id"]
        # Force release_at to now so it appears in feed
        _mongo_eval(f"use('test_database'); db.posts.updateOne({{post_id:'{post_id}'}}, {{$set:{{release_at: new Date().toISOString(), status:'approved'}}}});")
        # Verify via /api/posts/public
        feed = requests.get(f"{BASE_URL}/api/posts/public").json()["items"]
        match = [x for x in feed if x["post_id"] == post_id]
        assert match, "Post not found in public feed"
        assert match[0].get("prompt", {}).get("prompt_id") == pid
        assert match[0]["prompt"]["title"] == "TEST_link"

    def test_post_with_invalid_prompt_id_400(self):
        bad = requests.post(f"{BASE_URL}/api/posts",
                            headers=_h(self.member["token"]),
                            json={"kind": "post", "text": "x", "prompt_id": "prompt_doesnotexist"})
        assert bad.status_code == 400


# ---- Applications rate-limit ----

class TestApplicationsRateLimit:
    def setup_method(self):
        self.u = _seed_user("rate6", "needs_application", False)

    def teardown_method(self):
        _cleanup_user(self.u["user_id"])
        _mongo_eval(f"use('test_database'); db.applications.deleteMany({{email:'{self.u['email']}'}});")

    def test_second_application_within_24h_returns_429(self):
        payload = {
            "why_joining": "I want to join because of the writing community I have heard about",
            "current_role": "Broker",
            "market": "Chicago",
            "years_in_real_estate": "5",
        }
        r1 = requests.post(f"{BASE_URL}/api/applications", headers=_h(self.u["token"]), json=payload)
        assert r1.status_code == 200, r1.text
        assert r1.json()["status"] == "pending"
        # Decline so user can re-submit; rate limit should still kick in
        _mongo_eval(f"use('test_database'); db.applications.updateMany({{user_id:'{self.u['user_id']}'}}, {{$set:{{status:'declined'}}}}); db.users.updateOne({{user_id:'{self.u['user_id']}'}}, {{$set:{{status:'needs_application'}}}});")
        r2 = requests.post(f"{BASE_URL}/api/applications", headers=_h(self.u["token"]), json=payload)
        assert r2.status_code == 429, f"Expected 429, got {r2.status_code}: {r2.text}"


# ---- Image resize on upload ----

def _make_jpeg(w=2400, h=1800) -> bytes:
    """Generate a JPEG well above 1MB."""
    img = Image.new("RGB", (w, h))
    # Random-ish pattern to defeat JPEG compression
    px = img.load()
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            px[x, y] = ((x * 7) % 255, (y * 11) % 255, ((x + y) * 13) % 255)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=95)
    return out.getvalue()


def _make_gif(w=2400, h=2400) -> bytes:
    """Generate a >1MB GIF."""
    img = Image.new("P", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (x * y) % 256
    out = io.BytesIO()
    img.save(out, format="GIF")
    return out.getvalue()


class TestImageResize:
    def setup_method(self):
        self.u = _seed_user("up6", "approved", False)

    def teardown_method(self):
        _cleanup_user(self.u["user_id"])

    def test_large_jpeg_resized_and_capped_at_1920(self):
        data = _make_jpeg(2400, 1800)
        assert 1 * 1024 * 1024 < len(data) < 6 * 1024 * 1024, f"Test prep failed: {len(data)} bytes"
        r = requests.post(
            f"{BASE_URL}/api/uploads",
            headers=_h(self.u["token"]),
            files={"file": ("big.jpg", data, "image/jpeg")},
            data={"kind": "posts"},
        )
        assert r.status_code == 200, r.text
        stored_size = r.json()["size"]
        assert stored_size < len(data), f"Resize did not reduce: orig={len(data)}, new={stored_size}"
        # Fetch the file & verify dims
        path = r.json()["path"]
        fr = requests.get(f"{BASE_URL}/api/uploads/file/{path}")
        assert fr.status_code == 200
        img = Image.open(io.BytesIO(fr.content))
        assert max(img.size) <= 1920, f"Dimensions not capped at 1920: {img.size}"

    def test_gif_is_not_resized(self):
        data = _make_gif(2400, 2400)
        if len(data) <= 1 * 1024 * 1024:
            pytest.skip(f"Test GIF too small ({len(data)} bytes)")
        r = requests.post(
            f"{BASE_URL}/api/uploads",
            headers=_h(self.u["token"]),
            files={"file": ("anim.gif", data, "image/gif")},
            data={"kind": "posts"},
        )
        assert r.status_code == 200, r.text
        # Size should be (approximately) unchanged
        assert r.json()["size"] == len(data), f"GIF was resized: orig={len(data)} new={r.json()['size']}"
        assert r.json()["content_type"] == "image/gif"


# ---- Scheduler advance_weekly_prompt direct invocation ----

class TestAdvanceWeeklyPrompt:
    def setup_method(self):
        self.admin = _seed_user("admin6d", "approved", True, email=f"peter@1691inc.com")
        _mongo_eval("use('test_database'); db.prompts.deleteMany({title:/^TEST_advance_/});")

    def teardown_method(self):
        _cleanup_user(self.admin["user_id"])
        _mongo_eval("use('test_database'); db.prompts.deleteMany({title:/^TEST_advance_/});")

    def test_advance_promotes_scheduled(self):
        # Seed one active and one scheduled
        r1 = requests.post(f"{BASE_URL}/api/admin/prompts",
                           headers=_h(self.admin["token"]),
                           json={"title": "TEST_advance_old", "body": "", "status": "active"})
        old = r1.json()["prompt_id"]
        # Scheduled in the past so it's eligible
        r2 = requests.post(f"{BASE_URL}/api/admin/prompts",
                           headers=_h(self.admin["token"]),
                           json={"title": "TEST_advance_next", "body": "",
                                 "week_start": "2020-01-06T00:00:00+00:00",
                                 "status": "scheduled"})
        nxt = r2.json()["prompt_id"]

        # Call advance_weekly_prompt directly
        import sys
        sys.path.insert(0, "/app/backend")
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        from routes.prompts import advance_weekly_prompt
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        result = asyncio.new_event_loop().run_until_complete(advance_weekly_prompt(db))
        client.close()
        assert result["promoted"] == nxt

        # Verify state via API
        lst = requests.get(f"{BASE_URL}/api/prompts").json()["items"]
        smap = {x["prompt_id"]: x["status"] for x in lst}
        assert smap.get(old) == "past"
        cur = requests.get(f"{BASE_URL}/api/prompts/current").json()
        assert cur.get("prompt_id") == nxt
